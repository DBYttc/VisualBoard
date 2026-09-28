"""MainLoop 接线测试：用假摄像头/假追踪器跑完整帧循环，不接触真实硬件。

覆盖此前完全没有测试的编排层（app/main_loop.py）：
    合成帧 -> PointerStateTracker -> DepthPressDetector -> TriggerEngine -> KeyboardEmitter
以及 Presenter 的绘制路径（深度按压的测量线 + HUD 文字）。
"""

from __future__ import annotations

import dataclasses

import cv2
import numpy as np
import pytest

import visualboard.app.main_loop as ml
from visualboard.app.main_loop import MainLoop
from visualboard.core.config_loader import DepthPressSettings, Settings, load_settings
from visualboard.core.types import HandResult, KeyId

KEY_CENTER = (46.0, 306.0)  # key_1 中心 = keyboard_origin(20,280) + 半键宽


def _synth_finger(width_px: int):
    """中间一条肤色竖条（宽度可变）；关键点 6/7 用来量宽，8 落在 key_1 上。"""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    center_x = 320
    x0 = center_x - width_px // 2
    x1 = center_x + width_px // 2
    skin = cv2.cvtColor(np.uint8([[[150, 150, 110]]]), cv2.COLOR_YCrCb2BGR)[0, 0]
    cv2.rectangle(frame, (x0, 120), (x1, 360), (int(skin[0]), int(skin[1]), int(skin[2])), -1)

    landmarks = np.zeros((21, 2), dtype=np.float64)
    landmarks[6] = (float(center_x), 150.0)
    landmarks[7] = (float(center_x), 330.0)
    landmarks[8] = KEY_CENTER  # 食指指尖 -> key_1
    landmarks[4] = (200.0, 306.0)  # 拇指很远 -> 不构成接触捏合
    return frame, landmarks


def _synth_hand(scale: float, source: str):
    """把某条"表观尺寸线段"按 scale 缩放，模拟手指靠近/远离摄像头。"""
    frame, landmarks = _synth_finger(40)
    landmarks = landmarks.copy()
    if source == "finger_length":
        # 指根到指尖的投影长度 = 100 * scale
        landmarks[5] = (KEY_CENTER[0], KEY_CENTER[1] - 100.0 * scale)
    elif source == "hand_scale":
        landmarks[0] = (KEY_CENTER[0], KEY_CENTER[1] + 100.0 * scale)
        landmarks[9] = KEY_CENTER
    return frame, landmarks


def _settings(
    *,
    source: str = "mask",
    direction: str = "near",
    enabled: bool = True,
    pinch_source: str = "depth",
) -> Settings:
    settings = load_settings()
    return dataclasses.replace(
        settings,
        interaction=dataclasses.replace(
            settings.interaction,
            pinch_source=pinch_source,
            pinch_fire_on="stable_frames",
            pinch_stable_frames=2,
            cooldown_sec=0.05,
            trigger_mode="pinch",
        ),
        depth_press=DepthPressSettings(
            enabled=enabled,
            source=source,
            direction=direction,
            enter_ratio=1.12,
            exit_ratio=1.06,
            stable_frames=3,
            baseline_samples=30,
            min_samples=5,
            latch_key=True,
            half_len_px=40.0,
            morph_kernel=5,
        ),
        ui=dataclasses.replace(settings.ui, show_skeleton=False, show_fps=False),
    )


