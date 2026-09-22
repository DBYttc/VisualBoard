#!/usr/bin/env python3
"""Interactive pinch threshold calibration."""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from visualboard.capture.opencv_camera import OpenCVCamera
from visualboard.core.config_loader import load_settings
from visualboard.interaction.pointer_state import PointerStateTracker
from visualboard.vision.drawing import draw_pointer_dot
from visualboard.vision.hand_tracker import HandTracker

SAMPLES: list[float] = []


def main() -> int:
    settings = load_settings(ROOT / "config")
    camera = OpenCVCamera(settings.camera)
    tracker = HandTracker(settings.mediapipe)
    pointer_tracker = PointerStateTracker(settings.smoothing)

    print("Pinch 10 times when prompted. Press c to capture sample, q to quit.")

    try:
        while len(SAMPLES) < 10:
            frame = camera.read()
            if frame is None:
                continue
            hand = tracker.process(frame)
            if hand.detected:
                p = pointer_tracker.update(hand)
                if p.valid:
                    draw_pointer_dot(frame, p.index_px)
                    cv2.putText(
                        frame,
                        f"dist={p.pinch_distance_px:.1f} samples={len(SAMPLES)}/10",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 0),
                        2,
                    )
            cv2.imshow("Calibrate pinch (c=capture, q=quit)", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                return 1
            if key == ord("c") and hand.detected:
                p = pointer_tracker.update(hand)
                if p.valid:
                    SAMPLES.append(p.pinch_distance_px)
                    print(f"  sample {len(SAMPLES)}: {p.pinch_distance_px:.1f}px")
    finally:
        tracker.close()
        camera.release()
        cv2.destroyAllWindows()

    if len(SAMPLES) < 3:
        print("Not enough samples.")
        return 1

    mean = statistics.mean(SAMPLES)
    stdev = statistics.pstdev(SAMPLES) if len(SAMPLES) > 1 else 5.0
    suggested = mean + stdev
    print(f"\nSuggested pinch_threshold_px: {suggested:.1f}")
    print("Add to config/local.yaml:")
    print("interaction:")
    print(f"  pinch_threshold_px: {round(suggested)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
