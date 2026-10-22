"""Serialize a real sweep and splice it into the practice report.

Numbers are copied from measured grid points. This module refuses payloads
whose ``data_kind`` is anything other than ``real``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from visualboard.eval.metrics import GridPoint

CURVES_START = "<!-- vb:curves:start -->"
CURVES_END = "<!-- vb:curves:end -->"
CONCLUSIONS_START = "<!-- vb:conclusions:start -->"
CONCLUSIONS_END = "<!-- vb:conclusions:end -->"

REPORT_NAME = "2、计科xx班组长学号组长姓名计算机系统项目综合实践报告报告题目.md"


def point_dict(point: GridPoint, **extra: object) -> dict:
    payload = {
        "enter_ratio": point.enter_ratio,
        "exit_ratio": point.exit_ratio,
        "stable_frames": point.stable_frames,
        "pinch_threshold_px": point.pinch_threshold_px,
        "tp": point.tp,
        "fn": point.fn,
        "fp": point.fp,
        "tn": point.tn,
        "test_rate": round(point.test_rate, 6),
        "recall": round(point.recall, 6),
        "far": round(point.far, 6),
        "latency_mean": None
        if point.latency_mean is None
        else round(point.latency_mean, 6),
        "n": point.n,
    }
    payload.update(extra)
    return payload


def require_real_payload(payload: dict) -> None:
    if payload.get("data_kind") != "real":
        raise ValueError(
            "refusing to write experiment results unless data_kind is real"
        )


def dump_optimal(path: Path, payload: dict) -> None:
    require_real_payload(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(
            "# Generated from a data_kind=real session. Do not hand-edit the numbers.\n"
        )
        yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)


def write_overlay(path: Path, payload: dict) -> None:
    require_real_payload(payload)
    adopted = payload["adopted"]
    lines = [
        f"# data_kind=real",
        f"# source_csv={payload['raw_path']}",
        "# This file is NOT loaded automatically.",
        "# Copy the keys below into config/local.yaml to opt in.",
        "depth_press:",
        "  enabled: true",
        "  source: finger_length",
        "  direction: far",
        f"  enter_ratio: {adopted['enter_ratio']}",
        f"  exit_ratio: {adopted['exit_ratio']}",
        f"  stable_frames: {adopted['stable_frames']}",
        "interaction:",
        "  pinch_source: depth",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _metric_row(title: str, row: dict) -> str:
    latency = row.get("latency_mean")
    latency_text = "无 TP" if latency is None else f"{float(latency):.4f} s"
    param = row.get("param_text") or ""
    return (
        f"| {title} | {param} | {row['tp']} | {row['fn']} | {row['fp']} | {row['tn']} | "
        f"{float(row['test_rate']):.4f} | {float(row['recall']):.4f} | "
        f"{float(row['far']):.4f} | {latency_text} |"
    )


def render_curves(payload: dict, figures_dir: Path) -> str:
    require_real_payload(payload)
    peaks = payload["peaks"]
    lines = [
        f"选择用会话：`{payload['raw_path']}`，距离 {payload['distance_cm']} cm，"
        f"正样本段 {payload['n_pos']}、负样本段 {payload['n_neg']}。"
        f"坐标下降共 {payload['rounds']} 轮。下列曲线来自最后一轮。",
        "",
        "图中纵轴是测试率。标出的点是该条曲线按平台规则选出的刻度，不是插值。",
        "",
    ]
    figures = [
        (
            "E2_enter_ratio.png",
            "enter_ratio",
            peaks["enter_ratio"],
            "图 3-4 测试率随 enter_ratio 变化",
        ),
        (
            "E3_stable_frames.png",
            "stable_frames",
            peaks["stable_frames"],
            "图 3-5 测试率随 stable_frames 变化",
        ),
        (
            "E4_exit_ratio.png",
            "exit_ratio",
            peaks["exit_ratio"],
            "图 3-6 测试率随 exit_ratio 变化",
        ),
        (
            "E5_enter_x_exit_heatmap.png",
            None,
            None,
            "图 3-7 测试率随 enter_ratio 与 exit_ratio 变化",
        ),
    ]
    for filename, _key, peak, caption in figures:
        path = figures_dir / filename
        rel = f"experiments/figures/{filename}"
        if path.is_file():
            lines.append(f"![{caption}]({rel})")
            lines.append("")
        else:
            lines.append(f"`{rel}` 尚未生成。先运行 `python scripts/plot_curves.py`。")
            lines.append("")
        if peak is not None:
            lines.append(
                f"*{caption}。该曲线选出的刻度为 {peak['param_text']}，"
                f"测试率 {float(peak['test_rate']):.4f}，"
                f"TP/FN/FP/TN = {peak['tp']}/{peak['fn']}/{peak['fp']}/{peak['tn']}。*"
            )
        else:
            adopted = payload["heatmap_adopted"]
            lines.append(
                f"*{caption}。表中测试率最高的合法格为 "
                f"enter_ratio={adopted['enter_ratio']}，exit_ratio={adopted['exit_ratio']}，"
                f"测试率 {float(adopted['test_rate']):.4f}。非法格（exit ≥ enter）没有画出。*"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_conclusions(payload: dict) -> str:
    require_real_payload(payload)
    adopted = payload["adopted"]
    coordinate = payload["coordinate"]
    pinch = payload["pinch"]
    header = (
        "| 工作点 | 参数 | TP | FN | FP | TN | 测试率 | Recall | FAR | 延迟 |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
    )
    rows = [
        _metric_row("坐标下降三元组", coordinate),
        _metric_row("热力表采用格（系统采用）", adopted),
        _metric_row("contact 工作点", pinch),
    ]
    lines = [
        "每个数对应 `experiments/sweeps/` 里同一参数组合的一行，会话为 "
        f"`{payload['raw_path']}`。",
        "",
        header + "\n".join(rows),
        "",
    ]
    if payload["local_optimum"]:
        lines.append(
            "热力表最高格的测试率比坐标下降三元组高出 1/N 以上。"
            "简化寻优停在了局部工作点。按 `experiments/protocol.yaml`，"
            "系统采用热力表中测试率最高的合法格，stable_frames 仍用坐标下降的结果。"
            "上表两格都保留。"
        )
    else:
        lines.append(
            "热力表最高格相对坐标下降三元组的测试率提升不超过 1/N。"
            "系统采用的 enter_ratio 与 exit_ratio 仍取热力表最高合法格，"
            "stable_frames 取坐标下降结果。"
        )
    lines.append("")
    if adopted["satisfactory"]:
        lines.append(
            f"系统采用格的测试率为 {float(adopted['test_rate']):.4f}，"
            f"FAR 为 {float(adopted['far']):.4f}，达到预先写定的满意线"
            "（测试率 ≥ 0.85 且 FAR ≤ 0.15）。"
        )
    else:
        lines.append(
            f"系统采用格的测试率为 {float(adopted['test_rate']):.4f}，"
            f"FAR 为 {float(adopted['far']):.4f}，未达到满意线"
            "（测试率 ≥ 0.85 且 FAR ≤ 0.15）。"
        )
    lines.append("")
    lines.append(_sensitivity_note(payload))
    lines.append("")
    lines.append(
        f"同一会话上，depth 采用格测试率 {float(adopted['test_rate']):.4f}、"
        f"Recall {float(adopted['recall']):.4f}、FAR {float(adopted['far']):.4f}；"
        f"contact 工作点（pinch_threshold_px={pinch['pinch_threshold_px']}）测试率 "
        f"{float(pinch['test_rate']):.4f}、Recall {float(pinch['recall']):.4f}、"
        f"FAR {float(pinch['far']):.4f}。"
        "这是同一批正负段、同一条平台规则下的比较，不是显著性检验。"
    )
    lines.append("")
    transfer = payload.get("transfer") or {}
    if not transfer.get("collected"):
        lines.append("第二距离：未采集。")
    else:
        depth_t = transfer["depth"]
        pinch_t = transfer["pinch"]
        lines.append(
            f"第二距离会话 `{transfer['raw_path']}`（{transfer['distance_cm']} cm）"
            "不参与选参。锁定的 depth 工作点测试率 "
            f"{float(depth_t['test_rate']):.4f}、FAR {float(depth_t['far']):.4f}；"
            "锁定的 contact 工作点测试率 "
            f"{float(pinch_t['test_rate']):.4f}、FAR {float(pinch_t['far']):.4f}。"
        )
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _sensitivity_note(payload: dict) -> str:
    curve = payload["curves"]["enter_ratio"]
    peak_value = float(payload["peaks"]["enter_ratio"]["enter_ratio"])
    smaller = [row for row in curve if float(row["enter_ratio"]) < peak_value]
    larger = [row for row in curve if float(row["enter_ratio"]) > peak_value]
    bits = [
        f"enter_ratio 曲线的选出刻度是 {peak_value:.2f}。"
    ]
    if smaller:
        worst = max(smaller, key=lambda row: float(row["far"]))
        bits.append(
            f"更小的刻度里，FAR 最高出现在 {float(worst['enter_ratio']):.2f}"
            f"（FAR {float(worst['far']):.4f}，测试率 {float(worst['test_rate']):.4f}）。"
            "负样本段更容易出现上升沿。"
        )
    if larger:
        worst_recall = min(larger, key=lambda row: float(row["recall"]))
        bits.append(
            f"更大的刻度里，Recall 最低出现在 {float(worst_recall['enter_ratio']):.2f}"
            f"（Recall {float(worst_recall['recall']):.4f}，"
            f"测试率 {float(worst_recall['test_rate']):.4f}）。"
            "正样本段更容易漏检。"
        )
    return "".join(bits)


def splice_marked(text: str, start: str, end: str, body: str) -> str:
    start_at = text.find(start)
    end_at = text.find(end)
    if start_at < 0 or end_at < 0 or end_at < start_at:
        raise ValueError(f"report is missing markers {start} ... {end}")
    return text[: start_at + len(start)] + "\n" + body + text[end_at:]


def fill_report_text(text: str, payload: dict, figures_dir: Path) -> str:
    require_real_payload(payload)
    updated = splice_marked(text, CURVES_START, CURVES_END, render_curves(payload, figures_dir))
    updated = splice_marked(
        updated, CONCLUSIONS_START, CONCLUSIONS_END, render_conclusions(payload)
    )
    return updated
