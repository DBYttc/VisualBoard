"""虚拟键盘布局（真实键盘结构、铺满画面宽度、Shift/Tab）与 50% 半透明绘制。"""

from __future__ import annotations

import cv2
import numpy as np

from visualboard.core.config_loader import UISettings
from visualboard.core.types import HandResult, KeyId, Point2D
from visualboard.ui.presenter import HudState, Presenter
from visualboard.ui.virtual_keyboard import UNIT_COLUMNS, VirtualKeyboard


def _ui(**over) -> UISettings:
    values = dict(
        canvas_width=1280,
        canvas_height=720,
        keyboard_margin=0,
        keyboard_bottom=20,
        key_gap=6,
        row_gap=8,
        key_aspect=1.0,
        keyboard_opacity=0.5,
        show_skeleton=False,
        show_fps=False,
        demo_mode=False,
    )
    values.update(over)
    return UISettings(**values)


def _rows(kb: VirtualKeyboard) -> dict[int, list]:
    rows: dict[int, list] = {}
    for btn in kb.buttons:
        rows.setdefault(btn.y, []).append(btn)
    return rows


# ------------------------------------------------------------------ 布局


def test_keyboard_spans_the_whole_canvas_width():
    kb = VirtualKeyboard(_ui(canvas_width=1280))
    left = min(b.x for b in kb.buttons)
    right = max(b.x + b.width for b in kb.buttons)

    assert left == 0
    assert abs(right - 1280) <= 1  # 横向铺满，边界对齐


def test_every_row_covers_the_same_total_width():
    """真实键盘每行都是 15u，所以每行右边界应该一致。"""
    kb = VirtualKeyboard(_ui())
    rows = _rows(kb)
    assert len(rows) == 5
    for y, buttons in rows.items():
        right = max(b.x + b.width for b in buttons)
        assert abs(right - 1280) <= 1, f"row y={y} ends at {right}"


def test_keys_are_square_and_much_bigger_than_before():
    kb = VirtualKeyboard(_ui())
    letter = kb.get_button(KeyId("key_a"))
    assert letter is not None
    # 15u 铺满 1280：单位宽 ~85px，键宽 ~80px（原来是 52px）
    assert 75 <= letter.width <= 90
    assert abs(letter.height - letter.width) <= 1
    # 比旧布局（52px）明显大
    assert letter.width > 70


def test_geometry_follows_canvas_width():
    narrow = VirtualKeyboard(_ui(canvas_width=640))
    wide = VirtualKeyboard(_ui(canvas_width=1920))

    a_narrow = narrow.get_button(KeyId("key_a"))
    a_wide = wide.get_button(KeyId("key_a"))
    assert a_narrow is not None and a_wide is not None
    assert a_wide.width > a_narrow.width * 2.5


def test_keyboard_sits_at_the_bottom_of_the_canvas():
    kb = VirtualKeyboard(_ui(canvas_height=720, keyboard_bottom=20))
    assert abs(kb.bottom - (720 - 20)) <= 1
    assert kb.top > 100  # 上方留给 HUD 和手


def test_key_ids_are_unique():
    kb = VirtualKeyboard(_ui())
    ids = [b.key_id for b in kb.buttons]
    assert len(ids) == len(set(ids))
    # 真实键盘的键都在
    for name in ("key_a", "key_z", "key_0", "key_backspace", "key_enter",
                 "key_space", "key_caps", "key_tab", "key_shift_l", "key_shift_r",
                 "key_-", "key_=", "key_[", "key_]", "key_\\", "key_;", "key_'",
                 "key_,", "key_.", "key_/"):
        assert kb.get_button(KeyId(name)) is not None, name


def test_bottom_row_is_one_full_width_space():
    kb = VirtualKeyboard(_ui())
    rows = _rows(kb)
    bottom_y = max(rows)
    bottom = rows[bottom_y]
    assert len(bottom) == 1
    assert bottom[0].key_id == KeyId("key_space")
    assert abs(bottom[0].width - 1280) <= 1


def test_unit_columns_constant_is_ansi():
    assert UNIT_COLUMNS == 15.0


# -------------------------------------------------------------- 键位输出


def test_shift_is_sticky_for_one_key():
    kb = VirtualKeyboard(_ui())
    assert kb.resolve_output(KeyId("key_shift_l")) is None
    assert kb.shift_armed is True
    assert kb.resolve_output(KeyId("key_a")) == "A"
    assert kb.shift_armed is False  # 只作用于下一个键
    assert kb.resolve_output(KeyId("key_a")) == "a"


def test_shift_produces_shifted_symbols():
    kb = VirtualKeyboard(_ui())
    kb.resolve_output(KeyId("key_shift_r"))
    assert kb.resolve_output(KeyId("key_1")) == "!"
    kb.resolve_output(KeyId("key_shift_l"))
    assert kb.resolve_output(KeyId("key_/")) == "?"
    kb.resolve_output(KeyId("key_shift_l"))
    assert kb.resolve_output(KeyId("key_[")) == "{"


