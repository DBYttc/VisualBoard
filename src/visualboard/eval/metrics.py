"""Segment scores and the pre-registered operating-point rule.

测试率 = (TP + TN) / N，N = 正样本段数 + 负样本段数。
最优刻度是网格上测试率最高的实测点，不插值。
最高与次高相差不超过 1/N 时视为平台，平台内依次取更低 FAR、更短延迟、
更大的 enter_ratio、更大的 stable_frames、更小的 exit_ratio。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True, slots=True)
class Segment:
    kind: str  # "pos" or "neg"
    start: float
    end: float
    segment_id: int


@dataclass(frozen=True, slots=True)
class SegmentScore:
    tp: int
    fn: int
    fp: int
    tn: int
    latency_mean: Optional[float]

    @property
    def n_pos(self) -> int:
        return self.tp + self.fn

    @property
    def n_neg(self) -> int:
        return self.fp + self.tn

    @property
    def n(self) -> int:
        return self.n_pos + self.n_neg

    @property
    def test_rate(self) -> float:
        if self.n == 0:
            return 0.0
        return (self.tp + self.tn) / self.n

    @property
    def recall(self) -> float:
        if self.n_pos == 0:
            return 0.0
        return self.tp / self.n_pos

    @property
    def far(self) -> float:
        if self.n_neg == 0:
            return 0.0
        return self.fp / self.n_neg


@dataclass(frozen=True, slots=True)
class GridPoint:
    tp: int
    fn: int
    fp: int
    tn: int
    test_rate: float
    recall: float
    far: float
    latency_mean: Optional[float]
    enter_ratio: Optional[float] = None
    exit_ratio: Optional[float] = None
    stable_frames: Optional[int] = None
    pinch_threshold_px: Optional[float] = None

    @property
    def n(self) -> int:
        return self.tp + self.fn + self.fp + self.tn


def score_segments(segments: Sequence[Segment], edges: Sequence[float]) -> SegmentScore:
    """Score rising edges against labeled segments. Idle time is not passed in.

    A positive segment with at least one edge in ``[start, end]`` is one TP.
    Extra edges inside that segment are not counted again. A negative segment
    with any edge is one FP.
    """
    tp = fn = fp = tn = 0
    latencies: list[float] = []
    for seg in segments:
        if seg.kind not in ("pos", "neg"):
            raise ValueError(f"segment kind must be pos or neg, got {seg.kind}")
        if seg.end < seg.start:
            raise ValueError(f"segment {seg.segment_id} ends before it starts")
        hits = [t for t in edges if seg.start <= t <= seg.end]
        if seg.kind == "pos":
            if hits:
                tp += 1
                latencies.append(min(hits) - seg.start)
            else:
                fn += 1
        elif hits:
            fp += 1
        else:
            tn += 1
    latency = (sum(latencies) / len(latencies)) if latencies else None
    return SegmentScore(tp=tp, fn=fn, fp=fp, tn=tn, latency_mean=latency)


def point_from_score(score: SegmentScore, **params: object) -> GridPoint:
    return GridPoint(
        tp=score.tp,
        fn=score.fn,
        fp=score.fp,
        tn=score.tn,
        test_rate=score.test_rate,
        recall=score.recall,
        far=score.far,
        latency_mean=score.latency_mean,
        enter_ratio=params.get("enter_ratio"),  # type: ignore[arg-type]
        exit_ratio=params.get("exit_ratio"),  # type: ignore[arg-type]
        stable_frames=params.get("stable_frames"),  # type: ignore[arg-type]
        pinch_threshold_px=params.get("pinch_threshold_px"),  # type: ignore[arg-type]
    )


def is_legal(point: GridPoint) -> bool:
    """exit_ratio >= enter_ratio is not a hysteresis pair and is discarded."""
    if point.enter_ratio is None or point.exit_ratio is None:
        return True
    return point.exit_ratio < point.enter_ratio


def select_operating_point(points: Sequence[GridPoint]) -> GridPoint:
    """Pick the grid point required by experiments/protocol.yaml.

    Illegal exit/enter pairs are removed before the test-rate comparison.
    """
    legal = [p for p in points if is_legal(p)]
    if not legal:
        raise ValueError("no legal grid points to select from")
    n_values = {p.n for p in legal}
    if len(n_values) != 1:
        raise ValueError(f"grid points must share one N, got {sorted(n_values)}")
    n = legal[0].n
    if n <= 0:
        raise ValueError("N must be positive")
    band = 1.0 / n
    top = max(p.test_rate for p in legal)
    plateau = [p for p in legal if top - p.test_rate <= band + 1e-12]
    return min(plateau, key=_plateau_key)


def _plateau_key(point: GridPoint) -> tuple:
    latency = point.latency_mean if point.latency_mean is not None else float("inf")
    enter = point.enter_ratio if point.enter_ratio is not None else float("-inf")
    stable = point.stable_frames if point.stable_frames is not None else float("-inf")
    exit_ratio = point.exit_ratio if point.exit_ratio is not None else float("inf")
    pinch = (
        point.pinch_threshold_px
        if point.pinch_threshold_px is not None
        else float("inf")
    )
    # FAR 更低、延迟更短、更大的 enter、更大的 stable、更小的 exit。
    # 捏合阈值只在前几项全部相同时取更小值（更不容易误触发）。
    return (point.far, latency, -enter, -stable, exit_ratio, pinch)


def require_balanced(segments: Sequence[Segment]) -> tuple[int, int]:
    n_pos = sum(1 for seg in segments if seg.kind == "pos")
    n_neg = sum(1 for seg in segments if seg.kind == "neg")
    if n_pos <= 0 or n_pos != n_neg:
        raise ValueError(
            f"POS and NEG segment counts must be equal and non-zero, got {n_pos} and {n_neg}"
        )
    return n_pos, n_neg
