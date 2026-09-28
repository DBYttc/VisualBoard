#!/usr/bin/env python3
"""列出可用摄像头索引，各存一张快照，用来确认哪个 index 对应哪个摄像头。

用法（在项目根目录）:
    .venv\\Scripts\\python.exe scripts\\probe_cameras.py

快照默认存到系统临时目录，路径会打印出来；打开看一眼哪张是外接摄像头，
那个 index 就是 config/local.yaml 里 camera.device_index 要填的值。
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = Path(tempfile.gettempdir()) / "visualboard_camera_probe"
MAX_INDEX = 4


def probe(idx: int, backend: int | None, label: str) -> None:
    cap = cv2.VideoCapture(idx) if backend is None else cv2.VideoCapture(idx, backend)
    try:
        if not cap.isOpened():
            print(f"{label:6} index={idx}: 打不开（没有该设备，或被别的程序占用）")
            return

        # MSMF 刚打开时头几帧常是空的，多读几次再判定。
        ok, frame = False, None
        for _ in range(10):
            ok, frame = cap.read()
            if ok and frame is not None:
                break
            time.sleep(0.05)

        if not ok or frame is None:
            print(f"{label:6} index={idx}: 打开成功但读不到帧")
            return

        snap = OUT / f"cam_{label}_{idx}.jpg"
        cv2.imwrite(str(snap), frame)
        print(
            f"{label:6} index={idx}: OK  {frame.shape[1]}x{frame.shape[0]}  "
            f"亮度={frame.mean():5.1f}  backend={cap.getBackendName()}  -> {snap.name}"
        )
    except Exception as exc:  # noqa: BLE001 - 探测脚本，任何异常都只报告不中断
        print(f"{label:6} index={idx}: 异常 {type(exc).__name__}: {exc}")
    finally:
        cap.release()
        time.sleep(0.5)  # 给设备释放留时间，否则下一个索引可能打不开


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("先关掉正在运行的 app / 会议软件等占用摄像头的程序，再跑本脚本。\n")

    msmf, dshow = [], []
    for idx in range(MAX_INDEX):
        probe(idx, None, "msmf")
    print()
    for idx in range(MAX_INDEX):
        probe(idx, cv2.CAP_DSHOW, "dshow")

    print(f"\n快照目录：{OUT}")
    print("打开快照确认哪张是外接摄像头，把对应 index 填到 config/local.yaml：")
    print("camera:\n  device_index: <那个索引>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
