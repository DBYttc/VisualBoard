"""Multi-finger projection-length depth press + per-finger trigger."""

from __future__ import annotations

import numpy as np

from visualboard.core.config_loader import DepthPressSettings, InteractionSettings
from visualboard.core.types import KeyId, Point2D, PointerState
from visualboard.interaction.multi_finger_depth import MultiFingerDepthPress
from visualboard.interaction.trigger_engine import TriggerEngine
from visualboard.vision.finger_width import finger_projection_px
from visualboard.vision.landmarks import FINGER_NAMES, FINGER_SEGMENTS

KEY_A = KeyId("key_a")
KEY_B = KeyId("key_b")
KEY_C = KeyId("key_c")


def _ds(**over) -> DepthPressSettings:
    values = dict(
        enabled=True,
        source="finger_length",
        direction="far",
        baseline_mode="rolling",
        enter_ratio=1.12,
        exit_ratio=1.06,
        stable_frames=2,
        baseline_samples=30,
        min_samples=5,
        latch_key=True,
    )
    values.update(over)
    return DepthPressSettings(**values)


def _inter(**over) -> InteractionSettings:
    values = dict(
        pinch_threshold_px=40.0,
        cooldown_sec=0.05,
        hover_sec=0.5,
        trigger_mode="pinch",
        pinch_fire_on="press_edge",
        pinch_stable_frames=2,
        pinch_source="depth",
    )
    values.update(over)
    return InteractionSettings(**values)


def _landmarks_at_lengths(lengths: dict[str, float]) -> np.ndarray:
    """Synthetic landmarks: each finger MCP at origin-ish, tip along +Y by length."""
    lm = np.zeros((21, 2), dtype=np.float64)
    base_x = {"thumb": 100.0, "index": 200.0, "middle": 300.0, "ring": 400.0, "pinky": 500.0}
    for name in FINGER_NAMES:
        mcp, tip = FINGER_SEGMENTS[name]
        x = base_x[name]
        length = lengths.get(name, 100.0)
        lm[mcp] = (x, 100.0)
        lm[tip] = (x, 100.0 + length)
    return lm


def test_finger_projection_px_matches_segments():
    lm = _landmarks_at_lengths({"index": 80.0, "middle": 120.0})
    _a, _b, length = finger_projection_px("index", lm)
    assert abs(length - 80.0) < 1e-6
    _a, _b, length = finger_projection_px("middle", lm)
    assert abs(length - 120.0) < 1e-6


def test_multi_detector_presses_independently():
    det = MultiFingerDepthPress(_ds(stable_frames=2, min_samples=5))
    # Warm baseline at 100px for all fingers
    for i in range(10):
        det.update(_landmarks_at_lengths({}), now=i * 0.03)

    # Only index shortens (far direction -> press)
    pressed = det.update(
        _landmarks_at_lengths({"index": 85.0}), now=1.0
    )
    assert pressed["index"] is False  # first confirm frame
    pressed = det.update(
        _landmarks_at_lengths({"index": 85.0}), now=1.03
    )
    assert pressed["index"] is True
    assert pressed["middle"] is False
    assert pressed["thumb"] is False


def test_two_fingers_fire_different_keys_same_frame():
    engine = TriggerEngine(_inter(), _ds())
    finger_keys = {
        "thumb": None,
        "index": KEY_A,
        "middle": KEY_B,
        "ring": None,
        "pinky": None,
    }
    pressed = {n: False for n in FINGER_NAMES}
    pressed["index"] = True
    pressed["middle"] = True

    pointer = PointerState(
        index_px=Point2D(0, 0),
        thumb_px=Point2D(100, 0),
        pinch_distance_px=100.0,
        valid=True,
    )

    events = engine.update(
        pointer, KEY_A, 0.0, finger_keys=finger_keys, finger_pressed=pressed
    )
    events += engine.update(
        pointer, KEY_A, 0.03, finger_keys=finger_keys, finger_pressed=pressed
    )

    keys = {e.key_id for e in events}
    assert KEY_A in keys
    assert KEY_B in keys
    assert all(e.source == "depth" for e in events)


def test_press_edge_no_refire_while_held():
    engine = TriggerEngine(_inter(), _ds())
    finger_keys = {n: (KEY_A if n == "index" else None) for n in FINGER_NAMES}
    pressed = {n: (n == "index") for n in FINGER_NAMES}
    pointer = PointerState(
        index_px=Point2D(0, 0),
        thumb_px=Point2D(100, 0),
        pinch_distance_px=100.0,
        valid=True,
    )

    events = []
    for i in range(12):
        events += engine.update(
            pointer,
            KEY_A,
            i * 0.03,
            finger_keys=finger_keys,
            finger_pressed=pressed,
        )
    assert len(events) == 1

    # Release then press again
    released = {n: False for n in FINGER_NAMES}
    engine.update(pointer, KEY_A, 1.0, finger_keys=finger_keys, finger_pressed=released)
    events += engine.update(
        pointer, KEY_A, 1.1, finger_keys=finger_keys, finger_pressed=pressed
    )
    events += engine.update(
        pointer, KEY_A, 1.13, finger_keys=finger_keys, finger_pressed=pressed
    )
    assert len(events) == 2


def test_latch_keeps_original_key_on_drift():
    engine = TriggerEngine(_inter(), _ds(latch_key=True))
    pointer = PointerState(
        index_px=Point2D(0, 0),
        thumb_px=Point2D(100, 0),
        pinch_distance_px=100.0,
        valid=True,
    )
    keys_a = {n: (KEY_A if n == "index" else None) for n in FINGER_NAMES}
    keys_b = {n: (KEY_B if n == "index" else None) for n in FINGER_NAMES}
    pressed = {n: (n == "index") for n in FINGER_NAMES}

    engine.update(pointer, KEY_A, 0.0, finger_keys=keys_a, finger_pressed=pressed)
    engine.update(pointer, KEY_B, 0.03, finger_keys=keys_b, finger_pressed=pressed)
    events = engine.update(
        pointer, KEY_B, 0.06, finger_keys=keys_b, finger_pressed=pressed
    )
    # After stable_frames=2 the second update already fired; check key was A
    # Re-run cleanly:
    engine.reset()
    events = []
    events += engine.update(pointer, KEY_A, 0.0, finger_keys=keys_a, finger_pressed=pressed)
    events += engine.update(pointer, KEY_B, 0.03, finger_keys=keys_b, finger_pressed=pressed)
    assert len(events) == 1
    assert events[0].key_id == KEY_A


def test_contact_source_ignores_multi_finger_path():
    """pinch_source=contact must not use multi-finger depth even if finger maps passed."""
    engine = TriggerEngine(_inter(pinch_source="contact"), _ds())
    finger_keys = {n: (KEY_C if n == "index" else None) for n in FINGER_NAMES}
    pressed = {n: True for n in FINGER_NAMES}
    pointer = PointerState(
        index_px=Point2D(0, 0),
        thumb_px=Point2D(100, 0),
        pinch_distance_px=100.0,  # not pinching
        valid=True,
    )
    events = engine.update(
        pointer,
        KEY_C,
        0.0,
        depth_pressed=True,
        finger_keys=finger_keys,
        finger_pressed=pressed,
    )
    events += engine.update(
        pointer,
        KEY_C,
        0.03,
        depth_pressed=True,
        finger_keys=finger_keys,
        finger_pressed=pressed,
    )
    assert not events
