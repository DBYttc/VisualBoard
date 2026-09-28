from __future__ import annotations

import cv2
import numpy as np

from visualboard.core.config_loader import DepthPressSettings, InteractionSettings
from visualboard.core.types import KeyId, Point2D, PointerState
from visualboard.interaction.depth_press import DepthPressDetector
from visualboard.interaction.trigger_engine import TriggerEngine
from visualboard.vision.finger_width import measure_finger_width_px

BASE = 100.0
KEY_A = KeyId("key_a")
KEY_B = KeyId("key_b")


def _ds(**over) -> DepthPressSettings:
    values = dict(
        enabled=True,
        source="mask",
        direction="far",
        enter_ratio=1.12,
        exit_ratio=1.06,
        stable_frames=3,
        baseline_samples=30,
        min_samples=5,
        latch_key=True,
    )
    values.update(over)
    return DepthPressSettings(**values)


def _warm(det: DepthPressDetector, n: int = 10, value: float = BASE) -> None:
    for _ in range(n):
        det.update(value)


# ---------------------------------------------------------------- 检测器本身


def test_baseline_requires_min_samples():
    det = DepthPressDetector(_ds(min_samples=10))
    for _ in range(9):
        det.update(BASE)
    assert det.baseline() is None
    assert det.update(BASE) is False
    assert det.baseline() is not None


def test_far_direction_press_then_hysteresis_release():
    det = DepthPressDetector(_ds())
    _warm(det)

    assert det.update(85.0) is False  # 第 1 帧：确认中
    assert det.update(85.0) is False  # 第 2 帧
    assert det.update(85.0) is True  # 第 3 帧：stable_frames=3，按下

    # 只回到 92（还没进 exit_ratio=1.06 的中立区）-> 保持按下
    assert det.update(92.0) is True
    # 回到 98 -> ratio 0.98 -> signal 1.02 <= 1.06 -> 松开
    assert det.update(98.0) is False


def test_near_direction_press():
    det = DepthPressDetector(_ds(direction="near", stable_frames=2))
    _warm(det)
    assert det.update(115.0) is False
    assert det.update(115.0) is True


def test_missing_signal_keeps_level():
    det = DepthPressDetector(_ds(stable_frames=1))
    _warm(det)
    assert det.update(85.0) is True
    assert det.update(None) is True  # 手消失/分割失败：电平保持，不污染基线
    assert det.update(None) is True
    assert det.update(100.0) is False


def test_baseline_frozen_while_pressed():
    """一直按着不放时，基线不能被自己拉上去，否则 ratio 会回到 1.0 中途取消。"""
    det = DepthPressDetector(_ds(stable_frames=2))
    _warm(det)
    assert det.update(85.0) is False
    assert det.update(85.0) is True
    for _ in range(30):
        assert det.update(85.0) is True
    ratio = det.ratio()
    assert ratio is not None and ratio < 0.9


# ------------------------------------------------ 与 TriggerEngine 的接线


def _inter(**over) -> InteractionSettings:
    values = dict(
        pinch_threshold_px=40.0,
        cooldown_sec=0.4,
        hover_sec=0.5,
        trigger_mode="pinch",
        pinch_fire_on="release",
        pinch_stable_frames=3,
    )
    values.update(over)
    return InteractionSettings(**values)


def _ptr(dist: float = 100.0) -> PointerState:
    return PointerState(
        index_px=Point2D(100, 100),
        thumb_px=Point2D(100 + dist, 100),
        pinch_distance_px=dist,
        valid=True,
    )


def test_depth_channel_fires_without_any_pinch():
    engine = TriggerEngine(_inter(pinch_source="depth"), _ds())
    engine.update(_ptr(100.0), KEY_A, 0.0, True)  # 手指没捏合，只是离得近了
    events = engine.update(_ptr(100.0), KEY_A, 0.01, False)
    assert len(events) == 1
    assert events[0].key_id == KEY_A
    assert events[0].source == "depth"


