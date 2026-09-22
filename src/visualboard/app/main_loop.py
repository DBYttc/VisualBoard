from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2

from visualboard.capture.opencv_camera import OpenCVCamera
from visualboard.core.clock import SystemClock
from visualboard.core.config_loader import Settings
from visualboard.core.types import PointerState
from visualboard.interaction.modes import ModeController
from visualboard.interaction.pointer_state import PointerStateTracker
from visualboard.interaction.trigger_engine import TriggerEngine
from visualboard.io.keyboard_emitter import KeyboardEmitter
from visualboard.io.mouse_emitter import MouseEmitter
from visualboard.ui.presenter import HudState, Presenter
from visualboard.ui.virtual_keyboard import VirtualKeyboard
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
        self._trigger = TriggerEngine(settings.interaction)
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
        self._typed_buffer = ""

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
                    if self._modes.mode == "keyboard":
                        hover_id = self._keyboard.update_hover(pointer.index_px)
                        for event in self._trigger.update(pointer, hover_id, now):
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
                    self._keyboard.clear_hover()

                self._keyboard.tick_flash(now)

                hud = HudState(
                    fps=self._fps.tick(),
                    mode=self._modes.mode,
                    hand_detected=hand.detected,
                    emitter_error=self._emitter.last_error or self._mouse.last_error,
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
