from __future__ import annotations

from typing import Dict, List, Optional

from visualboard.core.config_loader import SmoothingSettings
from visualboard.core.types import FingerPointer, HandResult, Point2D, PointerState
from visualboard.vision.finger_width import finger_projection_px
from visualboard.vision.landmarks import FINGER_NAMES, FINGER_TIPS


class PointerStateTracker:
    def __init__(self, settings: SmoothingSettings) -> None:
        self._alpha = settings.ema_alpha
        self._smooth_tips: Dict[str, Optional[Point2D]] = {
            name: None for name in FINGER_NAMES
        }

    def reset(self) -> None:
        self._smooth_tips = {name: None for name in FINGER_NAMES}

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
                pinch_distance_px=float("inf"),
                valid=False,
                fingers=(),
            )

        lm = hand.landmarks_px
        fingers: List[FingerPointer] = []
        for name in FINGER_NAMES:
            tip_idx = FINGER_TIPS[name]
            raw = Point2D(float(lm[tip_idx][0]), float(lm[tip_idx][1]))
            smoothed = self._ema(self._smooth_tips[name], raw)
            self._smooth_tips[name] = smoothed
            _a, _b, proj = finger_projection_px(name, lm)
            fingers.append(
                FingerPointer(
                    name=name,  # type: ignore[arg-type]
                    tip_px=smoothed,
                    projection_px=proj,
                )
            )

        index_px = self._smooth_tips["index"]
        thumb_px = self._smooth_tips["thumb"]
        assert index_px is not None and thumb_px is not None

        return PointerState(
            index_px=index_px,
            thumb_px=thumb_px,
            pinch_distance_px=self._distance(index_px, thumb_px),
            valid=True,
            fingers=tuple(fingers),
        )