def test_contact_source_ignores_depth_channel():
    """默认行为保持不变：pinch_source=contact 时深度信号完全不参与。"""
    engine = TriggerEngine(_inter(pinch_source="contact"), _ds())
    engine.update(_ptr(100.0), KEY_A, 0.0, True)
    assert not engine.update(_ptr(100.0), KEY_A, 0.01, False)


def test_both_source_accepts_either_channel():
    engine = TriggerEngine(_inter(pinch_source="both"), _ds())

    engine.update(_ptr(30.0), KEY_A, 0.0, False)  # 接触捏合
    events = engine.update(_ptr(100.0), KEY_A, 0.01, False)
    assert len(events) == 1 and events[0].source == "pinch"

    engine.update(_ptr(100.0), KEY_A, 1.0, True)  # 深度通道（已过冷却）
    events = engine.update(_ptr(100.0), KEY_A, 1.01, False)
    assert len(events) == 1 and events[0].source == "depth"


def test_depth_press_latches_key_during_parallax_drift():
    """下压时 hover 漂到隔壁键，锁键后仍然触发按下瞬间的那一个键。"""
    engine = TriggerEngine(_inter(pinch_source="depth"), _ds(latch_key=True))
    engine.update(_ptr(100.0), KEY_A, 0.0, True)
    engine.update(_ptr(100.0), KEY_B, 0.01, True)  # 视差导致的漂移
    events = engine.update(_ptr(100.0), KEY_B, 0.02, False)
    assert len(events) == 1 and events[0].key_id == KEY_A


def test_depth_press_without_latch_cancels_on_sweep():
    engine = TriggerEngine(_inter(pinch_source="depth"), _ds(latch_key=False))
    engine.update(_ptr(100.0), KEY_A, 0.0, True)
    engine.update(_ptr(100.0), KEY_B, 0.01, True)
    assert not engine.update(_ptr(100.0), KEY_B, 0.02, False)


# ------------------------------------------------------- 端到端（合成画面）


def _synth_finger(width_px: int) -> tuple[np.ndarray, np.ndarray]:
    """造一帧"手指"：中间一条肤色竖条，宽度可变 —— 模拟手指靠近/远离。"""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    center_x = 320
    x0 = center_x - width_px // 2
    x1 = center_x + width_px // 2
    skin = cv2.cvtColor(np.uint8([[[150, 150, 110]]]), cv2.COLOR_YCrCb2BGR)[0, 0]
    cv2.rectangle(frame, (x0, 120), (x1, 360), (int(skin[0]), int(skin[1]), int(skin[2])), -1)

    landmarks = np.zeros((21, 2), dtype=np.float64)
    landmarks[6] = (float(center_x), 150.0)
    landmarks[7] = (float(center_x), 330.0)
    return frame, landmarks


def test_end_to_end_measure_detect_trigger():
    """不接摄像头，走完整链路：肤色测量 -> 深度检测 -> 触发按键。"""
    settings = DepthPressSettings(
        enabled=True,
        source="mask",
        direction="near",  # 手指靠近（表观变宽）算按下
        enter_ratio=1.12,
        exit_ratio=1.06,
        stable_frames=3,
        baseline_samples=30,
        min_samples=5,
        latch_key=True,
        half_len_px=40.0,
        morph_kernel=5,
    )
    detector = DepthPressDetector(settings)
    engine = TriggerEngine(
        _inter(pinch_source="depth", pinch_fire_on="stable_frames", pinch_stable_frames=2),
        settings,
    )

    def step(width: int, t: float):
        frame, landmarks = _synth_finger(width)
        measured = measure_finger_width_px(frame, landmarks, settings)
        signal = measured.width_px if measured is not None else None
        return engine.update(_ptr(100.0), KEY_A, t, detector.update(signal))

    events = []
    for i in range(12):  # 基线：宽 40px，全程不该触发
        events += step(40, i * 0.03)
    assert not events

    for i in range(12, 20):  # 手指靠近到 46px（+15%）
        events += step(46, i * 0.03)

    assert len(events) == 1  # 冷却(0.4s)会压掉后面的重复触发
    assert events[0].key_id == KEY_A
    assert events[0].source == "depth"

