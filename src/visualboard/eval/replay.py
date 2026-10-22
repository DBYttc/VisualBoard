"""Replay recorded measurements through the existing press detectors."""

from __future__ import annotations

from typing import Dict, Optional, Sequence

from visualboard.core.config_loader import DepthPressSettings
from visualboard.eval.io_csv import FrameRow
from visualboard.interaction.depth_press import DepthPressDetector
from visualboard.vision.landmarks import FINGER_NAMES


def replay_depth(
    frames: Sequence[FrameRow], settings: DepthPressSettings
) -> list[float]:
    """Rising edges of the OR of five ``DepthPressDetector`` levels.

    ``stable_frames`` is applied inside the detector. Empty lengths are passed
    as None, which keeps the current level and does not update the baseline.
    """
    detectors = {name: DepthPressDetector(settings) for name in FINGER_NAMES}
    prev = False
    edges: list[float] = []
    for frame in frames:
        active = False
        for name in FINGER_NAMES:
            pressed = detectors[name].update(frame.lengths.get(name), frame.timestamp)
            active = active or pressed
        if active and not prev:
            edges.append(frame.timestamp)
        prev = active
    return edges


def replay_pinch(
    frames: Sequence[FrameRow],
    threshold_px: float,
    stable_frames: int,
) -> list[float]:
    """Rising edges when pinch distance stays under the threshold.

    Confirmation uses ``interaction.pinch_stable_frames`` from the caller.
    It is not the depth detector's ``stable_frames``. A missing distance
    clears the streak and re-arms the edge, matching a lost hand.
    """
    need = max(1, int(stable_frames))
    streak = 0
    armed = True
    edges: list[float] = []
    for frame in frames:
        distance = frame.pinch_distance_px
        if distance is None:
            streak = 0
            armed = True
            continue
        if distance < threshold_px:
            streak += 1
            if armed and streak >= need:
                edges.append(frame.timestamp)
                armed = False
                streak = 0
        else:
            streak = 0
            armed = True
    return edges


def lengths_of(frame: FrameRow) -> Dict[str, Optional[float]]:
    return {name: frame.lengths.get(name) for name in FINGER_NAMES}
