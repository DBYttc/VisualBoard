#!/usr/bin/env python3
"""Fill sections 3 and 4 of the practice report from experiments/optimal.yaml.

Refuses payloads that are not data_kind=real.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from visualboard.eval.results import REPORT_NAME, fill_report_text, require_real_payload  # noqa: E402


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--optimal", type=Path, default=ROOT / "experiments" / "optimal.yaml")
    parser.add_argument("--report", type=Path, default=ROOT / REPORT_NAME)
    parser.add_argument("--figures-dir", type=Path, default=ROOT / "experiments" / "figures")
    args = parser.parse_args(argv)

    if not args.optimal.is_file():
        print(f"Missing {args.optimal}. Report numbers stay uncollected.", file=sys.stderr)
        return 1
    with args.optimal.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    try:
        require_real_payload(payload)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not args.report.is_file():
        print(f"Missing report {args.report}", file=sys.stderr)
        return 1
    text = args.report.read_text(encoding="utf-8")
    updated = fill_report_text(text, payload, args.figures_dir)
    args.report.write_text(updated, encoding="utf-8")
    print(f"Updated {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
