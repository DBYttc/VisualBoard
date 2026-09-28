from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2

from visualboard.capture.opencv_camera import OpenCVCamera
from visualboard.core.clock import SystemClock
from visualboard.core.config_loader import Settings
from visualboard.core.types import Frame, HandResult, Point2D, PointerState
from visualboard.interaction.depth_press import DepthPressDetector
from visualboard.interaction.modes import ModeController
from visualboard.interaction.pointer_state import PointerStateTracker
from visualboard.interaction.trigger_engine import TriggerEngine
from visualboard.io.keyboard_emitter import KeyboardEmitter
from visualboard.io.mouse_emitter import MouseEmitter
from visualboard.ui.presenter import HudState, Presenter
from visualboard.ui.virtual_keyboard import VirtualKeyboard
from visualboard.vision.finger_width import (
    FingerWidth,
    measure_finger_width_px,
    scale_segment_px,
)
from visualboard.vision.hand_tracker import HandTracker

logger = logging.getLogger(__name__)


@dataclass
class FpsCounter:
    _last_time: float = field(default_factory=time.monotonic)
    _frames: int = 0
    fps: float = 0.0

    def tick(self) -> float:
        self._frames += 1
        now = time.monotonic()
        dt = now - self._last_time
        if dt >= 0.5:
            self.fps = self._frames / dt
            self._frames = 0
            self._last_time = now
        return self.fps


class MainLoop:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._clock = SystemClock()
        self._camera = OpenCVCamera(settings.camera)
        self._tracker = HandTracker(settings.mediapipe)
        self._pointer_tracker = PointerStateTracker(settings.smoothing)
        self._keyboard = VirtualKeyboard(settings.ui)
        self._depth_settings = settings.depth_press
        self._trigger = TriggerEngine(settings.interaction, self._depth_settings)
        self._depth = DepthPressDetector(self._depth_settings)
        self._depth_info: Optional[FingerWidth] = None
        self._depth_line_pts: Optional[tuple[Point2D, Point2D]] = None
        self._emitter = KeyboardEmitter(self._keyboard)
        self._mouse = MouseEmitter(settings.mouse.move_enabled)
        self._modes = ModeController(settings.mode.default)
        self._presenter = Presenter(settings.ui)
        self._fps = FpsCounter()
        self._window = settings.demo.window_name
        self._typed_buffer = ""

    def _reset_all(self) -> None:
        self._trigger.reset()
        self._keyboard.reset()
        self._pointer_tracker.reset()
        self._mouse.reset()
        self._depth.reset()
        self._typed_buffer = ""

    def _read_depth_press(self, frame: Frame, hand: HandResult, now: float) -> bool:
        """量"手指表观尺寸"，判断是靠近还是远离摄像头 —— 作为按下信号。

        关闭（depth_press.enabled=false）时直接返回 False，不产生任何额外计算。
        """
        if not self._depth_settings.enabled or hand.landmarks_px is None:
            self._depth_info = None
            self._depth_line_pts = None
            return False

        if self._depth_settings.source == "mask":
            measured = measure_finger_width_px(
                frame, hand.landmarks_px, self._depth_settings
            )
            self._depth_info = measured
            if measured is None:
                self._depth_line_pts = None
                signal: Optional[float] = None
            else:
                a, b = measured.endpoints()
                self._depth_line_pts = (Point2D(a[0], a[1]), Point2D(b[0], b[1]))
                signal = measured.width_px
        else:
            # 只用关键点的信号（hand_scale / finger_length）：把被测量的那段画出来
            self._depth_info = None
            a, b, length = scale_segment_px(self._depth_settings.source, hand.landmarks_px)
            self._depth_line_pts = (Point2D(a[0], a[1]), Point2D(b[0], b[1]))
            signal = length

        return self._depth.update(signal, now)

    def _depth_text(self) -> Optional[str]:
        if not self._depth_settings.enabled:
            return None

        if self._depth.warming_up:
            remaining = self._depth.warmup_remaining()
            if remaining is not None:
                return (
                    f"depth({self._depth_settings.source}): CALIBRATING "
                    f"{remaining:.1f}s - hold your hand still"
                )

        signal = self._depth.signal()
        if signal is not None:
            state = "PRESS" if self._depth.active else "idle"
            base = self._depth.baseline()
            base_text = f" base={base:.1f}px" if base is not None else ""
            return (
                f"depth({self._depth_settings.source}): x{signal:.3f}{base_text} {state}"
            )
        if self._depth_info is None and self._depth_settings.source == "mask":
            return "depth(mask): no measurement - mask failed? try source: finger_length"
        return f"depth({self._depth_settings.source}): collecting baseline..."

    def _depth_line(self) -> Optional[tuple[Point2D, Point2D]]:
        if not self._depth_settings.enabled:
            return None
        return self._depth_line_pts

    def _append_buffer(self, char: Optional[str]) -> None:
        if char is None:
            return
        if char == "\b":
            self._typed_buffer = self._typed_buffer[:-1]
        elif char == "\n":
            self._typed_buffer += "\\n"
        else:
            self._typed_buffer += char
        if len(self._typed_buffer) > 48:
            self._typed_buffer = self._typed_buffer[-48:]

    def run(self) -> None:
        logger.info("Starting main loop. Click target app, then type with pinch.")
        cv2.namedWindow(self._window, cv2.WINDOW_NORMAL)

        pointer: Optional[PointerState] = None

        try:
            while True:
                frame = self._camera.read()
                if frame is None:
                    continue

                hand = self._tracker.process(frame)
                now = self._clock.monotonic()

                if hand.detected:
                    pointer = self._pointer_tracker.update(hand)
                    depth_pressed = self._read_depth_press(frame, hand, now)
                    if self._modes.mode == "keyboard":
                        hover_id = self._keyboard.update_hover(pointer.index_px)
                        for event in self._trigger.update(
                            pointer, hover_id, now, depth_pressed
                        ):
                            char = self._emitter.emit_and_get_char(event)
                            self._keyboard.flash_pressed(event.key_id)
                            self._append_buffer(char)
                    else:
                        self._keyboard.clear_hover()
                        self._mouse.update(
                            pointer, self._settings.interaction.pinch_threshold_px
                        )
                else:
                    pointer = None
                    self._depth.reset()
                    self._depth_info = None
                    self._keyboard.clear_hover()

                self._keyboard.tick_flash(now)

                hud = HudState(
                    fps=self._fps.tick(),
                    mode=self._modes.mode,
                    hand_detected=hand.detected,
                    emitter_error=self._emitter.last_error or self._mouse.last_error,
                    depth_text=self._depth_text(),
                    depth_line=self._depth_line(),
                )
                self._presenter.render(frame, hand, pointer, self._keyboard, hud)
                if self._typed_buffer and self._modes.mode == "keyboard":
                    cv2.putText(
                        frame,
                        f"Buf: {self._typed_buffer}",
                        (10, frame.shape[0] - 50),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (180, 255, 180),
                        1,
                    )
                cv2.imshow(self._window, frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("r"):
                    self._reset_all()
                if key == ord("m"):
                    self._modes.toggle()
                    self._trigger.reset()
                    self._mouse.reset()
                    logger.info("Mode -> %s", self._modes.mode)

        finally:
            self._tracker.close()
            self._camera.release()
            cv2.destroyAllWindows()
