from __future__ import annotations

import logging
import time
import dataclasses
from dataclasses import dataclass, field
from typing import Dict, Optional

import cv2

from visualboard.capture.opencv_camera import OpenCVCamera
from visualboard.core.clock import SystemClock
from visualboard.core.config_loader import Settings
from visualboard.core.types import Frame, HandResult, KeyId, Point2D, PointerState
from visualboard.interaction.depth_press import DepthPressDetector
from visualboard.interaction.modes import ModeController
from visualboard.interaction.multi_finger_depth import MultiFingerDepthPress
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

        # 画布尺寸跟着摄像头的**实际输出**走：4:3 摄像头在 width=1280 时输出 1280x960，
        # 若还按配置的 720 高布局，键盘就会浮在画面中间。等比缩放保证画面不被压扁。
        ui = settings.ui
        out_w, out_h = self._camera.output_size
        if (out_w, out_h) != (ui.canvas_width, ui.canvas_height):
            logger.info("UI canvas follows camera output: %dx%d", out_w, out_h)
            ui = dataclasses.replace(ui, canvas_width=out_w, canvas_height=out_h)
        self._ui = ui

        self._keyboard = VirtualKeyboard(ui)
        self._depth_settings = settings.depth_press
        self._trigger = TriggerEngine(settings.interaction, self._depth_settings)
        self._depth = DepthPressDetector(self._depth_settings)
        self._multi_depth = MultiFingerDepthPress(self._depth_settings)
        self._depth_info: Optional[FingerWidth] = None
        self._depth_line_pts: Optional[tuple[Point2D, Point2D]] = None
        self._emitter = KeyboardEmitter(self._keyboard)
        self._mouse = MouseEmitter(settings.mouse.move_enabled)
        self._modes = ModeController(settings.mode.default)
        self._presenter = Presenter(ui)
        self._fps = FpsCounter()
        self._window = settings.demo.window_name
        self._typed_buffer = ""

    def _use_multi_finger_depth(self) -> bool:
        return (
            self._depth_settings.enabled
            and self._depth_settings.source == "finger_length"
            and self._settings.interaction.pinch_source in ("depth", "both")
        )

    def _reset_all(self) -> None:
        self._trigger.reset()
        self._keyboard.reset()
        self._pointer_tracker.reset()
        self._mouse.reset()
        self._depth.reset()
        self._multi_depth.reset()
        self._typed_buffer = ""

    def _read_depth_press(self, frame: Frame, hand: HandResult, now: float) -> bool:
        """单指表观尺寸路径（mask / hand_scale）。五指 finger_length 走 _multi_depth。"""
        if not self._depth_settings.enabled or hand.landmarks_px is None:
            self._depth_info = None
            self._depth_line_pts = None
            return False

        if self._depth_settings.source == "finger_length":
            # Multi-finger path owns measurement; keep single-channel idle.
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
            self._depth_info = None
            a, b, length = scale_segment_px(self._depth_settings.source, hand.landmarks_px)
            self._depth_line_pts = (Point2D(a[0], a[1]), Point2D(b[0], b[1]))
            signal = length

        return self._depth.update(signal, now)

    def _depth_text(self) -> Optional[str]:
        if not self._depth_settings.enabled:
            return None

        if self._use_multi_finger_depth():
            return self._multi_depth.hud_text()

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
        if not self._depth_settings.enabled or self._use_multi_finger_depth():
            return None
        return self._depth_line_pts

    def _depth_lines(self) -> list[tuple[Point2D, Point2D]]:
        if not self._use_multi_finger_depth():
            return []
        return self._multi_depth.measure_lines()

    def _append_buffer(self, char: Optional[str]) -> None:
        if char is None:
            return
        if char == "\b":
            self._typed_buffer = self._typed_buffer[:-1]
        elif char == "\n":
            self._typed_buffer += "\\n"
        elif char == "\t":
            self._typed_buffer += "\\t"
        else:
            self._typed_buffer += char
        if len(self._typed_buffer) > 48:
            self._typed_buffer = self._typed_buffer[-48:]

    def run(self) -> None:
        logger.info("Starting main loop. Click target app, then type with finger press.")
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
                    finger_keys: Optional[Dict[str, Optional[KeyId]]] = None
                    finger_pressed: Optional[Dict[str, bool]] = None
                    depth_pressed = False

                    if self._use_multi_finger_depth() and hand.landmarks_px is not None:
                        finger_pressed = self._multi_depth.update(hand.landmarks_px, now)
                    else:
                        depth_pressed = self._read_depth_press(frame, hand, now)

                    if self._modes.mode == "keyboard":
                        if self._use_multi_finger_depth() and pointer.fingers:
                            tips = {f.name: f.tip_px for f in pointer.fingers}
                            finger_keys = self._keyboard.update_hovers(tips)
                            hover_id = finger_keys.get("index")
                        else:
                            hover_id = self._keyboard.update_hover(pointer.index_px)

                        for event in self._trigger.update(
                            pointer,
                            hover_id,
                            now,
                            depth_pressed,
                            finger_keys=finger_keys,
                            finger_pressed=finger_pressed,
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
                    self._multi_depth.reset()
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
                    depth_lines=self._depth_lines(),
                )
                self._presenter.render(frame, hand, pointer, self._keyboard, hud)
                if self._typed_buffer and self._modes.mode == "keyboard":
                    # 画在键盘上沿之上，避免被半透明键盘压住看不清
                    buffer_y = max(20, int(self._keyboard.top) - 12)
                    cv2.putText(
                        frame,
                        f"Buf: {self._typed_buffer}",
                        (10, buffer_y),
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
