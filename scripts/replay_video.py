#!/usr/bin/env python3
"""视频回放：把录好的输入视频当成摄像头喂给完整流水线（MediaPipe → 判定 → 出字）。

默认**边放边显示画面**：视频帧 + 虚拟键盘 + 手部骨架 + 悬停高亮，
左上角还会标出当前悬停键、队列内容和视频时间，方便你核对"手指到底在哪个键上"。

用法：
    # 直接看（按视频速度播放）
    python scripts/replay_video.py test/typing_01.mp4 --label baseline
    # 开"最近扫过的键" + 停留过滤
    python scripts/replay_video.py test/typing_01.mp4 --label trail100 --trail --dwell-ms 100
    # 不看画面、尽快跑完（快速试参数）
    python scripts/replay_video.py test/typing_01.mp4 --label quick --fast --no-window

播放时按键：
    空格 = 暂停/继续（暂停时可以逐帧核对高亮）
    q    = 退出
    r    = 重新标定（和真程序一致）
    m    = 切换键盘/鼠标模式

时间基准：
    now 直接取"视频时间"（帧号 / 视频帧率），所以 warmup_sec / cooldown_sec /
    trail_min_dwell_ms 这些按墙上时钟写的参数，回放时和录制时的语义一致。

出字：
    默认不真的打字，收集出字顺序最后打印并存 CSV；加 --type 才用 pynput 真的按键。
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import visualboard.app.main_loop as ml  # noqa: E402
from visualboard.core.config_loader import CameraSettings, Settings, load_settings  # noqa: E402
from visualboard.core.types import Frame  # noqa: E402


class VideoCamera:
    """把视频文件伪装成 OpenCVCamera：只暴露 output_size / read / release。"""

    def __init__(self, settings: CameraSettings, path: Path) -> None:
        self._cap = cv2.VideoCapture(str(path))
        if not self._cap.isOpened():
            raise SystemExit(f"打不开视频：{path}")
        self.fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        if self.fps <= 1 or self.fps > 240:
            self.fps = 30.0
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        # 和产品一致：只按宽度等比缩放（4:3 的 640x480 -> 1280x960）
        self.output_size: Tuple[int, int] = (
            settings.width,
            max(1, round(h * settings.width / w)) if w else settings.height,
        )
        self._mirror = settings.mirror
        self.frame_index = 0
        self.eof = False

    def read(self) -> Optional[Frame]:
        ok, frame = self._cap.read()
        if not ok or frame is None:
            # 主循环遇到 None 会 continue（还没走到 waitKey 就又读），会死循环；
            # 所以这里返回一帧黑屏，让 waitKey 看到 eof 后发 'q' 退出。
            self.eof = True
            w, h = self.output_size
            return np.zeros((h, w, 3), dtype=np.uint8)
        self.frame_index += 1
        if (frame.shape[1], frame.shape[0]) != self.output_size:
            frame = cv2.resize(frame, self.output_size, interpolation=cv2.INTER_LINEAR)
        if self._mirror:  # 和产品里的软件镜像保持一致
            frame = cv2.flip(frame, 1)
        return frame

    def release(self) -> None:
        self._cap.release()

    @property
    def video_time(self) -> float:
        return self.frame_index / self.fps


class VideoClock:
    """让 MainLoop 的 now 等于视频时间，时间相关参数才不会失真。"""

    def __init__(self, camera: VideoCamera) -> None:
        self._camera = camera

    def monotonic(self) -> float:
        return self._camera.video_time


class CaptureEmitter:
    """不真的按键，只把出字顺序记下来（--type 时改用真正的 KeyboardEmitter）。"""

    def __init__(self, keyboard, rows: List[dict]) -> None:
        self.last_error = None
        self._keyboard = keyboard
        self._rows = rows

    def emit_and_get_char(self, event):
        trail = self._keyboard._trail.get("index")
        trail_keys = [k for k, _ in trail] if trail else []
        char = self._keyboard.resolve_output(event.key_id)
        self._rows.append(
            {
                "emitted_key": str(event.key_id),
                "char": "" if char is None else char.replace("\n", "\\n"),
                "source": event.source,
                "trail_last": str(trail_keys[-1]) if trail_keys else "",
                "trail_prev": str(trail_keys[-2]) if len(trail_keys) > 1 else "",
                "trail_len": len(trail_keys),
                "trail_filtered": int(
                    bool(trail_keys) and str(event.key_id) != trail_keys[-1]
                ),
            }
        )
        return char


def _annotate(frame: Frame, camera: VideoCamera, keyboard, last_key: str) -> None:
    """在画面**右上角**写大字：悬停键 / 队列 / 视频时间（左上角是 HUD，别撞）。"""

    def label_of(key_id: str) -> str:
        btn = keyboard.get_button(key_id)  # type: ignore[arg-type]
        return btn.label if btn is not None else key_id

    hovered = [b.label for b in keyboard.buttons if b.is_hovered]
    trail = keyboard._trail.get("index")  # noqa: SLF001 - 回放脚本，只读
    trail_keys = [label_of(k) for k, _ in trail] if trail else []
    lines = [
        f"frame {camera.frame_index}  t={camera.video_time:5.2f}s",
        f"hover: {'/'.join(hovered) if hovered else '-'}",
        f"trail: {'>'.join(trail_keys[-5:]) if trail_keys else '-'}",
        f"emitted: {label_of(last_key) if last_key else '-'}",
    ]
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale, thick = 0.62, 2
    for i, text in enumerate(lines):
        (tw, _th), _ = cv2.getTextSize(text, font, scale, thick)
        x = frame.shape[1] - tw - 14  # 右对齐
        y = 32 + i * 27
        cv2.putText(frame, text, (x, y), font, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
        cv2.putText(frame, text, (x, y), font, scale, (0, 255, 255), thick, cv2.LINE_AA)


def _build_settings(args) -> Settings:
    s = load_settings()
    depth = dataclasses.replace(
        s.depth_press,
        enter_ratio=args.enter_ratio if args.enter_ratio is not None else s.depth_press.enter_ratio,
        exit_ratio=args.exit_ratio if args.exit_ratio is not None else s.depth_press.exit_ratio,
        stable_frames=args.stable_frames
        if args.stable_frames is not None
        else s.depth_press.stable_frames,
        warmup_sec=args.warmup if args.warmup is not None else s.depth_press.warmup_sec,
    )
    inter = dataclasses.replace(
        s.interaction,
        press_key_from_trail=bool(args.trail) or s.interaction.press_key_from_trail,
        trail_min_dwell_ms=args.dwell_ms
        if args.dwell_ms is not None
        else s.interaction.trail_min_dwell_ms,
        cooldown_sec=args.cooldown
        if args.cooldown is not None
        else s.interaction.cooldown_sec,
    )
    return dataclasses.replace(s, depth_press=depth, interaction=inter)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("video", type=Path, help="录好的输入视频（摄像头视角，不是屏幕录制）")
    p.add_argument("--label", default="run", help="这次回放的标签，用于输出文件名")
    p.add_argument("--trail", action="store_true", help='按下时用"最近扫过的键"')
    p.add_argument("--dwell-ms", type=int, default=None, help="trail_min_dwell_ms 覆盖值")
    p.add_argument("--enter-ratio", type=float, default=None)
    p.add_argument("--exit-ratio", type=float, default=None)
    p.add_argument("--stable-frames", type=int, default=None)
    p.add_argument("--warmup", type=float, default=None, help="startup 模式的标定秒数")
    p.add_argument("--cooldown", type=float, default=None)
    p.add_argument("--fast", action="store_true", help="不按视频时长等待（时间基准仍是视频时间）")
    p.add_argument("--no-window", action="store_true", help="不显示画面")
    p.add_argument("--type", action="store_true", help="真的用 pynput 按键（默认只记录）")
    p.add_argument("--max-frames", type=int, default=None)
    p.add_argument("--out", type=Path, default=None, help="CSV 输出路径")
    args = p.parse_args(argv)

    if not args.video.is_file():
        print(f"找不到视频：{args.video}", file=sys.stderr)
        return 1

    settings = _build_settings(args)
    camera = VideoCamera(settings.camera, args.video)
    print(
        f"视频：{args.video.name}  {camera.fps:.1f}fps  输出画布 {camera.output_size[0]}x"
        f"{camera.output_size[1]}  镜像={settings.camera.mirror}"
    )
    print(
        "参数："
        f"enter={settings.depth_press.enter_ratio} exit={settings.depth_press.exit_ratio} "
        f"stable_frames={settings.depth_press.stable_frames} warmup={settings.depth_press.warmup_sec}s "
        f"baseline={settings.depth_press.baseline_mode} "
        f"trail={settings.interaction.press_key_from_trail} "
        f"dwell={settings.interaction.trail_min_dwell_ms}ms "
        f"cooldown={settings.interaction.cooldown_sec}s"
    )
    if not args.no_window:
        print("播放中：空格=暂停/继续，q=退出，r=重新标定，m=切换模式")

    # 用视频代替摄像头（必须在 MainLoop 构造前替换）
    ml.OpenCVCamera = lambda _s: camera

    rows: List[dict] = []
    loop = ml.MainLoop(settings)
    loop._clock = VideoClock(camera)  # noqa: SLF001 - 回放脚本，允许注入
    if not args.type:
        loop._emitter = CaptureEmitter(loop._keyboard, rows)  # noqa: SLF001

    # 保存真实实现，再接管显示与按键
    real_imshow = cv2.imshow
    real_wait_key = cv2.waitKey
    state = {"paused": False, "t0": 0.0}

    def imshow(window: str, frame: Frame) -> None:
        last = rows[-1]["emitted_key"] if rows else ""
        _annotate(frame, camera, loop._keyboard, last)  # noqa: SLF001
        real_imshow(window, frame)

    def wait_key(_delay: int = 1) -> int:
        if state["paused"]:  # 暂停：只等空格/esc，画面停在当前帧
            while True:
                key = real_wait_key(30) & 0xFF
                if key == ord(" "):
                    state["paused"] = False
                    state["t0"] = 0.0  # 恢复时重新对齐节流
                    return 0xFF
                if key in (27, ord("q")):
                    return ord("q")
        key = real_wait_key(_delay) & 0xFF
        if key == ord(" "):
            state["paused"] = True
            print("⏸  暂停：按空格继续，q 退出")
            return 0xFF
        if args.max_frames is not None and camera.frame_index >= args.max_frames:
            return ord("q")
        if camera.eof:
            return ord("q")
        if not args.fast:  # 按视频时长节流
            import time as _time

            if state["t0"] == 0.0:
                state["t0"] = _time.monotonic()
            target = state["t0"] + camera.video_time
            now = _time.monotonic()
            if target > now:
                _time.sleep(target - now)
        return key

    cv2.imshow = imshow
    cv2.waitKey = wait_key
    if args.no_window:
        cv2.namedWindow = lambda *a, **k: None
        cv2.imshow = lambda *a, **k: None
        cv2.destroyAllWindows = lambda *a, **k: None

    try:
        loop.run()
    except KeyboardInterrupt:
        pass

    # ---------------- 汇总 ----------------
    out = args.out or args.video.with_name(f"{args.video.stem}.replay_{args.label}.csv")
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        f.write(f"# label={args.label}\n")
        f.write(f"# video={args.video.as_posix()}\n")
        f.write(
            f"# enter={settings.depth_press.enter_ratio} "
            f"exit={settings.depth_press.exit_ratio} "
            f"stable={settings.depth_press.stable_frames}\n"
        )
        f.write(
            f"# trail={settings.interaction.press_key_from_trail} "
            f"dwell_ms={settings.interaction.trail_min_dwell_ms}\n"
        )
        fieldnames = [
            "emitted_key", "char", "source", "trail_last",
            "trail_prev", "trail_len", "trail_filtered",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    keys = [r["emitted_key"] for r in rows]
    chars = "".join(r["char"] for r in rows)
    filtered = sum(r["trail_filtered"] for r in rows)
    print("-" * 60)
    print(f"处理帧数 : {camera.frame_index}  (视频时长 {camera.video_time:.1f}s)")
    print(f"按下次数 : {len(keys)}")
    print(f"出字序列 : {keys}")
    print(f"输出文本 : {chars!r}")
    if settings.interaction.press_key_from_trail:
        print(f"队列过滤生效（出的不是最新扫过的键）: {filtered} / {len(keys)}")
    print(f"CSV      : {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
