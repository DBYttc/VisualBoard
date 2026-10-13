"""Per-finger projection-length depth press (one DepthPressDetector each)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import numpy.typing as npt

from visualboard.core.config_loader import DepthPressSettings
from visualboard.core.types import Point2D
from visualboard.interaction.depth_press import DepthPressDetector
from visualboard.vision.finger_width import finger_projection_px
from visualboard.vision.landmarks import FINGER_NAMES


@dataclass(frozen=True, slots=True)
class FingerDepthSample:
    name: str
    pressed: bool
    length_px: Optional[float]
    line: Optional[Tuple[Point2D, Point2D]]
    signal: Optional[float]
    warming_up: bool


class MultiFingerDepthPress:
    """Five independent projection-length press detectors sharing one settings blob."""

    def __init__(self, settings: DepthPressSettings) -> None:
        self._settings = settings
        self._detectors: Dict[str, DepthPressDetector] = {
            name: DepthPressDetector(settings) for name in FINGER_NAMES
        }
        self._last: Dict[str, FingerDepthSample] = {}

    def reset(self) -> None:
        for det in self._detectors.values():
            det.reset()
        self._last.clear()

    @property
    def warming_up(self) -> bool:
        return any(d.warming_up for d in self._detectors.values())

    def warmup_remaining(self) -> Optional[float]:
        remainings = [
            d.warmup_remaining()
            for d in self._detectors.values()
            if d.warmup_remaining() is not None
        ]
        if not remainings:
            return None
        return max(remainings)  # type: ignore[type-var]

    def last_samples(self) -> Dict[str, FingerDepthSample]:
        return dict(self._last)

    def pressed_names(self) -> List[str]:
        return [s.name for s in self._last.values() if s.pressed]

    def update(
        self,
        landmarks_px: npt.NDArray[np.float64],
        now: Optional[float] = None,
    ) -> Dict[str, bool]:
        """Feed one frame of landmarks; return {finger_name: pressed}."""
        result: Dict[str, bool] = {}
        for name in FINGER_NAMES:
            a, b, length = finger_projection_px(name, landmarks_px)
            det = self._detectors[name]
            pressed = det.update(length, now)
            result[name] = pressed
            self._last[name] = FingerDepthSample(
                name=name,
                pressed=pressed,
                length_px=length,
                line=(Point2D(a[0], a[1]), Point2D(b[0], b[1])),
                signal=det.signal(),
                warming_up=det.warming_up,
            )
        return result

    def hud_text(self) -> Optional[str]:
        if not self._settings.enabled:
            return None
        if self.warming_up:
            remaining = self.warmup_remaining()
            if remaining is not None:
                return (
                    f"depth(5f): CALIBRATING {remaining:.1f}s - hold your hand still"
                )
        pressed = self.pressed_names()
        if not self._last:
            return "depth(5f): collecting baseline..."
        # Show busiest finger signal for tuning feedback
        signals = [
            (s.name, s.signal)
            for s in self._last.values()
            if s.signal is not None
        ]
        if not signals:
            return "depth(5f): collecting baseline..."
        name, sig = max(signals, key=lambda item: item[1] or 0.0)
        state = f"PRESS:{','.join(pressed)}" if pressed else "idle"
        return f"depth(5f): {name}=x{sig:.3f} {state}"

    def measure_lines(self) -> List[Tuple[Point2D, Point2D]]:
        """Lines for HUD: prefer pressed fingers, else all measured segments."""
        pressed_lines = [
            s.line for s in self._last.values() if s.pressed and s.line is not None
        ]
        if pressed_lines:
            return pressed_lines  # type: ignore[return-value]
        return [s.line for s in self._last.values() if s.line is not None]  # type: ignore[misc]
