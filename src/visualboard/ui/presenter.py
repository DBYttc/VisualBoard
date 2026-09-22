from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2

from visualboard.core.config_loader import UISettings
from visualboard.core.types import AppMode, Frame, HandResult, PointerState
from visualboard.ui.virtual_keyboard import VirtualKeyboard
from visualboard.vision.drawing import draw_hand_skeleton, draw_pointer_dot


@dataclass
class HudState:
    fps: float = 0.0
    mode: AppMode = "keyboard"
    hand_detected: bool = False
    emitter_error: Optional[str] = None


class Presenter:
    def __init__(self, settings: UISettings) -> None:
        self._settings = settings

    def render(
        self,
        frame: Frame,
        hand: HandResult,
        pointer: Optional[PointerState],
        keyboard: VirtualKeyboard,
        hud: HudState,
    ) -> Frame:
        show_skeleton = self._settings.show_skeleton and not self._settings.demo_mode
        if show_skeleton and hand.detected:
            draw_hand_skeleton(frame, hand)

        if pointer and pointer.valid:
            draw_pointer_dot(frame, pointer.index_px)

        if hud.mode == "keyboard":
            self._draw_keyboard(frame, keyboard)

        self._draw_hud(frame, hud, keyboard)
        return frame

    def _draw_keyboard(self, frame: Frame, keyboard: VirtualKeyboard) -> None:
        for btn in keyboard.buttons:
            if btn.is_pressed_flash:
                fill = (80, 180, 255)
            elif btn.is_hovered:
                fill = (60, 120, 220)
            else:
                fill = (50, 50, 50)
            x1, y1, x2, y2 = btn.rect()
            cv2.rectangle(frame, (x1, y1), (x2, y2), fill, -1)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (200, 200, 200), 1)
            label = btn.label
            if str(btn.key_id) == "key_caps" and keyboard.caps_on:
                label = "CAPS"
            scale = 0.45 if btn.is_special else 0.55
            tx = x1 + 8
            ty = y1 + btn.height // 2 + 6
            cv2.putText(
                frame,
                label,
                (tx, ty),
                cv2.FONT_HERSHEY_SIMPLEX,
                scale,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

    def _draw_hud(
        self, frame: Frame, hud: HudState, keyboard: VirtualKeyboard
    ) -> None:
        y = 28
        if self._settings.show_fps:
            cv2.putText(
                frame,
                f"FPS: {hud.fps:.1f}",
                (10, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )
            y += 28
        status = "Hand: OK" if hud.hand_detected else "Hand: -- (adjust light/distance)"
        cv2.putText(
            frame,
            status,
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255) if hud.hand_detected else (0, 140, 255),
            2,
        )
        y += 26
        cv2.putText(
            frame,
            f"Mode: {hud.mode} | Caps: {'ON' if keyboard.caps_on else 'off'}",
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
        )
        y += 24
        cv2.putText(
            frame,
            "Pinch on key to type | Q quit R reset M mode",
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (200, 200, 200),
            1,
        )
        if hud.emitter_error:
            cv2.putText(
                frame,
                hud.emitter_error[:60],
                (10, frame.shape[0] - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 0, 255),
                2,
            )
