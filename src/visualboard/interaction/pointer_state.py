from __future__ import annotations

from typing import Optional

from visualboard.core.config_loader import SmoothingSettings
from visualboard.core.types import HandResult, Point2D, PointerState
from visualboard.vision.landmarks import INDEX_FINGER_TIP, THUMB_TIP


class PointerStateTracker:
    def __init__(self, settings: SmoothingSettings) -> None:
        self._alpha = settings.ema_alpha
        self._smooth_index: Optional[Point2D] = None
        self._smooth_thumb: Optional[Point2D] = None

    def reset(self) -> None:
        self._smooth_index = None
        self._smooth_thumb = None

    def _ema(self, prev: Optional[Point2D], raw: Point2D) -> Point2D:
        if prev is None:
            return raw
        a = self._alpha
        return Point2D(
            x=a * raw.x + (1 - a) * prev.x,
            y=a * raw.y + (1 - a) * prev.y,
        )

    @staticmethod
    def _distance(a: Point2D, b: Point2D) -> float:
        dx = a.x - b.x
        dy = a.y - b.y
        return (dx * dx + dy * dy) ** 0.5

    def update(self, hand: HandResult) -> PointerState:
        if not hand.detected or hand.landmarks_px is None:
            return PointerState(
                index_px=Point2D(0, 0),
                thumb_px=Point2D(0, 0),
                pinch_distance_px= float("inf"),
                valid=False,
            )

        idx = hand.landmarks_px[INDEX_FINGER_TIP]
        thumb = hand.landmarks_px[THUMB_TIP]
        raw_index = Point2D(float(idx[0]), float(idx[1]))
        raw_thumb = Point2D(float(thumb[0]), float(thumb[1]))

        self._smooth_index = self._ema(self._smooth_index, raw_index)
        self._smooth_thumb = self._ema(self._smooth_thumb, raw_thumb)

        assert self._smooth_index is not None
        assert self._smooth_thumb is not None

        dist = self._distance(self._smooth_index, self._smooth_thumb)
        return PointerState(
            index_px=self._smooth_index,
            thumb_px=self._smooth_thumb,
            pinch_distance_px=dist,
            valid=True,
        )
