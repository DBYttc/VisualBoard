"""Coordinate descent, heatmap adoption, and the pinch baseline sweep."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional, Sequence

import yaml

from visualboard.core.config_loader import DepthPressSettings
from visualboard.eval.io_csv import Session
from visualboard.eval.metrics import (
    GridPoint,
    point_from_score,
    require_balanced,
    score_segments,
    select_operating_point,
)
from visualboard.eval.replay import replay_depth, replay_pinch


@dataclass(frozen=True, slots=True)
class Grids:
    enter_ratio: tuple[float, ...]
    exit_ratio: tuple[float, ...]
    stable_frames: tuple[int, ...]
    pinch_threshold_px: tuple[float, ...]
    init_enter: float
    init_exit: float
    init_stable: int
    max_rounds: int
    test_rate_min: float
    far_max: float
    pinch_stable_frames: int


@dataclass(frozen=True, slots=True)
class DescentResult:
    enter_ratio: float
    exit_ratio: float
    stable_frames: int
    rounds: int
    coordinate: GridPoint
    enter_curve: tuple[GridPoint, ...]
    stable_curve: tuple[GridPoint, ...]
    exit_curve: tuple[GridPoint, ...]
    enter_peak: GridPoint
    stable_peak: GridPoint
    exit_peak: GridPoint


def frange(start: float, stop: float, step: float) -> tuple[float, ...]:
    values: list[float] = []
    cursor = float(start)
    while cursor <= float(stop) + 1e-9:
        values.append(round(cursor, 4))
        cursor += float(step)
    return tuple(values)


def load_grids(protocol_path: Path, pinch_stable_frames: int) -> Grids:
    with protocol_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    grids = data["grids"]
    init = data["init"]
    satisfaction = data["satisfaction"]
    return Grids(
        enter_ratio=frange(
            grids["enter_ratio"]["start"],
            grids["enter_ratio"]["stop"],
            grids["enter_ratio"]["step"],
        ),
        exit_ratio=frange(
            grids["exit_ratio"]["start"],
            grids["exit_ratio"]["stop"],
            grids["exit_ratio"]["step"],
        ),
        stable_frames=tuple(int(v) for v in grids["stable_frames"]),
        pinch_threshold_px=frange(
            grids["pinch_threshold_px"]["start"],
            grids["pinch_threshold_px"]["stop"],
            grids["pinch_threshold_px"]["step"],
        ),
        init_enter=float(init["enter_ratio"]),
        init_exit=float(init["exit_ratio"]),
        init_stable=int(init["stable_frames"]),
        max_rounds=int(data.get("max_rounds", 2)),
        test_rate_min=float(satisfaction["test_rate_min"]),
        far_max=float(satisfaction["far_max"]),
        pinch_stable_frames=int(pinch_stable_frames),
    )


def depth_settings(
    base: DepthPressSettings, enter: float, exit_ratio: float, stable: int
) -> DepthPressSettings:
    return replace(
        base,
        enabled=True,
        source="finger_length",
        direction="far",
        baseline_mode="rolling",
        enter_ratio=float(enter),
        exit_ratio=float(exit_ratio),
        stable_frames=int(stable),
    )


def evaluate_depth(
    session: Session,
    base: DepthPressSettings,
    enter: float,
    exit_ratio: float,
    stable: int,
) -> GridPoint:
    if exit_ratio >= enter:
        raise ValueError("refusing to score exit_ratio >= enter_ratio")
    settings = depth_settings(base, enter, exit_ratio, stable)
    edges = replay_depth(session.frames, settings)
    score = score_segments(session.segments(), edges)
    return point_from_score(
        score,
        enter_ratio=float(enter),
        exit_ratio=float(exit_ratio),
        stable_frames=int(stable),
    )


def evaluate_pinch(
    session: Session, threshold_px: float, stable_frames: int
) -> GridPoint:
    edges = replay_pinch(session.frames, threshold_px, stable_frames)
    score = score_segments(session.segments(), edges)
    return point_from_score(score, pinch_threshold_px=float(threshold_px))


def _sweep_axis(
    session: Session,
    base: DepthPressSettings,
    axis: str,
    enter: float,
    exit_ratio: float,
    stable: int,
    grids: Grids,
) -> list[GridPoint]:
    points: list[GridPoint] = []
    if axis == "enter_ratio":
        values: Sequence[float] | Sequence[int] = grids.enter_ratio
    elif axis == "stable_frames":
        values = grids.stable_frames
    elif axis == "exit_ratio":
        values = grids.exit_ratio
    else:
        raise ValueError(axis)
    for value in values:
        e, x, s = enter, exit_ratio, stable
        if axis == "enter_ratio":
            e = float(value)
        elif axis == "stable_frames":
            s = int(value)
        else:
            x = float(value)
        if x >= e:
            continue
        points.append(evaluate_depth(session, base, e, x, s))
    if not points:
        raise ValueError(f"no legal points while sweeping {axis}")
    return points


def coordinate_descent(
    session: Session, base: DepthPressSettings, grids: Grids
) -> DescentResult:
    """Sweep enter, stable, exit, then enter again. At most ``max_rounds`` cycles."""
    require_balanced(session.segments())
    enter = grids.init_enter
    exit_ratio = grids.init_exit
    stable = grids.init_stable
    if exit_ratio >= enter:
        raise ValueError("protocol init has exit_ratio >= enter_ratio")

    last_enter_curve: list[GridPoint] = []
    stable_curve: list[GridPoint] = []
    exit_curve: list[GridPoint] = []
    enter_peak: Optional[GridPoint] = None
    stable_peak: Optional[GridPoint] = None
    exit_peak: Optional[GridPoint] = None
    rounds_done = 0

    for round_index in range(1, grids.max_rounds + 1):
        rounds_done = round_index
        first_enter = _sweep_axis(
            session, base, "enter_ratio", enter, exit_ratio, stable, grids
        )
        locked_enter = select_operating_point(first_enter).enter_ratio
        assert locked_enter is not None
        enter = locked_enter

        stable_curve = _sweep_axis(
            session, base, "stable_frames", enter, exit_ratio, stable, grids
        )
        stable_peak = select_operating_point(stable_curve)
        assert stable_peak.stable_frames is not None
        stable = stable_peak.stable_frames

        exit_curve = _sweep_axis(
            session, base, "exit_ratio", enter, exit_ratio, stable, grids
        )
        exit_peak = select_operating_point(exit_curve)
        assert exit_peak.exit_ratio is not None
        exit_ratio = exit_peak.exit_ratio

        last_enter_curve = _sweep_axis(
            session, base, "enter_ratio", enter, exit_ratio, stable, grids
        )
        enter_peak = select_operating_point(last_enter_curve)
        assert enter_peak.enter_ratio is not None
        if abs(enter_peak.enter_ratio - enter) < 1e-9:
            enter = enter_peak.enter_ratio
            break
        enter = enter_peak.enter_ratio

    assert enter_peak is not None and stable_peak is not None and exit_peak is not None
    coordinate = evaluate_depth(session, base, enter, exit_ratio, stable)
    return DescentResult(
        enter_ratio=enter,
        exit_ratio=exit_ratio,
        stable_frames=stable,
        rounds=rounds_done,
        coordinate=coordinate,
        enter_curve=tuple(last_enter_curve),
        stable_curve=tuple(stable_curve),
        exit_curve=tuple(exit_curve),
        enter_peak=enter_peak,
        stable_peak=stable_peak,
        exit_peak=exit_peak,
    )


def sweep_heatmap(
    session: Session, base: DepthPressSettings, stable: int, grids: Grids
) -> list[GridPoint]:
    points: list[GridPoint] = []
    for enter in grids.enter_ratio:
        for exit_ratio in grids.exit_ratio:
            if exit_ratio >= enter:
                continue
            points.append(evaluate_depth(session, base, enter, exit_ratio, stable))
    if not points:
        raise ValueError("heatmap has no legal cells")
    return points


def sweep_pinch(session: Session, grids: Grids) -> list[GridPoint]:
    return [
        evaluate_pinch(session, threshold, grids.pinch_stable_frames)
        for threshold in grids.pinch_threshold_px
    ]


def exceeds_local_gap(heatmap: GridPoint, coordinate: GridPoint) -> bool:
    """True when the heatmap cell beats coordinate descent by more than 1/N."""
    if heatmap.n != coordinate.n or heatmap.n <= 0:
        raise ValueError("heatmap and coordinate points must share N")
    return (heatmap.test_rate - coordinate.test_rate) > (1.0 / heatmap.n) + 1e-12


def satisfactory(point: GridPoint, grids: Grids) -> bool:
    return point.test_rate >= grids.test_rate_min and point.far <= grids.far_max