def test_caps_and_shift_combine_like_a_real_keyboard():
    kb = VirtualKeyboard(_ui())
    kb.resolve_output(KeyId("key_caps"))
    assert kb.caps_on is True
    assert kb.resolve_output(KeyId("key_a")) == "A"
    kb.resolve_output(KeyId("key_shift_l"))
    assert kb.resolve_output(KeyId("key_a")) == "a"  # Caps + Shift = 小写
    kb.resolve_output(KeyId("key_caps"))  # Caps 关掉
    assert kb.caps_on is False
    kb.resolve_output(KeyId("key_shift_l"))
    assert kb.resolve_output(KeyId("key_a")) == "A"


def test_tab_and_specials():
    kb = VirtualKeyboard(_ui())
    assert kb.resolve_output(KeyId("key_tab")) == "\t"
    assert kb.resolve_output(KeyId("key_space")) == " "
    assert kb.resolve_output(KeyId("key_enter")) == "\n"
    assert kb.resolve_output(KeyId("key_backspace")) == "\b"
    assert kb.resolve_output(KeyId("key_0")) == "0"
    assert kb.resolve_output(KeyId("key_-")) == "-"


def test_reset_clears_shift():
    kb = VirtualKeyboard(_ui())
    kb.resolve_output(KeyId("key_shift_l"))
    kb.reset()
    assert kb.shift_armed is False


def test_hover_works_on_the_new_layout():
    kb = VirtualKeyboard(_ui())
    btn = kb.get_button(KeyId("key_k"))
    assert btn is not None
    hovered = kb.update_hover(Point2D(btn.x + btn.width / 2, btn.y + btn.height / 2))
    assert hovered == KeyId("key_k")


# ------------------------------------------------------- 50% 半透明绘制


def test_keyboard_is_drawn_at_50_percent_opacity():
    """键面像素应该是 背景 与 键面底色 各占一半（50% 半透明）。"""
    kb = VirtualKeyboard(_ui(keyboard_opacity=0.5))
    presenter = Presenter(_ui(keyboard_opacity=0.5))

    background = np.full((720, 1280, 3), 200, dtype=np.uint8)
    frame = background.copy()
    presenter.render(
        frame,
        HandResult(detected=False),
        None,
        kb,
        HudState(mode="keyboard"),
    )

    btn = kb.get_button(KeyId("key_a"))
    assert btn is not None
    # 取键面内部、避开居中的文字和边框
    px = int(frame[btn.y + 4, btn.x + 4][0])

    fill = 50  # 普通键底色 (50,50,50)
    expected = 0.5 * fill + 0.5 * 200
    assert abs(px - expected) <= 3, f"expected ~{expected}, got {px}"


def test_full_opacity_paints_the_key_solid():
    kb = VirtualKeyboard(_ui(keyboard_opacity=1.0))
    presenter = Presenter(_ui(keyboard_opacity=1.0))
    frame = np.full((720, 1280, 3), 200, dtype=np.uint8)

    presenter.render(frame, HandResult(detected=False), None, kb, HudState(mode="keyboard"))

    btn = kb.get_button(KeyId("key_a"))
    assert btn is not None
    assert int(frame[btn.y + 4, btn.x + 4][0]) == 50


def test_hovered_key_is_brighter_than_normal_key():
    kb = VirtualKeyboard(_ui())
    presenter = Presenter(_ui())
    frame = np.full((720, 1280, 3), 200, dtype=np.uint8)

    kb.update_hover(
        Point2D(
            kb.get_button(KeyId("key_a")).x + 5,
            kb.get_button(KeyId("key_a")).y + 5,
        )
    )
    presenter.render(frame, HandResult(detected=False), None, kb, HudState(mode="keyboard"))

    hovered = kb.get_button(KeyId("key_a"))
    normal = kb.get_button(KeyId("key_s"))
    assert hovered is not None and normal is not None
    # 悬停键的红色分量更高（底色 (70,130,235) vs (50,50,50)）
    assert int(frame[hovered.y + 4, hovered.x + 4][2]) > int(frame[normal.y + 4, normal.x + 4][2])


def test_keyboard_mode_off_does_not_draw_keys():
    kb = VirtualKeyboard(_ui())
    presenter = Presenter(_ui())
    frame = np.full((720, 1280, 3), 200, dtype=np.uint8)

    presenter.render(frame, HandResult(detected=False), None, kb, HudState(mode="mouse"))

    btn = kb.get_button(KeyId("key_a"))
    assert btn is not None
    assert int(frame[btn.y + 4, btn.x + 4][0]) == 200  # 完全没画
