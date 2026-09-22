from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from visualboard.app.main_loop import MainLoop
from visualboard.core.config_loader import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VisualBoard gesture virtual keyboard")
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Directory containing default.yaml (and optional local.yaml)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        settings = load_settings(args.config_dir)
    except (FileNotFoundError, ValueError) as exc:
        logging.error("%s", exc)
        return 1

    MainLoop(settings).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
