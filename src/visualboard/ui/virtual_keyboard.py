from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from visualboard.core.config_loader import UISettings
from visualboard.core.types import KeyId, Point2D
from visualboard.ui.button import Button

# Rows: label on key, output char (lower), key_id suffix
_LAYOUT_ROWS: List[List[Tuple[str, str, bool]]] = [
    [
        ("1", "1", False),
        ("2", "2", False),
        ("3", "3", False),
        ("4", "4", False),
        ("5", "5", False),
        ("6", "6", False),
        ("7", "7", False),
        ("8", "8", False),
        ("9", "9", False),
        ("0", "0", False),
    ],
    [
        ("Q", "q", False),
        ("W", "w", False),
        ("E", "e", False),
        ("R", "r", False),
        ("T", "t", False),
        ("Y", "y", False),
        ("U", "u", False),
        ("I", "i", False),
        ("O", "o", False),
        ("P", "p", False),
    ],
    [
        ("A", "a", False),
        ("S", "s", False),
        ("D", "d", False),
        ("F", "f", False),
        ("G", "g", False),
        ("H", "h", False),
        ("J", "j", False),
        ("K", "k", False),
        ("L", "l", False),
    ],
    [
        ("Caps", "caps", True),
        ("Z", "z", False),
        ("X", "x", False),
        ("C", "c", False),
        ("V", "v", False),
        ("B", "b", False),
        ("N", "n", False),
        ("M", "m", False),
        ("Bksp", "backspace", True),
    ],
]

_BOTTOM_ROW: List[Tuple[str, str, int]] = [
    ("Space", "space", 4),
    ("Enter", "enter", 1),
]


class VirtualKeyboard:
    def __init__(self, settings: UISettings) -> None:
        self._settings = settings
        self._buttons: List[Button] = []
        self._by_id: Dict[KeyId, Button] = {}
        self._char_map: Dict[KeyId, str] = {}
        self._caps_on = False
        self._flash_until: Dict[KeyId, float] = {}
        self._build_layout()

    @property
    def caps_on(self) -> bool:
        return self._caps_on

    @property
    def buttons(self) -> List[Button]:
        return self._buttons

    def _key_id(self, suffix: str) -> KeyId:
        return KeyId(f"key_{suffix}")

    def _build_layout(self) -> None:
        ox, oy = self._settings.keyboard_origin
        kw = self._settings.key_width
        kh = self._settings.key_height
        kg = self._settings.key_gap
        rg = self._settings.row_gap

        y = oy
        for row in _LAYOUT_ROWS:
            x = ox
            for label, out, special in row:
                kid = self._key_id(out)
                btn = Button(
                    key_id=kid,
                    label=label,
                    x=x,
                    y=y,
                    width=kw,
                    height=kh,
                    is_special=special,
                )
                self._buttons.append(btn)
                self._by_id[kid] = btn
                self._char_map[kid] = out
                x += kw + kg
            y += kh + rg

        x = ox
        unit = kw + kg
        for label, out, span in _BOTTOM_ROW:
            kid = self._key_id(out)
            width = span * kw + (span - 1) * kg
            btn = Button(
                key_id=kid,
                label=label,
                x=x,
                y=y,
                width=width,
                height=kh,
                is_special=True,
            )
            self._buttons.append(btn)
            self._by_id[kid] = btn
            self._char_map[kid] = out
            x += width + kg

    def reset(self) -> None:
        self._caps_on = False
        self.clear_hover()
        self._flash_until.clear()

    def clear_hover(self) -> None:
        for btn in self._buttons:
            btn.is_hovered = False

    def update_hover(self, point: Point2D) -> Optional[KeyId]:
        self.clear_hover()
        # Top-most: iterate reversed so later buttons (e.g. bottom row) win if overlap
        hovered: Optional[KeyId] = None
        for btn in reversed(self._buttons):
            if btn.contains(point.x, point.y):
                btn.is_hovered = True
                hovered = btn.key_id
                break
        return hovered

    def hit_test(self, px: float, py: float) -> Optional[KeyId]:
        for btn in reversed(self._buttons):
            if btn.contains(px, py):
                return btn.key_id
        return None

    def flash_pressed(self, key_id: KeyId, duration: float = 0.15) -> None:
        self._flash_until[key_id] = time.monotonic() + duration

    def tick_flash(self, now: float) -> None:
        expired = [k for k, t in self._flash_until.items() if t <= now]
        for k in expired:
            del self._flash_until[k]
        for btn in self._buttons:
            btn.is_pressed_flash = btn.key_id in self._flash_until

    def resolve_output(self, key_id: KeyId) -> Optional[str]:
        action = self._char_map.get(key_id)
        if action is None:
            return None
        if action == "caps":
            self._caps_on = not self._caps_on
            return None
        if action == "backspace":
            return "\b"
        if action == "enter":
            return "\n"
        if action == "space":
            return " "
        if len(action) == 1 and action.isalpha():
            return action.upper() if self._caps_on else action
        return action

    def get_button(self, key_id: KeyId) -> Optional[Button]:
        return self._by_id.get(key_id)
