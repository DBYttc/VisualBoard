#!/usr/bin/env python3
"""Depth-press (apparent finger size -> distance) tuning aid.

Shows per frame:
  - the skin mask that the mask-source width measurement uses ('m' toggles the overlay)
  - a cyan line over the segment actually being measured for the configured source
  - all three candidate signals side by side (mask width / hand_scale / finger_length)
  - the ratio against the rolling baseline and the resulting signal

Usage:
    .venv\\Scripts\\python.exe scripts\\tune_depth_press.py                 # live camera
    .venv\\Scripts\\python.exe scripts\\tune_depth_press.py --image shot.png # offline

Keys (live): m = toggle mask overlay, s = save debug snapshot, q = quit
Offline mode writes <image>.depth_debug.png next to the input.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from visualboard.capture.opencv_camera import OpenCVCamera  # noqa: E402
from visualboard.core.config_loader import load_settings  # noqa: E402
from visualboard.core.types import Point2D  # noqa: E402
from visualboard.interaction.depth_press import DepthPressDetector  # noqa: E402
from visualboard.vision.drawing import draw_measure_line  # noqa: E402
from visualboard.vision.finger_width import (  # noqa: E402
    measure_finger_width_px,
    scale_segment_px,
    skin_mask,
)
from visualboard.vision.hand_tracker import HandTracker  # noqa: E402


def tint_mask(frame: np.ndarray, mask: np.ndarray, alpha: float = 0.35) -> np.ndarray:
    """Green tint over the pixels classified as skin."""
    tint = np.zeros_like(frame)
    tint[:, :, 1] = mask
    return cv2.addWeighted(frame, 1.0, tint, alpha, 0.0)


def landmark_signals(landmarks):
    """(hand_scale, finger_length) 两条只用关键点的信号，landmarks 为 None 时返回 (None, None)。"""
    if landmarks is None:
        return None, None
    return (
        scale_segment_px("hand_scale", landmarks)[2],
        scale_segment_px("finger_length", landmarks)[2],
    )


def annotate(frame, settings, measured, landmarks, detector) -> None:
    source = settings.source
    if source == "mask":
        if measured is not None:
            a, b = measured.endpoints()
            draw_measure_line(frame, Point2D(a[0], a[1]), Point2D(b[0], b[1]))
    elif landmarks is not None:
        a, b, _ = scale_segment_px(source, landmarks)
        draw_measure_line(frame, Point2D(a[0], a[1]), Point2D(b[0], b[1]))

    ratio = detector.ratio()
    signal = detector.signal()
    state = "PRESS" if detector.active else "idle"
    if ratio is not None and signal is not None:
        last = f"ratio={ratio:.4f}  signal={signal:.4f}  -> {state}"
    else:
        last = f"ratio=  n/a  signal=  n/a  -> collecting baseline... ({state})"

    hand, finger = landmark_signals(landmarks)
    lines = [
        (f"source={source}  direction={settings.direction}  "
         f"enter={settings.enter_ratio} exit={settings.exit_ratio}", (0, 255, 255)),
        (f"mask width   = {measured.width_px:7.2f}px"
         if measured is not None else "mask width   =     n/a", (0, 255, 255)),
        (f"hand_scale   = {hand:7.2f}px" if hand is not None
         else "hand_scale   =     n/a", (0, 255, 255)),
        (f"finger_length= {finger:7.2f}px" if finger is not None
         else "finger_length=     n/a", (0, 255, 255)),
        (last, (0, 255, 0) if state == "PRESS" else (200, 200, 200)),
    ]
    for i, (text, color) in enumerate(lines):
        cv2.putText(frame, text, (10, 26 + i * 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


def report(measured, landmarks) -> None:
    hand, finger = landmark_signals(landmarks)
    print(f"mask width    : {'n/a' if measured is None else f'{measured.width_px:.2f}px'}")
    print(f"hand_scale    : {'n/a' if hand is None else f'{hand:.2f}px'}")
    print(f"finger_length : {'n/a' if finger is None else f'{finger:.2f}px'}")
    print("Tip: do the press gesture and watch how far 'signal' moves away from 1.000;")
    print("     set enter_ratio between the idle max and the pressed peak.")


def run_offline(settings, path: Path) -> int:
    frame = cv2.imread(str(path))
    if frame is None:
        print(f"cannot read image: {path}")
        return 1

    tracker = HandTracker(settings.mediapipe)
    try:
        hand = tracker.process(frame)
        mask = skin_mask(frame, settings.depth_press)
        detector = DepthPressDetector(settings.depth_press)

        landmarks = hand.landmarks_px if hand.detected else None
        if landmarks is None:
            print("no hand detected in this image")
            measured = None
        else:
            measured = measure_finger_width_px(frame, landmarks, settings.depth_press)
            detector.update(measured.width_px if measured is not None else None)

        debug = tint_mask(frame, mask)
        annotate(debug, settings.depth_press, measured, landmarks, detector)
        out = path.with_suffix(path.suffix + ".depth_debug.png")
        cv2.imwrite(str(out), debug)
        print(f"skin pixels   : {int((mask > 0).sum())}")
        report(measured, landmarks)
        print(f"debug image   -> {out}")
    finally:
        tracker.close()
    return 0


def run_live(settings) -> int:
    camera = OpenCVCamera(settings.camera)
    tracker = HandTracker(settings.mediapipe)
    detector = DepthPressDetector(settings.depth_press)
    show_mask = True
    window = "tune depth press (m=mask s=save q=quit)"

    try:
        while True:
            frame = camera.read()
            if frame is None:
                continue

            hand = tracker.process(frame)
            landmarks = hand.landmarks_px if hand.detected else None
            measured = None
            if landmarks is not None:
                measured = measure_finger_width_px(frame, landmarks, settings.depth_press)
            detector.update(measured.width_px if measured is not None else None)

            view = frame.copy()
            if show_mask:
                view = tint_mask(view, skin_mask(frame, settings.depth_press))
            annotate(view, settings.depth_press, measured, landmarks, detector)
            cv2.imshow(window, view)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("m"):
                show_mask = not show_mask
            if key == ord("s"):
                out = ROOT / "depth_press_snapshot.png"
                cv2.imwrite(str(out), view)
                print(f"saved {out}")
                report(measured, landmarks)
    finally:
        tracker.close()
        camera.release()
        cv2.destroyAllWindows()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=None, help="offline: run on a still image")
    args = parser.parse_args()

    settings = load_settings(ROOT / "config")
    d = settings.depth_press
    print(f"depth_press: enabled={d.enabled} source={d.source} direction={d.direction} "
          f"enter={d.enter_ratio} exit={d.exit_ratio}")
    if not d.enabled:
        print("note: depth_press.enabled is false in config/local.yaml - "
              "the app will not show the measurement line until you set it to true")

    if args.image is not None:
        return run_offline(settings, args.image)
    return run_live(settings)


if __name__ == "__main__":
    raise SystemExit(main())
