#!/usr/bin/env python3
"""摄像头体检：逐个索引 × 逐个后端，测出启动耗时、原生分辨率、帧率，并给出配置建议。

回答的问题：
    - 哪颗摄像头是哪个 device_index（并存一张快照供肉眼确认）
    - 哪个后端打开最快（Windows 上 MSMF 可能慢到 8~24 秒）
    - 切到目标分辨率要多久（有些驱动要 2~3 秒）
    - 切换后帧率是否正常（USB 带宽/格式不够时会掉帧）

用法:
    .venv\\Scripts\\python.exe scripts\\probe_cameras.py            # 索引 0-3, DSHOW + 系统默认
    .venv\\Scripts\\python.exe scripts\\probe_cameras.py --quick     # 只试 DSHOW（最快）
    .venv\\Scripts\\python.exe scripts\\probe_cameras.py --indices 0 1 --backends dshow,msmf
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from visualboard.core.config_loader import load_settings  # noqa: E402

BACKENDS = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "default": cv2.CAP_ANY}
FPS_FRAMES = 20


def measure_fps(cap, frames: int = FPS_FRAMES):
    """读若干帧测平均帧率，返回 (fps, 最后一帧)。开头几帧丢掉（可能是旧缓冲）。"""
    for _ in range(3):
        cap.read()
    t = time.perf_counter()
    count = 0
    frame = None
    for _ in range(frames):
        ok, got = cap.read()
        if not ok or got is None:
            break
        frame = got
        count += 1
    elapsed = time.perf_counter() - t
    return (count / elapsed if elapsed > 0 else 0.0), frame


def check(index: int, backend: str, target: tuple[int, int], snapshot_dir: Path):
    t = time.perf_counter()
    cap = cv2.VideoCapture(index, BACKENDS[backend])
    open_ms = (time.perf_counter() - t) * 1000.0

    if not cap.isOpened():
        cap.release()
        time.sleep(0.3)
        return None

    native = (
        int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
    )
    native_fps, native_frame = measure_fps(cap)

    t = time.perf_counter()
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, target[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, target[1])
    set_ms = (time.perf_counter() - t) * 1000.0

    actual = (
        int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
    )
    target_fps, target_frame = measure_fps(cap)

    snap = snapshot_dir / f"cam{index}_{backend}.jpg"
    shot = target_frame if target_frame is not None else native_frame
    if shot is not None:
        cv2.imwrite(str(snap), shot)

    cap.release()
    time.sleep(0.4)

    return {
        "index": index,
        "backend": backend,
        "open_ms": open_ms,
        "native": native,
        "native_fps": native_fps,
        "set_ms": set_ms,
        "actual": actual,
        "target_fps": target_fps,
        "snapshot": snap,
    }


def advise(results: list[dict], target: tuple[int, int]) -> list[str]:
    if not results:
        return ["  没有可用的摄像头/后端组合。检查是否被别的程序占用，或换一个 USB 口。"]

    best = min(results, key=lambda r: r["open_ms"])
    lines = [
        f"  最快组合: index={best['index']} backend={best['backend']} "
        f"({best['open_ms']:.0f} ms) -> config/local.yaml 里用 device_index: {best['index']}"
    ]

    for r in results:
        tag = f"  index={r['index']} backend={r['backend']:7}"
        if r["set_ms"] >= 1500:
            lines.append(
                f"{tag}: 切到 {target[0]}x{target[1]} 要 {r['set_ms']:.0f} ms -> "
                f"建议 capture: native（原生 {r['native'][0]}x{r['native'][1]} "
                f"@ {r['native_fps']:.0f} fps）"
            )
        elif r["target_fps"] < 15:
            lines.append(
                f"{tag}: 切到 {r['actual'][0]}x{r['actual'][1]} 只有 {r['target_fps']:.1f} fps -> "
                f"带宽/格式不够，建议 capture: native 或调小 width/height"
            )
        else:
            lines.append(
                f"{tag}: 打开 {r['open_ms']:.0f} ms + 切分辨率 {r['set_ms']:.0f} ms，"
                f"{r['actual'][0]}x{r['actual'][1]} @ {r['target_fps']:.1f} fps -> capture: force 没问题"
            )
    return lines


def parse_size(text: str) -> tuple[int, int] | None:
    try:
        w, h = text.lower().split("x")
        return (int(w), int(h))
    except ValueError:
        return None


def sizes_report(index: int, backend: str, sizes: list[tuple[int, int]]) -> None:
    """同一颗摄像头上，请求不同分辨率的实际结果（帧率受 USB 带宽限制）。"""
    print(f"\n分辨率 x 帧率（index={index} backend={backend}）:")
    for w, h in sizes:
        cap = cv2.VideoCapture(index, BACKENDS[backend])
        if not cap.isOpened():
            print(f"  请求 {w:4}x{h:<4} 打不开")
            cap.release()
            continue
        t = time.perf_counter()
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        set_ms = (time.perf_counter() - t) * 1000.0
        actual = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        rate, _ = measure_fps(cap, 40)
        cap.release()
        time.sleep(0.4)
        note = "" if actual == (w, h) else f"（驱动实际给 {actual[0]}x{actual[1]}）"
        print(
            f"  请求 {w:4}x{h:<4} -> 实际 {actual[0]:4}x{actual[1]:<4} "
            f"@ {rate:5.1f} fps   设置 {set_ms:6.0f} ms {note}"
        )


def main() -> int:
    settings = load_settings(ROOT / "config")
    target = (settings.camera.width, settings.camera.height)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--indices", type=int, nargs="+", default=[0, 1, 2, 3])
    parser.add_argument(
        "--backends", default=None, help="逗号分隔: dshow,msmf,default（默认 dshow + default）"
    )
    parser.add_argument("--quick", action="store_true", help="只试 DSHOW 后端")
    parser.add_argument(
        "--sizes",
        default="640x480,960x540,1024x576,1280x720,1920x1080",
        help="要试的分辨率列表（对找到的最快组合测一遍；--no-sizes 可跳过）",
    )
    parser.add_argument("--no-sizes", action="store_true", help="跳过分辨率 x 帧率测试")
    args = parser.parse_args()

    if args.quick:
        backends = ["dshow"]
    elif args.backends:
        backends = [b.strip() for b in args.backends.split(",") if b.strip() in BACKENDS]
    else:
        backends = ["dshow", "default"]

    snapshot_dir = Path(tempfile.gettempdir()) / "visualboard_camera_probe"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    print(f"目标分辨率（config camera.width/height）: {target[0]}x{target[1]}")
    print("注意: MSMF/default 打开可能要 8 秒以上，别以为卡死了；用 --quick 可跳过\n")
    print("先关掉正在用摄像头的程序（会议软件 / 相机 app / 本程序）\n")

    results: list[dict] = []
    for index in args.indices:
        for backend in backends:
            print(f"测试 index={index} backend={backend} ...", flush=True)
            r = check(index, backend, target, snapshot_dir)
            if r is None:
                print("  打不开（没有该设备 / 被占用）")
            else:
                print(
                    f"  打开 {r['open_ms']:7.0f} ms | 原生 {r['native'][0]}x{r['native'][1]} "
                    f"@ {r['native_fps']:5.1f} fps | 切分辨率 {r['set_ms']:7.0f} ms -> "
                    f"{r['actual'][0]}x{r['actual'][1]} @ {r['target_fps']:5.1f} fps"
                )
            results.append(r)

    print("\n=== 建议 ===")
    usable = [r for r in results if r is not None]
    for line in advise(usable, target):
        print(line)

    if not args.no_sizes and usable:
        best = min(usable, key=lambda r: r["open_ms"])
        sizes = [s for s in (parse_size(x) for x in args.sizes.split(",")) if s]
        if sizes:
            sizes_report(best["index"], best["backend"], sizes)
            print(
                "\n  帧率随分辨率下降 = USB 带宽限制。若最大分辨率只有 10 fps，"
                "\n  用 config/local.yaml 的 capture: native（拿原生分辨率的高帧率），"
                "\n  或 capture: force + capture_width/height 请求一个折中尺寸。"
            )

    print(f"\n各索引快照: {snapshot_dir}（打开看哪个是外接摄像头）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
