from __future__ import annotations

import numpy as np

from visualboard.core.types import HandResult
from visualboard.interaction.pointer_state import PointerStateTracker


def _hand_at(index_xy: tuple[float, float], thumb_xy: tuple[float, float]) -> HandResult:
    pts = np.zeros((21, 2), dtype=np.float64)
    pts[8] = index_xy
    pts[4] = thumb_xy
    return HandResult(detected=True, landmarks_px=pts)


def test_ema_smooths_step(smoothing_settings):
    tracker = PointerStateTracker(smoothing_settings)
    p0 = tracker.update(_hand_at((0.0, 0.0), (100.0, 0.0)))
    assert p0.index_px.x == 0.0

    p1 = tracker.update(_hand_at((100.0, 0.0), (100.0, 0.0)))
    assert p1.index_px.x == 50.0

    p2 = tracker.update(_hand_at((100.0, 0.0), (100.0, 0.0)))
    assert p2.index_px.x == 75.0
