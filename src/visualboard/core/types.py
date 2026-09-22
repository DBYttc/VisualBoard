from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, NewType, Optional

import numpy as np
import numpy.typing as npt

KeyId = NewType("KeyId", str)
TriggerSource = Literal["pinch", "hover"]
AppMode = Literal["keyboard", "mouse"]


@dataclass(frozen=True, slots=True)
class Point2D:
    x: float
    y: float


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


Frame = npt.NDArray[np.uint8]
