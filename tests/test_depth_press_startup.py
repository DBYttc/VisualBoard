"""startup 基准模式（启动后 5 秒标定 + 冻结基准）与 press_edge 触发模式。

对应用户要的行为：
    启动 -> 5 秒摆姿势（期间绝不触发）-> 以那一刻的尺寸为基准
    -> x 相对基准变化超过 0.2 判定为一次输入
    -> 按住不放不会连发，回到基准附近才重新武装
"""

from __future__ import annotations

from visualboard.core.config_loader import DepthPressSettings, InteractionSettings
from visualboard.core.types import KeyId, Point2D, PointerState
from visualboard.interaction.depth_press import DepthPressDetector
from visualboard.interaction.trigger_engine import TriggerEngine

KEY_A = KeyId("key_a")
KEY_B = KeyId("key_b")


def _ds(**over) -> DepthPressSettings:
    values = dict(
        enabled=True,
        source="finger_length",
        direction="near",
        baseline_mode="startup",
        warmup_sec=5.0,
        enter_ratio=1.20,
        exit_ratio=1.10,
        stable_frames=1,
        baseline_samples=10,
        min_samples=5,
        latch_key=True,
    )
    values.update(over)
    return DepthPressSettings(**values)


def _inter(**over) -> InteractionSettings:
    values = dict(
        pinch_threshold_px=40.0,
        cooldown_sec=0.4,
        hover_sec=0.5,
        trigger_mode="pinch",
        pinch_fire_on="press_edge",
        pinch_stable_frames=2,
        pinch_source="depth",
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


def _calibrate(det: DepthPressDetector, value: float = 100.0, until: float = 5.1) -> float:
    """跑过 warmup 窗口，返回结束时间。"""
    t = 0.0
    while t < until:
        det.update(value, t)
        t = round(t + 0.1, 3)
    return t


# ------------------------------------------------------------- startup 模式


def test_warmup_blocks_and_then_freezes_baseline():
    det = DepthPressDetector(_ds())

    t = 0.0
    for _ in range(40):  # 4.0 秒：摆姿势
        assert det.update(100.0, t) is False
        t = round(t + 0.1, 3)

    assert det.warming_up is True
    assert det.baseline() is None  # 标定期内还没有基准（不能退回滚动中位数）
    remaining = det.warmup_remaining()
    assert remaining is not None and 0.0 < remaining <= 1.1 + 1e-6

    # 标定期内即使表观尺寸翻倍也不触发，且仍处于标定态
    assert det.update(200.0, t) is False
    assert det.warming_up is True
    t = round(t + 0.1, 3)

    # 继续摆到 5 秒之后：冻结基准（200 那一帧已被挤出 10 帧窗口，中位数仍是 100）
    while t < 5.2:
        assert det.update(100.0, t) is False
        t = round(t + 0.1, 3)

    assert det.warming_up is False
    base = det.baseline()
    assert base is not None and abs(base - 100.0) < 1e-6


def test_threshold_is_two_tenths_of_change():
    det = DepthPressDetector(_ds())
    _calibrate(det)

    assert det.update(119.0, 6.0) is False  # 变化 19% < 20%
    assert det.update(120.5, 6.1) is True  # 变化 20.5% -> 按下
    assert det.update(105.0, 6.2) is False  # 回到 5% -> 松开


def test_far_direction_reacts_to_shrinking_size():
    det = DepthPressDetector(_ds(direction="far"))
    _calibrate(det)

    assert det.update(120.0, 6.0) is False  # 变大不是 far 方向的"按下"
    assert det.update(83.0, 6.1) is True  # 100/83 = 1.205 -> 按下


def test_ratio_and_signal_are_reported_against_frozen_baseline():
    det = DepthPressDetector(_ds())
    _calibrate(det)
    det.update(120.0, 6.0)
    assert det.ratio() is not None and abs(det.ratio() - 1.2) < 1e-9
    # direction=near 时 signal == ratio
    assert det.signal() is not None and abs(det.signal() - 1.2) < 1e-9


def test_reset_restarts_calibration():
    det = DepthPressDetector(_ds())
    _calibrate(det)
    assert det.warming_up is False

    det.reset()
    assert det.warming_up is True
    assert det.baseline() is None
    assert det.update(200.0, 100.0) is False  # 重新进入标定期，不触发


def test_rolling_mode_keeps_working_after_new_options():
    """baseline_mode 默认还是 rolling，行为与以前一致（有回归测试守着）。"""
    det = DepthPressDetector(_ds(baseline_mode="rolling", enter_ratio=1.12, stable_frames=2))
    for _ in range(10):
        det.update(100.0)
    assert det.update(112.0) is False
    assert det.update(112.0) is True


# ----------------------------------------------------------- press_edge 模式


def test_press_edge_fires_once_per_press():
    engine = TriggerEngine(_inter(), _ds())
    events = []
    for i in range(10):  # 压住不放 10 帧
        events += engine.update(_ptr(100.0), KEY_A, i * 0.03, True)

    assert len(events) == 1
    assert events[0].key_id == KEY_A
    assert events[0].source == "depth"

    engine.update(_ptr(100.0), KEY_A, 0.5, False)  # 松开
    for i in range(10):  # 再压一次
        events += engine.update(_ptr(100.0), KEY_A, 0.6 + i * 0.03, True)
    assert len(events) == 2


def test_press_edge_hold_and_sweep_do_not_refire():
    engine = TriggerEngine(_inter(), _ds())

    events = engine.update(_ptr(100.0), KEY_A, 0.0, True)  # PINCHING
    events += engine.update(_ptr(100.0), KEY_A, 0.05, True)  # 出字 -> FIRED
    assert len(events) == 1

    # 手指还压着，滑到隔壁键 / 滑出键盘区 / 再滑回来：都不该再出字
    assert not engine.update(_ptr(100.0), KEY_B, 0.1, True)
    assert not engine.update(_ptr(100.0), None, 0.2, True)
    assert not engine.update(_ptr(100.0), KEY_A, 0.3, True)

    # 松手后才重新武装
    engine.update(_ptr(100.0), KEY_A, 0.5, False)
    again = engine.update(_ptr(100.0), KEY_A, 0.6, True)
    again += engine.update(_ptr(100.0), KEY_A, 0.65, True)
    assert len(again) == 1


def test_press_edge_still_respects_cooldown():
    engine = TriggerEngine(_inter(cooldown_sec=1.0), _ds())
    events = engine.update(_ptr(100.0), KEY_A, 0.0, True)
    events += engine.update(_ptr(100.0), KEY_A, 0.01, True)  # 出字
    assert len(events) == 1

    engine.update(_ptr(100.0), KEY_A, 0.2, False)  # 松手
    events += engine.update(_ptr(100.0), KEY_A, 0.3, True)  # 0.3s < 冷却 1.0s
    events += engine.update(_ptr(100.0), KEY_A, 0.31, True)
    assert len(events) == 1  # 被冷却压掉

    engine.update(_ptr(100.0), KEY_A, 1.5, False)
    events += engine.update(_ptr(100.0), KEY_A, 1.6, True)
    events += engine.update(_ptr(100.0), KEY_A, 1.61, True)
    assert len(events) == 2  # 冷却过去后正常出字
