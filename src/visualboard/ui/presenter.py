from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2

from visualboard.core.config_loader import UISettings
from visualboard.core.types import AppMode, Frame, HandResult, Point2D, PointerState
from visualboard.ui.virtual_keyboard import VirtualKeyboard
from visualboard.vision.drawing import (
    draw_hand_skeleton,
    draw_measure_line,
    draw_pointer_dot,
)


@dataclass
class HudState:
    fps: float = 0.0
    mode: AppMode = "keyboard"
    hand_detected: bool = False
    emitter_error: Optional[str] = None
    depth_text: Optional[str] = None
    depth_line: Optional[Tuple[Point2D, Point2D]] = None
    depth_lines: List[Tuple[Point2D, Point2D]] = field(default_factory=list)


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
            if pointer.fingers:
                for finger in pointer.fingers:
                    draw_pointer_dot(frame, finger.tip_px)
            else:
                draw_pointer_dot(frame, pointer.index_px)

        lines = hud.depth_lines
        if not lines and hud.depth_line is not None:
            lines = [hud.depth_line]
        for line in lines:
            draw_measure_line(frame, line[0], line[1])

        if hud.mode == "keyboard":
            self._draw_keyboard(frame, keyboard)

        self._draw_hud(frame, hud, keyboard)
        return frame

    def _fill_for(self, btn, keyboard: VirtualKeyboard):
        """键面颜色。亮色 = 正在按键/悬停/Shift、Caps 已激活。"""
        kid = str(btn.key_id)
        if btn.is_pressed_flash:
            return (90, 190, 255)
        if btn.is_hovered:
            return (70, 130, 235)
        if keyboard.shift_armed and kid in ("key_shift_l", "key_shift_r"):
            return (0, 150, 90)
        if keyboard.caps_on and kid == "key_caps":
            return (0, 150, 90)
        return (50, 50, 50)

    def _draw_keyboard(self, frame: Frame, keyboard: VirtualKeyboard) -> None:
        alpha = min(1.0, max(0.0, float(self._settings.keyboard_opacity)))

        # 1) 键面先画到一层拷贝上，再按透明度整体混合 ——
        #    alpha=0.5 时键面半透明，能看清压在下面的手和桌面。
        target = frame if alpha >= 1.0 else frame.copy()
        for btn in keyboard.buttons:
            x1, y1, x2, y2 = btn.rect()
            cv2.rectangle(target, (x1, y1), (x2, y2), self._fill_for(btn, keyboard), -1)
        if target is not frame:
            cv2.addWeighted(target, alpha, frame, 1.0 - alpha, 0.0, frame)

        # 2) 边框和文字画在混合之后：不受透明度影响，始终清晰。
        for btn in keyboard.buttons:
            x1, y1, x2, y2 = btn.rect()
            cv2.rectangle(frame, (x1, y1), (x2, y2), (210, 210, 210), 1)

            label = btn.label
            kid = str(btn.key_id)
            if kid == "key_caps" and keyboard.caps_on:
                label = "CAPS"
            elif kid in ("key_shift_l", "key_shift_r") and keyboard.shift_armed:
                label = "SHIFT*"

            # 字号随键高自适应（键盘铺满画面后键变大了，字也要跟着变大）
            scale = max(0.45, min(1.15, btn.height / 95.0)) * (0.8 if btn.is_special else 1.0)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
            tx = x1 + max(4, (btn.width - tw) // 2)  # 居中，宽键上比左对齐好认
            ty = y1 + (btn.height + th) // 2
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
            "Press finger on key to type | Q quit R reset M mode",
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (200, 200, 200),
            1,
        )
        if hud.depth_text:
            y += 22
            cv2.putText(
                frame,
                hud.depth_text,
                (10, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 200, 0),
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
