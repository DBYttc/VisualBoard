from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional

from visualboard.core.config_loader import DepthPressSettings, InteractionSettings
from visualboard.core.types import KeyId, PointerState, TriggerSource
from visualboard.interaction.events import KeyTriggerEvent

logger = logging.getLogger(__name__)


class _PinchState(Enum):
    IDLE = auto()
    PINCHING = auto()
    FIRED = auto()  # press_edge 模式：已经出过字，等回到中立区才重新武装


@dataclass
class _FingerTriggerState:
    state: _PinchState = _PinchState.IDLE
    key: Optional[KeyId] = None
    stable_frames: int = 0
    last_fire_time: float = -1e9


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
        self._finger_states: Dict[str, _FingerTriggerState] = {}

    def reset(self) -> None:
        self._pinch_state = _PinchState.IDLE
        self._pinch_key = None
        self._hover_key = None
        self._hover_start = None
        self._stable_frames = 0
        self._press_from_depth = False
        self._finger_states.clear()

    def _use_multi_finger_depth(self) -> bool:
        return (
            self._depth_settings is not None
            and self._depth_settings.enabled
            and self._depth_settings.source == "finger_length"
            and self._settings.pinch_source in ("depth", "both")
        )

    def _in_cooldown(self, now: float) -> bool:
        return (now - self._last_fire_time) < self._settings.cooldown_sec

    def _finger_in_cooldown(self, finger: str, now: float) -> bool:
        st = self._finger_states.get(finger)
        if st is None:
            return False
        return (now - st.last_fire_time) < self._settings.cooldown_sec

    def _emit(
        self,
        key_id: KeyId,
        source: TriggerSource,
        now: float,
        events: List[KeyTriggerEvent],
        finger: Optional[str] = None,
    ) -> None:
        if finger is not None:
            if self._finger_in_cooldown(finger, now):
                logger.debug(
                    "Trigger suppressed by per-finger cooldown finger=%s key=%s",
                    finger,
                    key_id,
                )
                return
        elif self._in_cooldown(now):
            logger.debug("Trigger suppressed by cooldown key=%s", key_id)
            return
        events.append(
            KeyTriggerEvent(key_id=key_id, source=source, timestamp=now)
        )
        if finger is not None:
            st = self._finger_states.setdefault(finger, _FingerTriggerState())
            st.last_fire_time = now
        else:
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

    def _update_multi_finger_depth(
        self,
        finger_keys: Dict[str, Optional[KeyId]],
        finger_pressed: Dict[str, bool],
        now: float,
        events: List[KeyTriggerEvent],
    ) -> None:
        """Independent press_edge / stable_frames / release state machine per finger."""
        latch = bool(self._depth_settings is not None and self._depth_settings.latch_key)
        fire_on = self._settings.pinch_fire_on

        for name, pressed in finger_pressed.items():
            st = self._finger_states.setdefault(name, _FingerTriggerState())
            hovered = finger_keys.get(name)

            if hovered is None:
                if st.state is not _PinchState.FIRED:
                    st.state = _PinchState.IDLE
                    st.key = None
                    st.stable_frames = 0
                continue

            if st.state is _PinchState.FIRED:
                if not pressed:
                    st.state = _PinchState.IDLE
                    st.key = None
                    st.stable_frames = 0
                continue

            if st.state is _PinchState.IDLE:
                if pressed:
                    st.state = _PinchState.PINCHING
                    st.key = hovered
                    st.stable_frames = 1
                continue

            # PINCHING
            if st.key != hovered:
                if not latch:
                    logger.debug("Multi-finger press cancelled: key sweep finger=%s", name)
                    st.state = _PinchState.IDLE
                    st.key = None
                    st.stable_frames = 0
                    continue
                # latch: keep original key

            if fire_on in ("stable_frames", "press_edge") and pressed:
                st.stable_frames += 1
                if st.stable_frames >= self._settings.pinch_stable_frames:
                    if st.key is not None:
                        self._emit(st.key, "depth", now, events, finger=name)
                    if fire_on == "press_edge":
                        st.state = _PinchState.FIRED
                        st.stable_frames = 0
                    else:
                        st.state = _PinchState.IDLE
                        st.key = None
                        st.stable_frames = 0
                continue

            if not pressed and st.key is not None:
                if fire_on == "release":
                    self._emit(st.key, "depth", now, events, finger=name)
                st.state = _PinchState.IDLE
                st.key = None
                st.stable_frames = 0

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
        finger_keys: Optional[Dict[str, Optional[KeyId]]] = None,
        finger_pressed: Optional[Dict[str, bool]] = None,
    ) -> List[KeyTriggerEvent]:
        events: List[KeyTriggerEvent] = []
        mode = self._settings.trigger_mode

        if mode in ("pinch", "both"):
            if (
                self._use_multi_finger_depth()
                and finger_keys is not None
                and finger_pressed is not None
            ):
                self._update_multi_finger_depth(finger_keys, finger_pressed, now, events)
                # both: also allow classic contact pinch on index hover
                if self._settings.pinch_source == "both":
                    contact = (
                        pointer.valid
                        and pointer.pinch_distance_px < self._settings.pinch_threshold_px
                    )
                    if contact:
                        self._update_pinch(pointer, hovered_key_id, now, events, False)
            else:
                self._update_pinch(pointer, hovered_key_id, now, events, depth_pressed)
        if mode in ("hover", "both") and not events:
            self._update_hover(hovered_key_id, now, events)

        return events
