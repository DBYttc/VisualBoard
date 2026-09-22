from __future__ import annotations

import logging
from enum import Enum, auto
from typing import List, Optional

from visualboard.core.config_loader import InteractionSettings
from visualboard.core.types import KeyId, PointerState, TriggerSource
from visualboard.interaction.events import KeyTriggerEvent

logger = logging.getLogger(__name__)


class _PinchState(Enum):
    IDLE = auto()
    PINCHING = auto()


class TriggerEngine:
    def __init__(self, settings: InteractionSettings) -> None:
        self._settings = settings
        self._pinch_state = _PinchState.IDLE
        self._pinch_key: Optional[KeyId] = None
        self._last_fire_time = -1e9
        self._hover_key: Optional[KeyId] = None
        self._hover_start: Optional[float] = None
        self._stable_frames = 0

    def reset(self) -> None:
        self._pinch_state = _PinchState.IDLE
        self._pinch_key = None
        self._hover_key = None
        self._hover_start = None
        self._stable_frames = 0

    def _in_cooldown(self, now: float) -> bool:
        return (now - self._last_fire_time) < self._settings.cooldown_sec

    def _emit(
        self,
        key_id: KeyId,
        source: TriggerSource,
        now: float,
        events: List[KeyTriggerEvent],
    ) -> None:
        if self._in_cooldown(now):
            logger.debug("Trigger suppressed by cooldown key=%s", key_id)
            return
        events.append(
            KeyTriggerEvent(key_id=key_id, source=source, timestamp=now)
        )
        self._last_fire_time = now

    def _update_pinch(
        self,
        pointer: PointerState,
        hovered_key_id: Optional[KeyId],
        now: float,
        events: List[KeyTriggerEvent],
    ) -> None:
        if not pointer.valid or hovered_key_id is None:
            self._pinch_state = _PinchState.IDLE
            self._pinch_key = None
            self._stable_frames = 0
            return

        threshold = self._settings.pinch_threshold_px
        pinching = pointer.pinch_distance_px < threshold

        if self._pinch_state == _PinchState.IDLE:
            if pinching:
                self._pinch_state = _PinchState.PINCHING
                self._pinch_key = hovered_key_id
                self._stable_frames = 1
            return

        # PINCHING
        if self._pinch_key != hovered_key_id:
            logger.debug("Pinch cancelled: key sweep")
            self._pinch_state = _PinchState.IDLE
            self._pinch_key = None
            self._stable_frames = 0
            return

        if self._settings.pinch_fire_on == "stable_frames" and pinching:
            self._stable_frames += 1
            if self._stable_frames >= self._settings.pinch_stable_frames:
                self._emit(self._pinch_key, "pinch", now, events)
                self._pinch_state = _PinchState.IDLE
                self._pinch_key = None
                self._stable_frames = 0
            return

        if not pinching and self._pinch_key is not None:
            if self._settings.pinch_fire_on == "release":
                self._emit(self._pinch_key, "pinch", now, events)
            self._pinch_state = _PinchState.IDLE
            self._pinch_key = None
            self._stable_frames = 0

    def _update_hover(
        self,
        hovered_key_id: Optional[KeyId],
        now: float,
        events: List[KeyTriggerEvent],
    ) -> None:
        if hovered_key_id is None:
            self._hover_key = None
            self._hover_start = None
            return

        if hovered_key_id != self._hover_key:
            self._hover_key = hovered_key_id
            self._hover_start = now
            return

        if self._hover_start is None:
            self._hover_start = now
            return

        if (now - self._hover_start) >= self._settings.hover_sec:
            self._emit(hovered_key_id, "hover", now, events)
            self._hover_key = None
            self._hover_start = None

    def update(
        self,
        pointer: PointerState,
        hovered_key_id: Optional[KeyId],
        now: float,
    ) -> List[KeyTriggerEvent]:
        events: List[KeyTriggerEvent] = []
        mode = self._settings.trigger_mode

        if mode in ("pinch", "both"):
            self._update_pinch(pointer, hovered_key_id, now, events)
        if mode in ("hover", "both") and not events:
            self._update_hover(hovered_key_id, now, events)

        return events
