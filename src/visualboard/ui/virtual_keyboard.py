"""虚拟键盘：按真实 ANSI 键盘的"单位宽"网格布局，并自动铺满画面宽度。

布局规则（和真实键盘一致）：
    每行都是 15 个字母键宽（1u），系统键占多个单位：
        数字行  : ` 1..0 - = (13u) + Bksp(2u)
        字母行1 : Tab(1.5u) + Q..P(10u) + [ ](2u) + \\(1.5u)
        字母行2 : Caps(1.75u) + A..L(9u) + ; '(2u) + Enter(2.25u)
        字母行3 : Shift(2.25u) + Z..M(7u) + , . /(3u) + Shift(2.75u)
        底行    : Space(15u)

尺寸不是写死的：单位宽由 ``ui.canvas_width``（默认=摄像头宽度）反推，
所以键盘横向正好铺满画面；纵向贴着画面底部，键是正方形（可调 key_aspect）。
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from visualboard.core.config_loader import UISettings
from visualboard.core.types import KeyId, Point2D
from visualboard.ui.button import Button

UNIT_COLUMNS = 15.0

# (标签, 动作, 占几个单位, 是否特殊键)
_LAYOUT: List[List[Tuple[str, str, float, bool]]] = [
    [
        ("`", "`", 1.0, False),
        ("1", "1", 1.0, False),
        ("2", "2", 1.0, False),
        ("3", "3", 1.0, False),
        ("4", "4", 1.0, False),
        ("5", "5", 1.0, False),
        ("6", "6", 1.0, False),
        ("7", "7", 1.0, False),
        ("8", "8", 1.0, False),
        ("9", "9", 1.0, False),
        ("0", "0", 1.0, False),
        ("-", "-", 1.0, False),
        ("=", "=", 1.0, False),
        ("Bksp", "backspace", 2.0, True),
    ],
    [
        ("Tab", "tab", 1.5, True),
        ("Q", "q", 1.0, False),
        ("W", "w", 1.0, False),
        ("E", "e", 1.0, False),
        ("R", "r", 1.0, False),
        ("T", "t", 1.0, False),
        ("Y", "y", 1.0, False),
        ("U", "u", 1.0, False),
        ("I", "i", 1.0, False),
        ("O", "o", 1.0, False),
        ("P", "p", 1.0, False),
        ("[", "[", 1.0, False),
        ("]", "]", 1.0, False),
        ("\\", "\\", 1.5, False),
    ],
    [
        ("Caps", "caps", 1.75, True),
        ("A", "a", 1.0, False),
        ("S", "s", 1.0, False),
        ("D", "d", 1.0, False),
        ("F", "f", 1.0, False),
        ("G", "g", 1.0, False),
        ("H", "h", 1.0, False),
        ("J", "j", 1.0, False),
        ("K", "k", 1.0, False),
        ("L", "l", 1.0, False),
        (";", ";", 1.0, False),
        ("'", "'", 1.0, False),
        ("Enter", "enter", 2.25, True),
    ],
    [
        ("Shift", "shift_l", 2.25, True),
        ("Z", "z", 1.0, False),
        ("X", "x", 1.0, False),
        ("C", "c", 1.0, False),
        ("V", "v", 1.0, False),
        ("B", "b", 1.0, False),
        ("N", "n", 1.0, False),
        ("M", "m", 1.0, False),
        (",", ",", 1.0, False),
        (".", ".", 1.0, False),
        ("/", "/", 1.0, False),
        ("Shift", "shift_r", 2.75, True),
    ],
    [
        ("Space", "space", 15.0, True),
    ],
]

# Shift 按下的那一刻生效的字符（和真实键盘一致）
_SHIFT_MAP = {
    "`": "~",
    "1": "!",
    "2": "@",
    "3": "#",
    "4": "$",
    "5": "%",
    "6": "^",
    "7": "&",
    "8": "*",
    "9": "(",
    "0": ")",
    "-": "_",
    "=": "+",
    "[": "{",
    "]": "}",
    "\\": "|",
    ";": ":",
    "'": '"',
    ",": "<",
    ".": ">",
    "/": "?",
}

_SHIFT_ACTIONS = ("shift_l", "shift_r")


class VirtualKeyboard:
    def __init__(self, settings: UISettings) -> None:
        self._settings = settings
        self._buttons: List[Button] = []
        self._by_id: Dict[KeyId, Button] = {}
        self._char_map: Dict[KeyId, str] = {}
        self._caps_on = False
        self._shift_armed = False
        self._flash_until: Dict[KeyId, float] = {}
        self._top = 0.0
        self._bottom = 0.0
        self._build_layout()

    # ------------------------------------------------------------- 几何/状态

    @property
    def caps_on(self) -> bool:
        return self._caps_on

    @property
    def shift_armed(self) -> bool:
        return self._shift_armed

    @property
    def buttons(self) -> List[Button]:
        return self._buttons

    @property
    def top(self) -> float:
        """键盘最上沿的 y（HUD/缓冲提示可以据此避开键盘）。"""
        return self._top

    @property
    def bottom(self) -> float:
        return self._bottom

    def _key_id(self, action: str) -> KeyId:
        return KeyId(f"key_{action}")

    def _build_layout(self) -> None:
        s = self._settings
        margin = max(0, s.keyboard_margin)
        gap = max(0, s.key_gap)
        avail = max(1.0, float(s.canvas_width) - 2.0 * margin)

        # pitch = 一个单位宽（含它右侧的间隙）；键宽 = span*pitch - gap
        pitch = (avail + gap) / UNIT_COLUMNS
        key_h = max(1, int(round(pitch * s.key_aspect - gap)))
        total_h = len(_LAYOUT) * key_h + (len(_LAYOUT) - 1) * s.row_gap
        top = max(0.0, float(s.canvas_height) - s.keyboard_bottom - total_h)
        self._top = top
        self._bottom = top + total_h

        y = int(round(top))
        for row in _LAYOUT:
            cursor = float(margin)
            for label, action, span, special in row:
                kid = self._key_id(action)
                if kid in self._by_id:
                    raise ValueError(f"duplicate key id in layout: {kid}")

                x0 = int(round(cursor))
                cursor_next = cursor + span * pitch
                x1 = int(round(cursor_next)) - gap

                btn = Button(
                    key_id=kid,
                    label=label,
                    x=x0,
                    y=y,
                    width=max(1, x1 - x0),
                    height=key_h,
                    is_special=special,
                )
                self._buttons.append(btn)
                self._by_id[kid] = btn
                self._char_map[kid] = action
                cursor = cursor_next
            y += key_h + s.row_gap

    # ----------------------------------------------------------------- 交互

    def reset(self) -> None:
        self._caps_on = False
        self._shift_armed = False
        self.clear_hover()
        self._flash_until.clear()

    def clear_hover(self) -> None:
        for btn in self._buttons:
            btn.is_hovered = False

    def update_hover(self, point: Point2D) -> Optional[KeyId]:
        self.clear_hover()
        # 倒序遍历：后画的键（底行 Space）在重叠时优先
        for btn in reversed(self._buttons):
            if btn.contains(point.x, point.y):
                btn.is_hovered = True
                return btn.key_id
        return None

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
        """键位 -> 要输出的字符。返回 None 表示这个键只改状态（Shift / Caps）。"""
        action = self._char_map.get(key_id)
        if action is None:
            return None

        if action in _SHIFT_ACTIONS:
            self._shift_armed = not self._shift_armed
            return None
        if action == "caps":
            self._caps_on = not self._caps_on
            return None

        shifted = self._shift_armed
        self._shift_armed = False  # Shift 只作用于下一个键（像真实键盘点一下那样）

        if action == "backspace":
            return "\b"
        if action == "enter":
            return "\n"
        if action == "tab":
            return "\t"
        if action == "space":
            return " "

        if len(action) == 1 and action.isalpha():
            return action.upper() if (self._caps_on ^ shifted) else action
        if shifted and action in _SHIFT_MAP:
            return _SHIFT_MAP[action]
        return action

    def get_button(self, key_id: KeyId) -> Optional[Button]:
        return self._by_id.get(key_id)
