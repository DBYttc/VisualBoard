"""Read and write recorded sessions. Real sessions are the only report source."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, TextIO

from visualboard.eval.metrics import Segment
from visualboard.vision.landmarks import FINGER_NAMES

LENGTH_COLUMNS = [f"len_{name}" for name in FINGER_NAMES]
COLUMNS = [
    "timestamp",
    "label",
    "segment_id",
    *LENGTH_COLUMNS,
    "pinch_distance_px",
]


@dataclass
class FrameRow:
    timestamp: float
    label: str
    segment_id: Optional[int]
    lengths: Dict[str, Optional[float]]
    pinch_distance_px: Optional[float]


@dataclass
class Session:
    meta: dict[str, str]
    frames: list[FrameRow] = field(default_factory=list)
    path: Optional[Path] = None

    @property
    def data_kind(self) -> str:
        return self.meta.get("data_kind", "")

    def segments(self) -> list[Segment]:
        grouped: dict[int, list[FrameRow]] = {}
        for frame in self.frames:
            if frame.label not in ("pos", "neg") or frame.segment_id is None:
                continue
            grouped.setdefault(frame.segment_id, []).append(frame)
        segments: list[Segment] = []
        for segment_id, rows in grouped.items():
            kind = rows[0].label
            if any(row.label != kind for row in rows):
                raise ValueError(f"segment {segment_id} mixes labels")
            segments.append(
                Segment(
                    kind=kind,
                    start=rows[0].timestamp,
                    end=rows[-1].timestamp,
                    segment_id=segment_id,
                )
            )
        segments.sort(key=lambda seg: (seg.start, seg.segment_id))
        return segments


def require_real(session: Session) -> None:
    if session.data_kind != "real":
        raise ValueError(
            f"refusing session {session.path}: data_kind={session.data_kind!r}, want 'real'"
        )


def write_session(path: Path, meta: dict[str, str], frames: list[FrameRow]) -> None:
    if meta.get("data_kind") != "real":
        raise ValueError("refusing to write a session whose data_kind is not real")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for key in (
            "data_kind",
            "role",
            "distance_cm",
            "recorded_at",
            "width",
            "height",
            "n_pos",
            "n_neg",
        ):
            if key in meta:
                handle.write(f"# {key}={meta[key]}\n")
        for key, value in meta.items():
            if key not in {
                "data_kind",
                "role",
                "distance_cm",
                "recorded_at",
                "width",
                "height",
                "n_pos",
                "n_neg",
            }:
                handle.write(f"# {key}={value}\n")
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for frame in frames:
            row = {
                "timestamp": f"{frame.timestamp:.6f}",
                "label": frame.label,
                "segment_id": "" if frame.segment_id is None else str(frame.segment_id),
                "pinch_distance_px": _fmt(frame.pinch_distance_px),
            }
            for name in FINGER_NAMES:
                row[f"len_{name}"] = _fmt(frame.lengths.get(name))
            writer.writerow(row)


def read_session(path: Path, *, require_data_kind_real: bool = True) -> Session:
    meta: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        _read_meta(handle, meta)
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no CSV header")
        missing = [name for name in COLUMNS if name not in reader.fieldnames]
        if missing:
            raise ValueError(f"{path} missing columns: {missing}")
        frames = [_parse_row(row) for row in reader]
    session = Session(meta=meta, frames=frames, path=path)
    if require_data_kind_real:
        require_real(session)
    return session


def _read_meta(handle: TextIO, meta: dict[str, str]) -> None:
    while True:
        pos = handle.tell()
        line = handle.readline()
        if line == "":
            return
        stripped = line.strip()
        if stripped == "":
            continue
        if not stripped.startswith("#"):
            handle.seek(pos)
            return
        body = stripped[1:].strip()
        if "=" not in body:
            continue
        key, value = body.split("=", 1)
        meta[key.strip()] = value.strip()


def _parse_row(row: dict[str, str]) -> FrameRow:
    label = (row.get("label") or "").strip()
    if label not in ("idle", "pos", "neg"):
        raise ValueError(f"bad label {label!r}")
    segment_text = (row.get("segment_id") or "").strip()
    segment_id = int(segment_text) if segment_text else None
    if label in ("pos", "neg") and segment_id is None:
        raise ValueError("pos/neg rows need a segment_id")
    lengths = {name: _opt_float(row.get(f"len_{name}")) for name in FINGER_NAMES}
    return FrameRow(
        timestamp=float(row["timestamp"]),
        label=label,
        segment_id=segment_id,
        lengths=lengths,
        pinch_distance_px=_opt_float(row.get("pinch_distance_px")),
    )


def _opt_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = value.strip()
    if text == "":
        return None
    return float(text)


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"
