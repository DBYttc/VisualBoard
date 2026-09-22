from __future__ import annotations

from unittest.mock import MagicMock

from visualboard.core.types import KeyId
from visualboard.interaction.events import KeyTriggerEvent
from visualboard.io.keyboard_emitter import KeyboardEmitter
from visualboard.ui.virtual_keyboard import VirtualKeyboard


def test_emit_types_character(ui_settings):
    kb = VirtualKeyboard(ui_settings)
    emitter = KeyboardEmitter(kb)
    emitter._controller = MagicMock()

    char = emitter.emit_and_get_char(
        KeyTriggerEvent(key_id=KeyId("key_h"), source="pinch", timestamp=0.0)
    )
    assert char == "h"
    emitter._controller.type.assert_called_once_with("h")


def test_emit_backspace(ui_settings):
    kb = VirtualKeyboard(ui_settings)
    emitter = KeyboardEmitter(kb)
    emitter._controller = MagicMock()

    char = emitter.emit_and_get_char(
        KeyTriggerEvent(key_id=KeyId("key_backspace"), source="pinch", timestamp=0.0)
    )
    assert char == "\b"
    assert emitter._controller.press.called
