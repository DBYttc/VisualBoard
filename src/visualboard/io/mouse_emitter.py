from __future__ import annotations

import logging
from typing import Optional

from pynput.mouse import Button, Controller

from visualboard.core.types import Point2D, PointerState

logger = logging.getLogger(__name__)


class MouseEmitter:
    def __init__(self, move_enabled: bool = True) -> None:
        self._controller = Controller()
        self._move_enabled = move_enabled
        self._was_pinching = False
        self.last_error: Optional[str] = None

    def reset(self) -> None:
        self._was_pinching = False

    def update(self, pointer: PointerState, pinch_threshold: float) -> None:
        self.last_error = None
        if not pointer.valid:
            self._was_pinching = False
            return
        try:
            if self._move_enabled:
                self._controller.position = (
                    int(pointer.index_px.x),
                    int(pointer.index_px.y),
                )
            pinching = pointer.pinch_distance_px < pinch_threshold
            if pinching and not self._was_pinching:
                self._controller.press(Button.left)
                self._controller.release(Button.left)
            self._was_pinching = pinching
        except Exception as exc:
            msg = f"mouse pynput error: {exc}"
            logger.exception(msg)
            self.last_error = msg

    def move_to(self, point: Point2D) -> None:
        if not self._move_enabled:
            return
        self._controller.position = (int(point.x), int(point.y))
