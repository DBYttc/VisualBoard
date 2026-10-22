#!/usr/bin/env python3
"""Sweep a real session offline and write experiments/optimal.yaml.

Refuses any CSV whose header is not data_kind=real. Does not invent trials.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Iterable, Optional

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from visualboard.core.config_loader import load_settings  # noqa: E402
from visualboard.eval.io_csv import read_session  # noqa: E402
from visualboard.eval.metrics import GridPoint, require_balanced, select_operating_point  # noqa: E402
from visualboard.eval.results import dump_optimal, point_dict, write_overlay  # noqa: E402
from visualboard.eval.sweep import (  # noqa: E402
    coordinate_descent,
    evaluate_depth,
    evaluate_pinch,
    exceeds_local_gap,
    load_grids,
    satisfactory,
    sweep_heatmap,
    sweep_pinch,
)

SWEEP_FIELDS = [
    "enter_ratio",
    "exit_ratio",
    "stable_frames",
    "pinch_threshold_px",
    "tp",
    "fn",
    "fp",
    "tn",
    "test_rate",
    "recall",
    "far",
    "latency_mean",
    "n",
]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True, help="select 会话 CSV")
    parser.add_argument("--transfer", type=Path, default=None, help="第二距离 CSV，不参与选参")
    parser.add_argument(
        "--protocol", type=Path, default=ROOT / "experiments" / "protocol.yaml"
    )
    parser.add_argument("--sweep-dir", type=Path, default=ROOT / "experiments" / "sweeps")
    parser.add_argument("--optimal", type=Path, default=ROOT / "experiments" / "optimal.yaml")
    parser.add_argument(
        "--overlay", type=Path, default=ROOT / "config" / "optimal_overlay.yaml"
    )
    parser.add_argument(
        "--trials-each",
        type=int,
        default=None,
        help="正负段数量。默认读协议里的 trials_each",
    )
    args = parser.parse_args(argv)

    settings = load_settings(ROOT / "config")
    grids = load_grids(args.protocol, settings.interaction.pinch_stable_frames)
    trials_each = args.trials_each
    if trials_each is None:
        with args.protocol.open(encoding="utf-8") as handle:
            trials_each = int(yaml.safe_load(handle)["trials_each"])

    select = _load_role(args.raw, "select", trials_each)
    transfer = None
    if args.transfer is not None:
        transfer = _load_role(args.transfer, "transfer", trials_each)

    descent = coordinate_descent(select, settings.depth_press, grids)
    heatmap = sweep_heatmap(select, settings.depth_press, descent.stable_frames, grids)
    heatmap_point = select_operating_point(heatmap)
    pinch_points = sweep_pinch(select, grids)
    pinch_point = select_operating_point(pinch_points)
    local = exceeds_local_gap(heatmap_point, descent.coordinate)
    adopted_ok = satisfactory(heatmap_point, grids)

    transfer_block: dict = {"collected": False}
    if transfer is not None:
        depth_t = evaluate_depth(
            transfer,
            settings.depth_press,
            heatmap_point.enter_ratio,
            heatmap_point.exit_ratio,
            descent.stable_frames,
        )
        pinch_t = evaluate_pinch(
            transfer,
            pinch_point.pinch_threshold_px,
            grids.pinch_stable_frames,
        )
        transfer_block = {
            "collected": True,
            "raw_path": _rel(transfer.path),
            "distance_cm": transfer.meta.get("distance_cm", ""),
            "depth": _labeled(depth_t, param_text=_depth_text(depth_t)),
            "pinch": _labeled(
                pinch_t, param_text=f"pinch_threshold_px={pinch_t.pinch_threshold_px}"
            ),
        }

    payload = {
        "data_kind": "real",
        "raw_path": _rel(select.path),
        "distance_cm": select.meta.get("distance_cm", ""),
        "recorded_at": select.meta.get("recorded_at", ""),
        "width": select.meta.get("width", ""),
        "height": select.meta.get("height", ""),
        "n_pos": trials_each,
        "n_neg": trials_each,
        "rounds": descent.rounds,
        "satisfaction_rule": {
            "test_rate_min": grids.test_rate_min,
            "far_max": grids.far_max,
        },
        "coordinate": _labeled(descent.coordinate, param_text=_depth_text(descent.coordinate)),
        "peaks": {
            "enter_ratio": _labeled(
                descent.enter_peak, param_text=f"enter_ratio={descent.enter_peak.enter_ratio}"
            ),
            "stable_frames": _labeled(
                descent.stable_peak,
                param_text=f"stable_frames={descent.stable_peak.stable_frames}",
            ),
            "exit_ratio": _labeled(
                descent.exit_peak, param_text=f"exit_ratio={descent.exit_peak.exit_ratio}"
            ),
        },
        "heatmap_adopted": _labeled(heatmap_point, param_text=_depth_text(heatmap_point)),
        "local_optimum": bool(local),
        "adopted": _labeled(
            heatmap_point,
            param_text=_depth_text(heatmap_point),
            satisfactory=adopted_ok,
            stable_frames=descent.stable_frames,
        ),
        "pinch": _labeled(
            pinch_point, param_text=f"pinch_threshold_px={pinch_point.pinch_threshold_px}"
        ),
        "transfer": transfer_block,
        "curves": {
            "enter_ratio": [_labeled(p) for p in descent.enter_curve],
            "stable_frames": [_labeled(p) for p in descent.stable_curve],
            "exit_ratio": [_labeled(p) for p in descent.exit_curve],
        },
    }
    # Adopted stable_frames is the coordinate-descent value. The heatmap cell
    # was already scored at that stable_frames, so the metric row matches.
    payload["adopted"]["stable_frames"] = descent.stable_frames
    payload["heatmap_adopted"]["stable_frames"] = descent.stable_frames

    args.sweep_dir.mkdir(parents=True, exist_ok=True)
    _write_curve(args.sweep_dir / "enter_ratio.csv", descent.enter_curve)
    _write_curve(args.sweep_dir / "stable_frames.csv", descent.stable_curve)
    _write_curve(args.sweep_dir / "exit_ratio.csv", descent.exit_curve)
    _write_curve(args.sweep_dir / "heatmap.csv", heatmap)
    _write_curve(args.sweep_dir / "pinch.csv", pinch_points)
    manifest = {
        "data_kind": "real",
        "raw_path": payload["raw_path"],
        "transfer_path": None if transfer is None else _rel(transfer.path),
        "optimal": str(args.optimal),
    }
    with (args.sweep_dir / "manifest.yaml").open("w", encoding="utf-8") as handle:
        yaml.safe_dump(manifest, handle, allow_unicode=True, sort_keys=False)

    dump_optimal(args.optimal, payload)
    write_overlay(args.overlay, payload)
    print(f"Wrote {args.optimal}")
    print(f"Adopted enter_ratio={payload['adopted']['enter_ratio']} "
          f"exit_ratio={payload['adopted']['exit_ratio']} "
          f"stable_frames={payload['adopted']['stable_frames']}")
    print("Next: python scripts/plot_curves.py")
    print("Then: python scripts/fill_report.py")
    return 0


def _load_role(path: Path, role: str, trials_each: int):
    session = read_session(path, require_data_kind_real=True)
    if session.meta.get("role") != role:
        raise SystemExit(f"{path} role is {session.meta.get('role')!r}, want {role!r}")
    n_pos, n_neg = require_balanced(session.segments())
    if n_pos != trials_each or n_neg != trials_each:
        raise SystemExit(
            f"{path} has {n_pos} POS and {n_neg} NEG, protocol wants {trials_each} each"
        )
    return session


def _rel(path: Optional[Path]) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _depth_text(point: GridPoint) -> str:
    return (
        f"enter_ratio={point.enter_ratio}, exit_ratio={point.exit_ratio}, "
        f"stable_frames={point.stable_frames}"
    )


def _labeled(point: GridPoint, **extra: object) -> dict:
    return point_dict(point, **extra)


def _write_curve(path: Path, points: Iterable[GridPoint]) -> None:
    rows = [point_dict(point) for point in points]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SWEEP_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row[key] is None else row[key] for key in SWEEP_FIELDS})


if __name__ == "__main__":
    raise SystemExit(main())
