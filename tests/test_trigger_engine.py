from __future__ import annotations

from visualboard.core.config_loader import InteractionSettings
from visualboard.core.types import KeyId, Point2D, PointerState
from visualboard.interaction.trigger_engine import TriggerEngine


def _pointer(dist: float) -> PointerState:
    return PointerState(
        index_px=Point2D(100, 100),
        thumb_px=Point2D(100 + dist, 100),
        pinch_distance_px=dist,
        valid=True,
    )


def test_pinch_release_fires_on_hovered_key(interaction_settings: InteractionSettings):
    engine = TriggerEngine(interaction_settings)
    key = KeyId("key_a")
    t = 0.0

    events = engine.update(_pointer(50), key, t)
    assert not events

    events = engine.update(_pointer(30), key, t + 0.01)
    assert not events

    events = engine.update(_pointer(50), key, t + 0.02)
    assert len(events) == 1
    assert events[0].key_id == key
    assert events[0].source == "pinch"


def test_cooldown_blocks_second_fire(interaction_settings: InteractionSettings):
    engine = TriggerEngine(interaction_settings)
    key = KeyId("key_a")
    t = 0.0

    engine.update(_pointer(30), key, t)
    events = engine.update(_pointer(50), key, t + 0.01)
    assert len(events) == 1

    engine.update(_pointer(30), key, t + 0.05)
    events = engine.update(_pointer(50), key, t + 0.06)
    assert not events

    engine.update(_pointer(30), key, t + 0.5)
    events = engine.update(_pointer(50), key, t + 0.51)
    assert len(events) == 1


def test_key_sweep_cancels_pinch(interaction_settings: InteractionSettings):
    engine = TriggerEngine(interaction_settings)
    key_a = KeyId("key_a")
    key_b = KeyId("key_b")
    t = 0.0

    engine.update(_pointer(30), key_a, t)
    engine.update(_pointer(30), key_b, t + 0.01)
    events = engine.update(_pointer(50), key_b, t + 0.02)
    assert not events


def test_hover_mode(interaction_settings: InteractionSettings):
    settings = InteractionSettings(
        pinch_threshold_px=interaction_settings.pinch_threshold_px,
        cooldown_sec=interaction_settings.cooldown_sec,
        hover_sec=0.3,
        trigger_mode="hover",
        pinch_fire_on="release",
        pinch_stable_frames=3,
    )
    engine = TriggerEngine(settings)
    key = KeyId("key_a")

    events = engine.update(_pointer(100), key, 0.0)
    assert not events
    events = engine.update(_pointer(100), key, 0.2)
    assert not events
    events = engine.update(_pointer(100), key, 0.31)
    assert len(events) == 1
    assert events[0].source == "hover"
