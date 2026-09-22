from __future__ import annotations

from visualboard.core.types import AppMode


class ModeController:
    def __init__(self, initial: AppMode = "keyboard") -> None:
        self._mode: AppMode = initial

    @property
    def mode(self) -> AppMode:
        return self._mode

    def toggle(self) -> AppMode:
        self._mode = "mouse" if self._mode == "keyboard" else "keyboard"
        return self._mode

    def set(self, mode: AppMode) -> None:
        self._mode = mode