def _run_loop(monkeypatch, frames, settings) -> tuple[list[KeyId], int]:
    shared = {"i": 0}
    emitted: list[KeyId] = []

    class FakeCamera:
        def __init__(self, _settings):
            pass

        def read(self):
            return frames[min(shared["i"], len(frames) - 1)][0].copy()

        def release(self):
            pass

    class FakeTracker:
        def __init__(self, _settings):
            pass

        def process(self, _frame):
            i = min(shared["i"], len(frames) - 1)
            shared["i"] += 1
            return HandResult(detected=True, landmarks_px=frames[i][1])

        def close(self):
            pass

    class FakeEmitter:
        def __init__(self, _keyboard):
            self.last_error = None

        def emit_and_get_char(self, event):
            emitted.append(event.key_id)
            return "1"

    monkeypatch.setattr(ml, "OpenCVCamera", FakeCamera)
    monkeypatch.setattr(ml, "HandTracker", FakeTracker)
    monkeypatch.setattr(ml, "KeyboardEmitter", FakeEmitter)

    # 不开窗口、不读键盘：帧数跑完后让 waitKey 返回 q 结束循环
    monkeypatch.setattr(ml.cv2, "namedWindow", lambda *a, **k: None)
    monkeypatch.setattr(ml.cv2, "imshow", lambda *a, **k: None)
    monkeypatch.setattr(ml.cv2, "destroyAllWindows", lambda *a, **k: None)
    ticks = {"n": 0}

    def fake_wait_key(_delay=0):
        ticks["n"] += 1
        return ord("q") if ticks["n"] > len(frames) else 0xFF

    monkeypatch.setattr(ml.cv2, "waitKey", fake_wait_key)

    MainLoop(settings).run()
    return emitted, ticks["n"]


def test_mask_source_fires_depth_press(monkeypatch):
    """mask 源：合成手指从 40px "变宽"到 46px（= 离摄像头更近）-> 触发 key_1。"""
    frames = [_synth_finger(w) for w in [40] * 12 + [46] * 20 + [40] * 10]
    emitted, iterations = _run_loop(monkeypatch, frames, _settings(source="mask"))

    assert emitted, "深度按压链路没有触发任何按键"
    assert emitted[0] == KeyId("key_1")
    assert iterations > 20  # 基线阶段确实跑过了


@pytest.mark.parametrize("source", ["hand_scale", "finger_length"])
def test_landmark_sources_fire_depth_press(monkeypatch, source):
    """只吃关键点的两条信号都能走通全链路（不吃光照/肤色）。"""
    frames = [_synth_hand(s, source) for s in [1.0] * 12 + [1.2] * 20]
    emitted, _ = _run_loop(monkeypatch, frames, _settings(source=source))

    assert emitted, f"{source} 信号没有触发按键"
    assert emitted[0] == KeyId("key_1")


def test_depth_disabled_does_not_fire(monkeypatch):
    """默认配置（enabled=False + pinch_source=contact）下，链路完全不参与。"""
    frames = [_synth_finger(w) for w in [40] * 12 + [60] * 20]
    emitted, _ = _run_loop(
        monkeypatch,
        frames,
        _settings(source="mask", enabled=False, pinch_source="contact"),
    )

    # 手指"变宽"只是画面变化，拇指-食指并未接触（154px > 45px 阈值）
    assert not emitted


def test_mask_failure_is_reported_and_does_not_fire(monkeypatch):
    """掩膜量不出宽度时（这里给纯灰画面）不应该触发，也不该抛异常。"""
    frames = []
    for _ in range(30):
        frame = np.full((480, 640, 3), 90, dtype=np.uint8)  # 灰画面，无肤色
        _, landmarks = _synth_finger(40)
        frames.append((frame, landmarks))

    emitted, _ = _run_loop(monkeypatch, frames, _settings(source="mask"))
    assert not emitted


def test_startup_mode_calibrates_then_fires(monkeypatch):
    """startup 基准模式：前几帧用来冻结基准，之后变化 20% 才出字。"""
    frames = [_synth_hand(s, "finger_length") for s in [1.0] * 12 + [1.25] * 20]
    settings = _settings(source="finger_length")
    settings = dataclasses.replace(
        settings,
        depth_press=dataclasses.replace(
            settings.depth_press,
            baseline_mode="startup",
            warmup_sec=0.0,  # 单测里不等真实 5 秒
            enter_ratio=1.20,
            exit_ratio=1.10,
            stable_frames=1,
            min_samples=5,
        ),
    )

    emitted, _ = _run_loop(monkeypatch, frames, settings)
    assert emitted, "startup 模式下没有触发按键"
    assert emitted[0] == KeyId("key_1")
