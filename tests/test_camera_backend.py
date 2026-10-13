"""摄像头后端选择与采集分辨率模式。

不碰真实硬件，用假的 VideoCapture 记录"试了哪些后端、设了哪些参数"，
并检查 native 模式下帧会被缩放到工作分辨率（这样键盘布局和像素阈值才一致）。
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from visualboard.capture.opencv_camera import OpenCVCamera
from visualboard.core.config_loader import CameraSettings


class FakeCap:
    def __init__(
        self,
        opened: bool = True,
        size: tuple[int, int] = (1280, 720),
        report: tuple[int, int] | None = None,
        honour_set: bool = True,
    ) -> None:
        self._opened = opened
        self._size = size  # read() 实际交付的尺寸
        self._report = size if report is None else report  # get() 报出来的尺寸
        self._honour_set = honour_set
        self.sets: list[tuple[int, int]] = []

    def isOpened(self) -> bool:
        return self._opened

    def getBackendName(self) -> str:
        return "FAKE"

    def set(self, prop: int, value: int) -> bool:
        self.sets.append((prop, value))
        if not self._honour_set:
            return True
        w, h = self._report
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            self._report = (int(value), h)
        elif prop == cv2.CAP_PROP_FRAME_HEIGHT:
            self._report = (w, int(value))
        return True

    def get(self, prop: int) -> float:
        w, h = self._report
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return float(w)
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(h)
        return 0.0

    def read(self):
        w, h = self._size
        return True, np.zeros((h, w, 3), dtype=np.uint8)

    def release(self) -> None:
        self._opened = False


def _settings(**over) -> CameraSettings:
    values = dict(
        device_index=0,
        width=1280,
        height=720,
        mirror=True,
        backend="auto",
        capture="force",
    )
    values.update(over)
    return CameraSettings(**values)


# --------------------------------------------------------------- 后端选择


def test_auto_prefers_dshow(monkeypatch):
    calls: list[tuple[int, int]] = []

    def fake_capture(index, api):
        calls.append((index, api))
        return FakeCap()

    monkeypatch.setattr(cv2, "VideoCapture", fake_capture)
    OpenCVCamera(_settings())

    # DSHOW 一次就成功，不该再去试系统默认后端（那一下要 8 秒以上）
    assert calls == [(0, cv2.CAP_DSHOW)]


def test_auto_falls_back_when_dshow_fails(monkeypatch):
    calls: list[tuple[int, int]] = []

    def fake_capture(index, api):
        calls.append((index, api))
        return FakeCap(opened=(api != cv2.CAP_DSHOW))

    monkeypatch.setattr(cv2, "VideoCapture", fake_capture)
    OpenCVCamera(_settings())

    assert [api for _, api in calls] == [cv2.CAP_DSHOW, cv2.CAP_ANY]


def test_msmf_backend_is_forced(monkeypatch):
    calls: list[tuple[int, int]] = []

    def fake_capture(index, api):
        calls.append((index, api))
        return FakeCap()

    monkeypatch.setattr(cv2, "VideoCapture", fake_capture)
    OpenCVCamera(_settings(backend="msmf"))

    assert calls == [(0, cv2.CAP_MSMF)]


def test_all_backends_failing_raises_clear_error(monkeypatch):
    monkeypatch.setattr(cv2, "VideoCapture", lambda _i, _a: FakeCap(opened=False))

    with pytest.raises(RuntimeError) as excinfo:
        OpenCVCamera(_settings(backend="dshow"))

    assert "device_index=0" in str(excinfo.value)


# ----------------------------------------------------------- 分辨率模式


def test_force_mode_requests_working_resolution(monkeypatch):
    cap = FakeCap(size=(1280, 720))
    monkeypatch.setattr(cv2, "VideoCapture", lambda _i, _a: cap)

    camera = OpenCVCamera(_settings(capture="force"))

    assert (cv2.CAP_PROP_FRAME_WIDTH, 1280) in cap.sets
    assert (cv2.CAP_PROP_FRAME_HEIGHT, 720) in cap.sets
    assert camera.read().shape[:2] == (720, 1280)


def test_native_mode_skips_renegotiation_and_scales_uniformly(monkeypatch):
    """native 模式：不调用 set()（省掉驱动切换分辨率的 2~3 秒），read() 里**等比**放大。

    4:3 的 640x480 只按宽度压到 1280 -> 高度是 960 而不是 720；
    强行拉到 1280x720 会让画面横向变形（手看起来会变扁）。
    """
    cap = FakeCap(size=(640, 480))
    monkeypatch.setattr(cv2, "VideoCapture", lambda _i, _a: cap)

    camera = OpenCVCamera(_settings(capture="native"))
    frame = camera.read()

    assert cap.sets == []  # 关键：一次 set 都没有
    assert camera.output_size == (1280, 960)
    assert frame.shape[:2] == (960, 1280)
    assert abs(1280 / 960 - 640 / 480) < 0.01  # 长宽比原样保留


def test_output_size_matches_working_resolution_when_camera_agrees(monkeypatch):
    cap = FakeCap(size=(1280, 720))
    monkeypatch.setattr(cv2, "VideoCapture", lambda _i, _a: cap)

    camera = OpenCVCamera(_settings(capture="force"))

    assert camera.output_size == (1280, 720)  # 16:9 摄像头 -> 不产生缩放


def test_silent_resolution_fallback_keeps_aspect(monkeypatch):
    """摄像头不理会 set()、仍然交 640x480 时，等比缩放到 1280x960，不能压扁。"""
    cap = FakeCap(size=(640, 480), honour_set=False)
    monkeypatch.setattr(cv2, "VideoCapture", lambda _i, _a: cap)

    camera = OpenCVCamera(_settings(capture="force"))

    assert camera.output_size == (1280, 960)
    assert frame_shape(camera.read()) == (960, 1280)


def test_force_mode_can_request_a_different_capture_size(monkeypatch):
    """capture_width/height 只影响"向摄像头请求什么"，工作坐标系仍是 width x height。"""
    cap = FakeCap(size=(960, 540))
    monkeypatch.setattr(cv2, "VideoCapture", lambda _i, _a: cap)

    camera = OpenCVCamera(
        _settings(capture="force", capture_width=1024, capture_height=576)
    )

    assert (cv2.CAP_PROP_FRAME_WIDTH, 1024) in cap.sets
    assert (cv2.CAP_PROP_FRAME_HEIGHT, 576) in cap.sets
    assert camera.read().shape[:2] == (720, 1280)


def frame_shape(frame) -> tuple[int, int]:
    return (frame.shape[0], frame.shape[1])
