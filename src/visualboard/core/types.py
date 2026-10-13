from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, NewType, Optional, Tuple

import numpy as np
import numpy.typing as npt

KeyId = NewType("KeyId", str)
TriggerSource = Literal["pinch", "hover", "depth"]
AppMode = Literal["keyboard", "mouse"]
FingerName = Literal["thumb", "index", "middle", "ring", "pinky"]


@dataclass(frozen=True, slots=True)
class Point2D:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class FingerPointer:
    """Single fingertip used for hit-test + projection-length depth press."""

    name: FingerName
    tip_px: Point2D
    projection_px: float


@dataclass(frozen=True, slots=True)
class HandResult:
    detected: bool
    landmarks_px: Optional[npt.NDArray[np.float64]] = None
    handedness: Optional[str] = None


@dataclass(frozen=True, slots=True)
class PointerState:
    index_px: Point2D
    thumb_px: Point2D
    pinch_distance_px: float
    valid: bool = True
    fingers: Tuple[FingerPointer, ...] = field(default_factory=tuple)


Frame = npt.NDArray[np.uint8]
