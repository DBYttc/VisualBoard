"""从画面里量"手指表观宽度"（像素），用作离摄像头远近的信号。

原理（单目针孔模型）：``w_px ≈ f · W_mm / Z``
    - W 是手指真实宽度（同一个用户基本恒定）
    - f 由摄像头视场决定（同一台机器恒定）
    => ``w_px`` 变大就表示手指离摄像头更近；用"相对基线的比例"当信号即可
       自校准（不需要知道 f、绝对距离或手的真实尺寸）。

为什么需要肤色掩膜：MediaPipe 的 21 个关键点全在手指**中轴线**上，任意两点距离
都是"指节长度"，量不出"粗细"，所以要自己分割出手指轮廓再沿垂直方向量。

已知的脆弱点（用 ``source: hand_scale`` 可绕开）：
    - 依赖光照/肤色/背景对比度，深色或同色背景会失效
    - 手指并拢时相邻手指会连成一块，此时用"单侧宽度×2"兜底（见 measure_width_in_mask）
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np
import numpy.typing as npt

from visualboard.core.config_loader import DepthPressSettings
from visualboard.core.types import Frame

# MediaPipe 关键点索引
WRIST = 0
INDEX_MCP = 5
INDEX_TIP = 8
MIDDLE_MCP = 9

# 采样步长（像素）。0.5 让边界估计有半像素分辨率：40px 宽的手指出 1.25% 量化噪声，
# 而我们要检测的信号量级是 10% 上下。
_STEP_PX = 0.5


@dataclass(frozen=True, slots=True)
class FingerWidth:
    """一次测量的结果。center/normal 用整帧坐标，方便直接画出来。"""

    width_px: float
    center: Tuple[float, float]
    normal: Tuple[float, float]
    samples: int

    def endpoints(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """指宽两端的坐标，用于在画面上画一条"量出来的宽度"线。"""
        half = self.width_px / 2.0
        nx, ny = self.normal
        cx, cy = self.center
        return ((cx - nx * half, cy - ny * half), (cx + nx * half, cy + ny * half))


def scale_segment_px(
    source: str, landmarks_px: npt.NDArray[np.float64]
) -> Tuple[Tuple[float, float], Tuple[float, float], float]:
    """只用关键点的"表观尺寸"信号，返回 (端点a, 端点b, 像素长度)。

    同一套物理量（正比于 1/Z），完全不吃光照和肤色，而且这条线段可以直接画在画面上，
    方便确认"量的是哪一段、数值合不合理"。

    - ``hand_scale``：手腕(0) -> 中指根(9)。整只手靠近/远离时变化明显。
    - ``finger_length``：食指根(5) -> 食指尖(8) 的**投影长度**。
      俯视机位下"手指下压"主要是绕掌指关节转动、手腕几乎不动，
      此时 hand_scale 基本不变，而这条投影长度会明显缩短 -> 更适合下压动作。
    """
    if source == "finger_length":
        i, j = INDEX_MCP, INDEX_TIP
    else:
        i, j = WRIST, MIDDLE_MCP
    a = np.asarray(landmarks_px[i], dtype=float)
    b = np.asarray(landmarks_px[j], dtype=float)
    return (
        (float(a[0]), float(a[1])),
        (float(b[0]), float(b[1])),
        float(np.hypot(b[0] - a[0], b[1] - a[1])),
    )


def hand_scale_px(landmarks_px: npt.NDArray[np.float64]) -> float:
    """手腕(0) -> 中指根(9) 的像素距离（scale_segment_px 的便捷封装）。"""
    return scale_segment_px("hand_scale", landmarks_px)[2]


def skin_mask(image_bgr: Frame, settings: DepthPressSettings) -> npt.NDArray[np.uint8]:
    """YCrCb 肤色阈值掩膜。输入可以是整帧，也可以是裁剪后的小图。"""
    ycrcb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2YCrCb)
    lower = np.array(
        [settings.skin_y_min, settings.skin_cr_min, settings.skin_cb_min], dtype=np.uint8
    )
    upper = np.array([255, settings.skin_cr_max, settings.skin_cb_max], dtype=np.uint8)
    mask = cv2.inRange(ycrcb, lower, upper)
    k = int(settings.morph_kernel)
    if k >= 3:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def _is_skin(mask: npt.NDArray[np.uint8], x: float, y: float) -> bool:
    # 用 +0.5 取整而不是 round()：round() 是银行家舍入（round(50.5) == 50），
    # 会让沿垂线的半像素采样左右不对称。
    xi = int(x + 0.5)
    yi = int(y + 0.5)
    h, w = mask.shape[:2]
    if xi < 0 or yi < 0 or xi >= w or yi >= h:
        return False
    return bool(mask[yi, xi])


def _find_skin_near(
    mask: npt.NDArray[np.uint8],
    center: npt.NDArray[np.float64],
    normal: npt.NDArray[np.float64],
    tolerance: float,
) -> Optional[npt.NDArray[np.float64]]:
    """关键点偶尔会落在手指边缘外一两像素，沿垂线找最近的皮肤点当中心。"""
    for k in range(1, max(1, int(tolerance)) + 1):
        for sign in (float(k), -float(k)):
            candidate = center + normal * sign
            if _is_skin(mask, candidate[0], candidate[1]):
                return candidate
    return None


def _extent(
    mask: npt.NDArray[np.uint8],
    center: npt.NDArray[np.float64],
    normal: npt.NDArray[np.float64],
    sign: float,
    half_len: float,
) -> Tuple[float, bool]:
    """从中心沿 normal*sign 往外走，返回 (走到多远的皮肤, 是否在搜索范围内碰到边界)。"""
    e = 0.0
    while e < half_len:
        q = center + normal * (sign * (e + _STEP_PX))
        if not _is_skin(mask, q[0], q[1]):
            break
        e += _STEP_PX
    return e, e < half_len


def measure_width_in_mask(
    mask: npt.NDArray[np.uint8],
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    settings: DepthPressSettings,
) -> Optional[FingerWidth]:
    """在掩膜里量 p1->p2 这段手指的宽度（坐标是掩膜自身坐标系）。

    沿指段取若干采样点，每点沿**垂直方向**双向走，直到遇到非皮肤像素：
      - 两侧都在搜索范围内碰到边界 -> 正常情况，宽度 = 左 + 右
      - 只有一侧碰到边界（另一侧连着隔壁手指/手臂）-> 用干净那一侧 × 2
      - 两侧都顶到搜索边界 -> 整片都是皮肤，判为无效（手指并拢或背景同色）
    最后对若干采样取中位数，抗单点噪声。
    """
    start = np.asarray(p1, dtype=float)
    end = np.asarray(p2, dtype=float)
    delta = end - start
    seg_len = float(np.hypot(delta[0], delta[1]))
    if seg_len < settings.min_segment_px:
        # 指段投影太短（手指朝向镜头/严重卷曲）时，垂线方向不可信
        return None

    normal = np.array([-delta[1] / seg_len, delta[0] / seg_len])
    half_len = float(settings.half_len_px)

    widths: list[float] = []
    candidates: list[Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], float]] = []

    n_samples = max(2, int(settings.samples))
    for t in np.linspace(0.2, 0.8, n_samples):
        center = start + t * delta
        if not _is_skin(mask, center[0], center[1]):
            found = _find_skin_near(mask, center, normal, settings.center_tol_px)
            if found is None:
                continue
            center = found

        plus, plus_bounded = _extent(mask, center, normal, 1.0, half_len)
        minus, minus_bounded = _extent(mask, center, normal, -1.0, half_len)

        if plus_bounded and minus_bounded:
            width = plus + minus
        elif plus_bounded:
            width = 2.0 * plus
        elif minus_bounded:
            width = 2.0 * minus
        else:
            continue

        widths.append(width)
        candidates.append((center, normal, width))

    if len(widths) < 2:
        return None

    median = float(np.median(widths))
    center, normal, _ = min(candidates, key=lambda item: abs(item[2] - median))
    return FingerWidth(
        width_px=median,
        center=(float(center[0]), float(center[1])),
        normal=(float(normal[0]), float(normal[1])),
        samples=len(widths),
    )


def measure_finger_width_px(
    frame_bgr: Frame,
    landmarks_px: npt.NDArray[np.float64],
    settings: DepthPressSettings,
) -> Optional[FingerWidth]:
    """在整帧上量 ``settings.finger_landmarks`` 这段手指的宽度。

    只在指段外扩一点点的 ROI 里做肤色分割：整帧做掩膜约 2.0ms，ROI 里约 0.1ms；
    剩下的约 0.9ms 是沿垂线逐点采样的 Python 循环（实测合计约 1.0ms/帧，
    30fps 下占 3%）。不想付这个代价就用 ``source: hand_scale``（约 0.0015ms）。
    """
    i, j = settings.finger_landmarks
    p1 = np.asarray(landmarks_px[i], dtype=float)
    p2 = np.asarray(landmarks_px[j], dtype=float)

    margin = float(settings.half_len_px) + 4.0
    frame_h, frame_w = frame_bgr.shape[:2]
    x0 = int(max(0, math.floor(min(p1[0], p2[0]) - margin)))
    y0 = int(max(0, math.floor(min(p1[1], p2[1]) - margin)))
    x1 = int(min(frame_w, math.ceil(max(p1[0], p2[0]) + margin)))
    y1 = int(min(frame_h, math.ceil(max(p1[1], p2[1]) + margin)))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None

    crop = frame_bgr[y0:y1, x0:x1]
    mask = skin_mask(crop, settings)
    measured = measure_width_in_mask(
        mask, (p1[0] - x0, p1[1] - y0), (p2[0] - x0, p2[1] - y0), settings
    )
    if measured is None:
        return None
    return FingerWidth(
        width_px=measured.width_px,
        center=(measured.center[0] + x0, measured.center[1] + y0),
        normal=measured.normal,
        samples=measured.samples,
    )
