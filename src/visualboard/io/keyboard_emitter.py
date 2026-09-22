from __future__ import annotations

import logging
from typing import Optional

from pynput.keyboard import Controller, Key

from visualboard.core.types import KeyId
from visualboard.interaction.events import KeyTriggerEvent
from visualboard.ui.virtual_keyboard import VirtualKeyboard

logger = logging.getLogger(__name__)


class KeyboardEmitter:
    def __init__(self, keyboard: VirtualKeyboard) -> None:
        self._keyboard = keyboard
        self._controller = Controller()
        self.last_error: Optional[str] = None

    def emit_and_get_char(self, event: KeyTriggerEvent) -> Optional[str]:
        self.last_error = None
        try:
            output = self._keyboard.resolve_output(event.key_id)
            if output is None:
                return None
            if output == "\b":
                self._controller.press(Key.backspace)
                self._controller.release(Key.backspace)
            elif output == "\n":
                self._controller.press(Key.enter)
                self._controller.release(Key.enter)
            else:
                self._controller.type(output)
            logger.info("Emitted key=%s source=%s", event.key_id, event.source)
            return output
        except Exception as exc:
            msg = f"pynput error: {exc}"
            logger.exception(msg)
            self.last_error = msg
            return None

    def emit(self, event: KeyTriggerEvent) -> bool:
        self.emit_and_get_char(event)
        return self.last_error is None

    def type_key_id(self, key_id: KeyId) -> bool:
        result = self.emit_and_get_char(
            KeyTriggerEvent(key_id=key_id, source="pinch", timestamp=0.0)
        )
        return result is not None
