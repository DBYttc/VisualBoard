#!/usr/bin/env python3
"""Plot test-rate curves from a real sweep. Exits non-zero when the sweep is absent."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Optional

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep-dir", type=Path, default=ROOT / "experiments" / "sweeps")
    parser.add_argument("--figures-dir", type=Path, default=ROOT / "experiments" / "figures")
    parser.add_argument("--optimal", type=Path, default=ROOT / "experiments" / "optimal.yaml")
    args = parser.parse_args(argv)

    manifest_path = args.sweep_dir / "manifest.yaml"
    if not manifest_path.is_file():
        print(f"No sweep manifest at {manifest_path}. Refusing to draw a placeholder.", file=sys.stderr)
        return 1
    with manifest_path.open(encoding="utf-8") as handle:
        manifest = yaml.safe_load(handle) or {}
    if manifest.get("data_kind") != "real":
        print("Sweep manifest data_kind is not real. Refusing to plot.", file=sys.stderr)
        return 1
    if not args.optimal.is_file():
        print(f"Missing {args.optimal}. Refusing to plot.", file=sys.stderr)
        return 1
    with args.optimal.open(encoding="utf-8") as handle:
        optimal = yaml.safe_load(handle) or {}
    if optimal.get("data_kind") != "real":
        print("optimal.yaml data_kind is not real. Refusing to plot.", file=sys.stderr)
        return 1

    needed = ["enter_ratio.csv", "stable_frames.csv", "exit_ratio.csv", "heatmap.csv"]
    for name in needed:
        if not (args.sweep_dir / name).is_file():
            print(f"Missing {args.sweep_dir / name}. Refusing to plot.", file=sys.stderr)
            return 1

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _use_cjk_font(plt)
    args.figures_dir.mkdir(parents=True, exist_ok=True)

    _plot_line(
        plt,
        _read_csv(args.sweep_dir / "enter_ratio.csv"),
        "enter_ratio",
        optimal["peaks"]["enter_ratio"]["enter_ratio"],
        "enter_ratio",
        args.figures_dir / "E2_enter_ratio.png",
    )
    _plot_line(
        plt,
        _read_csv(args.sweep_dir / "stable_frames.csv"),
        "stable_frames",
        optimal["peaks"]["stable_frames"]["stable_frames"],
        "stable_frames",
        args.figures_dir / "E3_stable_frames.png",
    )
    _plot_line(
        plt,
        _read_csv(args.sweep_dir / "exit_ratio.csv"),
        "exit_ratio",
        optimal["peaks"]["exit_ratio"]["exit_ratio"],
        "exit_ratio",
        args.figures_dir / "E4_exit_ratio.png",
    )
    _plot_heatmap(
        plt,
        _read_csv(args.sweep_dir / "heatmap.csv"),
        float(optimal["heatmap_adopted"]["enter_ratio"]),
        float(optimal["heatmap_adopted"]["exit_ratio"]),
        args.figures_dir / "E5_enter_x_exit_heatmap.png",
    )
    print(f"Wrote figures under {args.figures_dir}")
    return 0


def _use_cjk_font(plt) -> None:
    from matplotlib import font_manager

    for name in ("Microsoft YaHei", "SimHei"):
        if any(name.lower() in found.name.lower() for found in font_manager.fontManager.ttflist):
            plt.rcParams["font.sans-serif"] = [name]
            plt.rcParams["axes.unicode_minus"] = False
            return


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _plot_line(plt, rows: list[dict[str, str]], x_key: str, marked, xlabel: str, dest: Path) -> None:
    xs = [float(row[x_key]) for row in rows]
    ys = [float(row["test_rate"]) for row in rows]
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    ax.plot(xs, ys, marker="o")
    ax.axvline(float(marked), color="0.4", linestyle="--", label=f"选出 {xlabel}={marked}")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("测试率")
    ax.set_ylim(-0.05, 1.05)
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(dest, dpi=140)
    plt.close(fig)


def _plot_heatmap(plt, rows: list[dict[str, str]], enter: float, exit_ratio: float, dest: Path) -> None:
    enters = sorted({float(row["enter_ratio"]) for row in rows})
    exits = sorted({float(row["exit_ratio"]) for row in rows})
    grid = [[float("nan") for _ in enters] for _ in exits]
    lookup = {
        (float(row["enter_ratio"]), float(row["exit_ratio"])): float(row["test_rate"])
        for row in rows
    }
    for y, exit_value in enumerate(exits):
        for x, enter_value in enumerate(enters):
            if (enter_value, exit_value) in lookup:
                grid[y][x] = lookup[(enter_value, exit_value)]
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    image = ax.imshow(grid, origin="lower", aspect="auto", vmin=0.0, vmax=1.0)
    ax.set_xticks(range(len(enters)), [f"{v:.2f}" for v in enters], rotation=45, ha="right")
    ax.set_yticks(range(len(exits)), [f"{v:.2f}" for v in exits])
    ax.set_xlabel("enter_ratio")
    ax.set_ylabel("exit_ratio")
    if enter in enters and exit_ratio in exits:
        ax.scatter([enters.index(enter)], [exits.index(exit_ratio)], c="white", marker="x", s=80)
    fig.colorbar(image, ax=ax, label="测试率")
    fig.tight_layout()
    fig.savefig(dest, dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
