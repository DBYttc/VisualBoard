"""In-memory fixtures for the sweep rule. These rows are not experiment data."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from visualboard.core.config_loader import DepthPressSettings
from visualboard.eval.io_csv import FrameRow, Session, read_session, write_session
from visualboard.eval.metrics import (
    GridPoint,
    Segment,
    score_segments,
    select_operating_point,
)
from visualboard.eval.replay import replay_depth, replay_pinch
from visualboard.eval.results import dump_optimal, fill_report_text
from visualboard.eval.sweep import Grids, coordinate_descent
from visualboard.vision.landmarks import FINGER_NAMES

ROOT = Path(__file__).resolve().parents[1]


def _gp(**kwargs) -> GridPoint:
    values = dict(
        tp=18,
        fn=2,
        fp=2,
        tn=18,
        test_rate=0.9,
        recall=0.9,
        far=0.1,
        latency_mean=0.1,
        enter_ratio=1.12,
        exit_ratio=1.06,
        stable_frames=4,
        pinch_threshold_px=None,
    )
    values.update(kwargs)
    return GridPoint(**values)


def test_unique_peak_is_the_highest_test_rate():
    # N=40, 1/N=0.025. 0.90 and 0.85 differ by more than that.
    chosen = select_operating_point(
        [
            _gp(enter_ratio=1.06, exit_ratio=1.02, test_rate=0.80, tp=16, fn=4, fp=4, tn=16),
            _gp(enter_ratio=1.12, test_rate=0.90, tp=18, fn=2, fp=2, tn=18),
            _gp(enter_ratio=1.18, test_rate=0.85, tp=17, fn=3, fp=3, tn=17, far=0.0),
        ]
    )
    assert chosen.enter_ratio == 1.12


def test_plateau_prefers_lower_far_then_larger_enter():
    chosen = select_operating_point(
        [
            _gp(enter_ratio=1.06, exit_ratio=1.02, test_rate=0.90, far=0.30, fp=6, tn=14),
            _gp(enter_ratio=1.12, test_rate=0.88, far=0.05, fp=1, tn=19, tp=17, fn=3),
        ]
    )
    assert chosen.enter_ratio == 1.12

    tied = select_operating_point(
        [
            _gp(enter_ratio=1.10, test_rate=0.90),
            _gp(enter_ratio=1.18, test_rate=0.90),
        ]
    )
    assert tied.enter_ratio == 1.18


def test_plateau_prefers_shorter_latency_before_larger_enter():
    chosen = select_operating_point(
        [
            _gp(enter_ratio=1.06, exit_ratio=1.02, test_rate=0.90, latency_mean=0.05),
            _gp(enter_ratio=1.20, test_rate=0.90, latency_mean=0.40),
        ]
    )
    assert chosen.enter_ratio == 1.06


def test_plateau_prefers_larger_stable_and_smaller_exit():
    stable = select_operating_point(
        [
            _gp(stable_frames=2, test_rate=0.90, latency_mean=0.2),
            _gp(stable_frames=6, test_rate=0.90, latency_mean=0.2),
        ]
    )
    assert stable.stable_frames == 6

    exit_ratio = select_operating_point(
        [
            _gp(enter_ratio=1.20, exit_ratio=1.10, test_rate=0.90, latency_mean=0.2),
            _gp(enter_ratio=1.20, exit_ratio=1.02, test_rate=0.90, latency_mean=0.2),
        ]
    )
    assert exit_ratio.exit_ratio == 1.02


def test_illegal_exit_is_discarded_even_with_a_higher_rate():
    chosen = select_operating_point(
        [
            _gp(enter_ratio=1.10, exit_ratio=1.10, test_rate=0.99),
            _gp(enter_ratio=1.10, exit_ratio=1.02, test_rate=0.70, tp=14, fn=6, fp=6, tn=14),
        ]
    )
    assert chosen.exit_ratio == 1.02


def test_score_counts_one_segment_once():
    segments = [
        Segment("pos", 0.0, 1.0, 1),
        Segment("pos", 2.0, 3.0, 2),
        Segment("neg", 4.0, 5.0, 3),
        Segment("neg", 6.0, 7.0, 4),
    ]
    score = score_segments(segments, [0.2, 0.4, 4.2])
    assert (score.tp, score.fn, score.fp, score.tn) == (1, 1, 1, 1)
    assert score.test_rate == 0.5
    assert score.latency_mean == pytest.approx(0.2)


def test_replay_depth_rising_edge_on_shrink_only():
    frames = []
    t = 0.0
    for _ in range(8):
        frames.append(_row(t, "idle", None, 100.0, 80.0))
        t += 0.05
    for _ in range(6):
        frames.append(_row(t, "pos", 1, 70.0, 80.0))
        t += 0.05
    for _ in range(6):
        frames.append(_row(t, "neg", 2, 100.0, 80.0))
        t += 0.05
    session = Session(meta={"data_kind": "real"}, frames=frames)
    settings = DepthPressSettings(
        enabled=True,
        source="finger_length",
        direction="far",
        baseline_mode="rolling",
        enter_ratio=1.12,
        exit_ratio=1.06,
        stable_frames=2,
        baseline_samples=20,
        min_samples=5,
    )
    edges = replay_depth(frames, settings)
    score = score_segments(session.segments(), edges)
    assert score.tp == 1
    assert score.fn == 0
    assert score.fp == 0
    assert score.tn == 1
    assert len(edges) == 1


def test_replay_pinch_needs_stable_frames():
    frames = [
        _row(0.0, "pos", 1, 100.0, 80.0),
        _row(0.1, "pos", 1, 100.0, 20.0),
        _row(0.2, "pos", 1, 100.0, 20.0),
        _row(0.3, "neg", 2, 100.0, 80.0),
    ]
    assert replay_pinch(frames, 45.0, 3) == []
    edges = replay_pinch(frames, 45.0, 2)
    assert edges == [0.2]


def test_coordinate_descent_on_flat_fixture_picks_conservative_end():
    frames = []
    t = 0.0
    for _ in range(10):
        frames.append(_row(t, "idle", None, 100.0, 80.0))
        t += 0.1
    for _ in range(6):
        frames.append(_row(t, "pos", 1, 70.0, 80.0))
        t += 0.1
    for _ in range(4):
        frames.append(_row(t, "idle", None, 100.0, 80.0))
        t += 0.1
    for _ in range(6):
        frames.append(_row(t, "neg", 2, 100.0, 80.0))
        t += 0.1
    session = Session(meta={"data_kind": "real", "role": "select"}, frames=frames)
    grids = Grids(
        enter_ratio=(1.08, 1.12, 1.20),
        exit_ratio=(1.02, 1.06),
        stable_frames=(1, 2),
        pinch_threshold_px=(40.0,),
        init_enter=1.12,
        init_exit=1.06,
        init_stable=1,
        max_rounds=2,
        test_rate_min=0.85,
        far_max=0.15,
        pinch_stable_frames=3,
    )
    base = DepthPressSettings(
        enabled=True,
        source="finger_length",
        direction="far",
        baseline_mode="rolling",
        enter_ratio=1.12,
        exit_ratio=1.06,
        stable_frames=1,
        baseline_samples=20,
        min_samples=5,
    )
    result = coordinate_descent(session, base, grids)
    assert result.enter_ratio == 1.20
    assert result.exit_ratio == 1.02
    assert result.stable_frames == 1
    assert result.exit_ratio < result.enter_ratio
    assert result.coordinate.test_rate == 1.0


def test_session_roundtrip_and_reject_synthetic(tmp_path: Path):
    frames = [_row(0.0, "idle", None, 100.0, 80.0), _row(0.1, "pos", 1, None, None)]
    dest = tmp_path / "session.csv"
    write_session(
        dest,
        {
            "data_kind": "real",
            "role": "select",
            "distance_cm": "40",
            "recorded_at": "2026-10-21T20:00:00",
            "width": "1280",
            "height": "720",
            "n_pos": "1",
            "n_neg": "1",
        },
        frames,
    )
    loaded = read_session(dest)
    assert loaded.data_kind == "real"
    assert loaded.frames[1].lengths["index"] is None
    assert loaded.frames[1].segment_id == 1
    assert not str(dest).startswith(str(ROOT / "experiments" / "raw"))

    fake = tmp_path / "synthetic.csv"
    text = dest.read_text(encoding="utf-8").replace("data_kind=real", "data_kind=synthetic")
    fake.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="real"):
        read_session(fake)
    with pytest.raises(ValueError, match="real"):
        dump_optimal(tmp_path / "optimal.yaml", {"data_kind": "synthetic"})


def test_plot_refuses_without_real_sweep(tmp_path: Path):
    module = _load_script("plot_curves.py")
    figures = tmp_path / "figures"
    code = module.main(["--sweep-dir", str(tmp_path), "--figures-dir", str(figures), "--optimal", str(tmp_path / "missing.yaml")])
    assert code != 0
    assert list(figures.glob("*.png")) == []


def test_fill_report_rejects_synthetic_and_splices_real(tmp_path: Path):
    module = _load_script("fill_report.py")
    optimal = tmp_path / "optimal.yaml"
    optimal.write_text("data_kind: synthetic\n", encoding="utf-8")
    report = tmp_path / "report.md"
    report.write_text("keep\n", encoding="utf-8")
    assert module.main(["--optimal", str(optimal), "--report", str(report)]) != 0
    assert report.read_text(encoding="utf-8") == "keep\n"

    payload = _real_payload()
    template = (
        "before\n<!-- vb:curves:start -->\n未采集\n<!-- vb:curves:end -->\n"
        "mid\n<!-- vb:conclusions:start -->\n未采集\n<!-- vb:conclusions:end -->\n"
    )
    updated = fill_report_text(template, payload, tmp_path / "no-figures")
    assert "<!-- vb:conclusions:start -->\n未采集\n" not in updated
    assert "enter_ratio=1.12" in updated
    assert "第二距离：未采集" in updated
    assert "尚未生成" in updated
    assert "before" in updated


def _row(timestamp, label, segment_id, length, pinch) -> FrameRow:
    lengths = {name: length for name in FINGER_NAMES}
    return FrameRow(timestamp, label, segment_id, lengths, pinch)


def _load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _real_payload() -> dict:
    row = {
        "enter_ratio": 1.12,
        "exit_ratio": 1.06,
        "stable_frames": 4,
        "pinch_threshold_px": None,
        "tp": 18,
        "fn": 2,
        "fp": 2,
        "tn": 18,
        "test_rate": 0.9,
        "recall": 0.9,
        "far": 0.1,
        "latency_mean": 0.1,
        "n": 40,
        "param_text": "enter_ratio=1.12, exit_ratio=1.06, stable_frames=4",
        "satisfactory": True,
    }
    pinch = dict(row)
    pinch.update(
        {
            "pinch_threshold_px": 45,
            "enter_ratio": None,
            "exit_ratio": None,
            "stable_frames": None,
            "param_text": "pinch_threshold_px=45",
        }
    )
    peak_enter = dict(row)
    peak_enter["param_text"] = "enter_ratio=1.12"
    return {
        "data_kind": "real",
        "raw_path": "experiments/raw/session_select_40cm_example.csv",
        "distance_cm": "40",
        "n_pos": 20,
        "n_neg": 20,
        "rounds": 1,
        "coordinate": row,
        "peaks": {
            "enter_ratio": peak_enter,
            "stable_frames": {**row, "param_text": "stable_frames=4"},
            "exit_ratio": {**row, "param_text": "exit_ratio=1.06"},
        },
        "heatmap_adopted": row,
        "local_optimum": False,
        "adopted": row,
        "pinch": pinch,
        "transfer": {"collected": False},
        "curves": {
            "enter_ratio": [
                {"enter_ratio": 1.06, "test_rate": 0.8, "recall": 1.0, "far": 0.4},
                {"enter_ratio": 1.12, "test_rate": 0.9, "recall": 0.9, "far": 0.1},
                {"enter_ratio": 1.20, "test_rate": 0.7, "recall": 0.5, "far": 0.0},
            ]
        },
    }
