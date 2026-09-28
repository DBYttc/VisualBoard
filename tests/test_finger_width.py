from __future__ import annotations

import cv2
import numpy as np

from visualboard.core.config_loader import DepthPressSettings
from visualboard.vision.finger_width import (
    hand_scale_px,
    measure_finger_width_px,
    measure_width_in_mask,
    scale_segment_px,
    skin_mask,
)


def _ds(**over) -> DepthPressSettings:
    values = dict(
        enabled=True,
        source="mask",
        direction="far",
        half_len_px=18.0,
        samples=5,
        center_tol_px=3.0,
        min_segment_px=8.0,
        morph_kernel=0,  # 单测里不做形态学，避免核把 10px 的假手指削掉
    )
    values.update(over)
    return DepthPressSettings(**values)


def _bar_mask(x0: int = 45, x1: int = 55) -> np.ndarray:
    """100x120 的掩膜，中间一条竖直"手指"（宽 x1-x0）。"""
    mask = np.zeros((120, 100), dtype=np.uint8)
    mask[30:90, x0:x1] = 255
    return mask


def _skin_bgr() -> tuple[int, int, int]:
    """造一个确定落在 YCrCb 肤色范围内的 BGR 颜色（Y=150, Cr=150, Cb=110）。"""
    bgr = cv2.cvtColor(np.uint8([[[150, 150, 110]]]), cv2.COLOR_YCrCb2BGR)[0, 0]
    return int(bgr[0]), int(bgr[1]), int(bgr[2])


# ------------------------------------------------------------------ 掩膜


def test_skin_mask_accepts_skin_color_and_rejects_gray():
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    image[:, :] = _skin_bgr()
    assert int(skin_mask(image, _ds()).max()) == 255

    gray = np.full((10, 10, 3), 128, dtype=np.uint8)  # Cr=Cb=128，超出 Cb 上限
    assert int(skin_mask(gray, _ds()).max()) == 0


# ------------------------------------------------------------ 宽度测量


def test_measure_width_of_vertical_bar():
    result = measure_width_in_mask(_bar_mask(), (50.0, 35.0), (50.0, 85.0), _ds())
    assert result is not None
    assert 8.5 <= result.width_px <= 11.5
    assert result.samples >= 2
    # 垂线方向应该是水平的（指段竖直）
    assert abs(result.normal[1]) < 1e-6


def test_merged_neighbour_falls_back_to_clean_side():
    """右侧与隔壁手指连成一整块时，用干净那一侧 × 2。"""
    result = measure_width_in_mask(_bar_mask(x0=45, x1=85), (50.0, 35.0), (50.0, 85.0), _ds())
    assert result is not None
    assert 9.0 <= result.width_px <= 13.0


def test_no_skin_returns_none():
    empty = np.zeros((120, 100), dtype=np.uint8)
    assert measure_width_in_mask(empty, (50.0, 35.0), (50.0, 85.0), _ds()) is None


def test_all_skin_is_rejected():
    """整片都是皮肤（手指并拢 / 背景同色）时不该给出宽度。"""
    solid = np.full((120, 100), 255, dtype=np.uint8)
    assert measure_width_in_mask(solid, (50.0, 35.0), (50.0, 85.0), _ds()) is None


def test_short_segment_is_rejected():
    assert measure_width_in_mask(_bar_mask(), (50.0, 50.0), (50.0, 54.0), _ds()) is None


def test_measure_finger_width_px_handles_roi_offset():
    """整帧入口：ROI 裁剪后坐标要能正确换算回整帧坐标。"""
    frame = np.zeros((160, 160, 3), dtype=np.uint8)
    cv2.rectangle(frame, (105, 30), (115, 130), _skin_bgr(), -1)

    landmarks = np.zeros((21, 2), dtype=np.float64)
    landmarks[6] = (110.0, 50.0)
    landmarks[7] = (110.0, 110.0)

    result = measure_finger_width_px(frame, landmarks, _ds(morph_kernel=5))
    assert result is not None
    assert 8.0 <= result.width_px <= 13.0
    assert abs(result.center[0] - 110.0) <= 2.5
    assert 50.0 <= result.center[1] <= 110.0


def test_hand_scale_px():
    landmarks = np.zeros((21, 2), dtype=np.float64)
    landmarks[0] = (0.0, 0.0)
    landmarks[9] = (30.0, 40.0)
    assert abs(hand_scale_px(landmarks) - 50.0) < 1e-6


def test_scale_segment_px_picks_the_right_landmarks():
    landmarks = np.zeros((21, 2), dtype=np.float64)
    landmarks[0] = (0.0, 0.0)
    landmarks[9] = (30.0, 40.0)  # hand_scale -> 50
    landmarks[5] = (100.0, 100.0)
    landmarks[8] = (100.0, 130.0)  # finger_length -> 30

    a, b, length = scale_segment_px("hand_scale", landmarks)
    assert (a, b) == ((0.0, 0.0), (30.0, 40.0))
    assert abs(length - 50.0) < 1e-6

    a, b, length = scale_segment_px("finger_length", landmarks)
    assert (a, b) == ((100.0, 100.0), (100.0, 130.0))
    assert abs(length - 30.0) < 1e-6
