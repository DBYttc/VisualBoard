from __future__ import annotations

from visualboard.core.types import KeyId, Point2D
from visualboard.ui.virtual_keyboard import VirtualKeyboard


def test_hit_test_finds_letter_key(ui_settings):
    kb = VirtualKeyboard(ui_settings)
    btn = next(b for b in kb.buttons if b.key_id == KeyId("key_a"))
    cx = btn.x + btn.width / 2
    cy = btn.y + btn.height / 2
    assert kb.hit_test(cx, cy) == KeyId("key_a")


def test_hover_exclusive(ui_settings):
    kb = VirtualKeyboard(ui_settings)
    btn = next(b for b in kb.buttons if b.key_id == KeyId("key_q"))
    cx = btn.x + btn.width / 2
    cy = btn.y + btn.height / 2
    hover = kb.update_hover(Point2D(cx, cy))
    assert hover == KeyId("key_q")
    hovered = [b for b in kb.buttons if b.is_hovered]
    assert len(hovered) == 1


def test_caps_toggle_and_resolve(ui_settings):
    kb = VirtualKeyboard(ui_settings)
    assert kb.resolve_output(KeyId("key_caps")) is None
    assert kb.caps_on is True
    assert kb.resolve_output(KeyId("key_a")) == "A"
    assert kb.resolve_output(KeyId("key_a")) == "A"
    kb.resolve_output(KeyId("key_caps"))
    assert kb.caps_on is False
    assert kb.resolve_output(KeyId("key_a")) == "a"
