from __future__ import annotations

import logging
from enum import Enum, auto
from typing import List, Optional

from visualboard.core.config_loader import DepthPressSettings, InteractionSettings
from visualboard.core.types import KeyId, PointerState, TriggerSource
from visualboard.interaction.events import KeyTriggerEvent

logger = logging.getLogger(__name__)


class _PinchState(Enum):
    IDLE = auto()
    PINCHING = auto()
    FIRED = auto()  # press_edge 模式：已经出过字，等回到中立区才重新武装


class TriggerEngine:
    def __init__(
        self,
        settings: InteractionSettings,
        depth_settings: Optional[DepthPressSettings] = None,
    ) -> None:
        self._settings = settings
        self._depth_settings = depth_settings
        self._pinch_state = _PinchState.IDLE
        self._pinch_key: Optional[KeyId] = None
        self._last_fire_time = -1e9
        self._hover_key: Optional[KeyId] = None
        self._hover_start: Optional[float] = None
        self._stable_frames = 0
        # 本次按压是否由"表观尺寸/深度"通道发起：决定事件 source 与是否锁键
        self._press_from_depth = False

    def reset(self) -> None:
        self._pinch_state = _PinchState.IDLE
        self._pinch_key = None
        self._hover_key = None
        self._hover_start = None
        self._stable_frames = 0
        self._press_from_depth = False

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
        depth_pressed: Optional[bool] = None,
    ) -> None:
        if not pointer.valid or hovered_key_id is None:
            # FIRED 状态下即使暂时离开键位也要保持，否则手指还压着时移回键上会再触发一次
            if self._pinch_state is not _PinchState.FIRED:
                self._pinch_state = _PinchState.IDLE
                self._pinch_key = None
                self._stable_frames = 0
                self._press_from_depth = False
            return

        threshold = self._settings.pinch_threshold_px
        contact = pointer.pinch_distance_px < threshold
        depth = bool(depth_pressed)
        mode = self._settings.pinch_source
        if mode == "contact":
            pinching = contact
        elif mode == "depth":
            pinching = depth
        else:  # both
            pinching = contact or depth

        if self._pinch_state is _PinchState.FIRED:
            # 已经出过字：必须等手指回到中立区（pinching 变 False）才重新武装
            if not pinching:
                self._pinch_state = _PinchState.IDLE
                self._pinch_key = None
                self._stable_frames = 0
                self._press_from_depth = False
            return

        if self._pinch_state == _PinchState.IDLE:
            if pinching:
                self._pinch_state = _PinchState.PINCHING
                self._pinch_key = hovered_key_id
                self._stable_frames = 1
                self._press_from_depth = depth and not contact
            return

        # PINCHING
        if self._pinch_key != hovered_key_id:
            # 深度按压时手指下压会带来横向视差，hover 可能漂到隔壁键；
            # latch_key=True 时锁定按下瞬间的键（等价于"按下即定键"）。
            latch = bool(
                self._press_from_depth
                and self._depth_settings is not None
                and self._depth_settings.latch_key
            )
            if not latch:
                logger.debug("Pinch cancelled: key sweep")
                self._pinch_state = _PinchState.IDLE
                self._pinch_key = None
                self._stable_frames = 0
                self._press_from_depth = False
                return

        trigger_source: TriggerSource = "depth" if self._press_from_depth else "pinch"
        fire_on = self._settings.pinch_fire_on

        if fire_on in ("stable_frames", "press_edge") and pinching:
            self._stable_frames += 1
            if self._stable_frames >= self._settings.pinch_stable_frames:
                self._emit(self._pinch_key, trigger_source, now, events)
                if fire_on == "press_edge":
                    # 出字后停在 FIRED，按住不放也不会连发；松开（回到中立区）才复位
                    self._pinch_state = _PinchState.FIRED
                    self._stable_frames = 0
                else:
                    self._pinch_state = _PinchState.IDLE
                    self._pinch_key = None
                    self._stable_frames = 0
                    self._press_from_depth = False
            return

        if not pinching and self._pinch_key is not None:
            if fire_on == "release":
                self._emit(self._pinch_key, trigger_source, now, events)
            self._pinch_state = _PinchState.IDLE
            self._pinch_key = None
            self._stable_frames = 0
            self._press_from_depth = False

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
        depth_pressed: Optional[bool] = None,
    ) -> List[KeyTriggerEvent]:
        events: List[KeyTriggerEvent] = []
        mode = self._settings.trigger_mode

        if mode in ("pinch", "both"):
            self._update_pinch(pointer, hovered_key_id, now, events, depth_pressed)
        if mode in ("hover", "both") and not events:
            self._update_hover(hovered_key_id, now, events)

        return events
