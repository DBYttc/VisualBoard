"""Offline scoring for recorded press sessions.

Experiment numbers in the course report must come from ``data_kind=real``
sessions. This package does not synthesize those sessions.
"""

from visualboard.eval.metrics import GridPoint, Segment, SegmentScore, select_operating_point

__all__ = [
    "GridPoint",
    "Segment",
    "SegmentScore",
    "select_operating_point",
]
