#!/usr/bin/env python3
"""Guided recording of a real press session.

P starts a 1.5 s positive segment (press toward the desk and lift).
N starts a 2.0 s negative segment (hover and move, do not press).
S saves after 20 positive and 20 negative segments. Q quits without saving.

The CSV header is data_kind=real. Idle frames are stored so the rolling
baseline can be replayed; they are not scored.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from visualboard.capture.opencv_camera import OpenCVCamera  # noqa: E402
from visualboard.core.config_loader import load_settings  # noqa: E402
from visualboard.eval.io_csv import FrameRow, write_session  # noqa: E402
from visualboard.interaction.pointer_state import PointerStateTracker  # noqa: E402
from visualboard.vision.drawing import draw_hand_skeleton  # noqa: E402
from visualboard.vision.finger_width import finger_projection_px  # noqa: E402
from visualboard.vision.hand_tracker import HandTracker  # noqa: E402
from visualboard.vision.landmarks import FINGER_NAMES  # noqa: E402

POS_SEC = 1.5
NEG_SEC = 2.0
TARGET = 20


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distance-cm", type=float, required=True)
    parser.add_argument("--role", choices=("select", "transfer"), required=True)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "experiments" / "raw")
    args = parser.parse_args(argv)
    if args.distance_cm <= 0:
        print("--distance-cm must be positive", file=sys.stderr)
        return 1

    settings = load_settings(ROOT / "config")
    camera = OpenCVCamera(settings.camera)
    tracker = HandTracker(settings.mediapipe)
    pointer_tracker = PointerStateTracker(settings.smoothing)
    min_samples = max(2, int(settings.depth_press.min_samples))

    frames: list[FrameRow] = []
    origin = time.perf_counter()
    baseline_frames = 0
    n_pos = 0
    n_neg = 0
    segment_id = 0
    active: Optional[tuple[str, int, float, float]] = None
    window = "VisualBoard Record Session"
    print(
        "P = 1.5s 真按（向桌面下压再抬起），N = 2.0s 干扰（移动但不要下压）。"
        f"各满 {TARGET} 段后按 S 保存。Q 放弃且不写文件。"
    )
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    try:
        while True:
            frame = camera.read()
            if frame is None:
                continue
            now = time.perf_counter() - origin
            hand = tracker.process(frame)
            lengths = {name: None for name in FINGER_NAMES}
            pinch = None
            if hand.detected and hand.landmarks_px is not None:
                for name in FINGER_NAMES:
                    lengths[name] = finger_projection_px(name, hand.landmarks_px)[2]
                pointer = pointer_tracker.update(hand)
                pinch = pointer.pinch_distance_px
                if lengths["index"] is not None:
                    baseline_frames += 1
                draw_hand_skeleton(frame, hand)
            label = "idle"
            current_segment: Optional[int] = None
            if active is not None:
                kind, sid, started, duration = active
                label = kind
                current_segment = sid
                if now - started >= duration:
                    recorded = any(row.segment_id == sid for row in frames)
                    if recorded and kind == "pos":
                        n_pos += 1
                    elif recorded and kind == "neg":
                        n_neg += 1
                    active = None
                    label = "idle"
                    current_segment = None
            frames.append(
                FrameRow(
                    timestamp=now,
                    label=label,
                    segment_id=current_segment,
                    lengths=lengths,
                    pinch_distance_px=pinch,
                )
            )
            _annotate(
                frame,
                baseline_frames,
                min_samples,
                n_pos,
                n_neg,
                active,
                now,
                args.role,
                args.distance_cm,
            )
            cv2.imshow(window, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q")):
                print("Quit without saving.")
                return 0
            if key in (ord("s"), ord("S")):
                if n_pos < TARGET or n_neg < TARGET or active is not None:
                    print(f"Need {TARGET} POS and {TARGET} NEG before save. Now {n_pos}/{n_neg}.")
                    continue
                width, height = camera.output_size
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                distance = f"{args.distance_cm:g}"
                dest = args.out_dir / f"session_{args.role}_{distance}cm_{stamp}.csv"
                write_session(
                    dest,
                    {
                        "data_kind": "real",
                        "role": args.role,
                        "distance_cm": distance,
                        "recorded_at": datetime.now().isoformat(timespec="seconds"),
                        "width": str(width),
                        "height": str(height),
                        "n_pos": str(n_pos),
                        "n_neg": str(n_neg),
                    },
                    frames,
                )
                print(f"Saved {dest}")
                return 0
            if active is not None:
                continue
            if baseline_frames < min_samples:
                continue
            if key in (ord("p"), ord("P"), ord("n"), ord("N")):
                kind = "pos" if key in (ord("p"), ord("P")) else "neg"
                if kind == "pos" and n_pos >= TARGET:
                    print("POS already has 20 segments.")
                    continue
                if kind == "neg" and n_neg >= TARGET:
                    print("NEG already has 20 segments.")
                    continue
                segment_id += 1
                duration = POS_SEC if kind == "pos" else NEG_SEC
                active = (kind, segment_id, now, duration)
    finally:
        tracker.close()
        camera.release()
        cv2.destroyAllWindows()


def _annotate(frame, baseline, need, n_pos, n_neg, active, now, role, distance) -> None:
    if baseline < need:
        status = f"baseline {baseline}/{need}  hold hand in view"
    elif active is None:
        status = f"{role} {distance:g}cm  POS {n_pos}/{TARGET}  NEG {n_neg}/{TARGET}  P/N/S/Q"
    else:
        kind, _sid, started, duration = active
        left = max(0.0, duration - (now - started))
        status = f"{kind.upper()} {left:.1f}s   POS {n_pos}/{TARGET} NEG {n_neg}/{TARGET}"
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 36), (0, 0, 0), -1)
    cv2.putText(frame, status, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)


if __name__ == "__main__":
    raise SystemExit(main())
