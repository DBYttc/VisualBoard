#!/usr/bin/env python3
"""Measure camera + hand tracking FPS for ~10 seconds."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from visualboard.capture.opencv_camera import OpenCVCamera
from visualboard.core.config_loader import load_settings
from visualboard.vision.hand_tracker import HandTracker


def main() -> int:
    settings = load_settings(ROOT / "config")
    camera = OpenCVCamera(settings.camera)
    tracker = HandTracker(settings.mediapipe)

    frames = 0
    start = time.monotonic()
    duration = 10.0

    try:
        while time.monotonic() - start < duration:
            frame = camera.read()
            if frame is None:
                continue
            tracker.process(frame)
            frames += 1
    finally:
        tracker.close()
        camera.release()

    elapsed = time.monotonic() - start
    print(f"Frames: {frames}, elapsed: {elapsed:.2f}s, FPS: {frames / elapsed:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
