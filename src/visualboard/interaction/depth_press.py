"""把"表观尺寸"信号变成稳定的按下电平。

输入是每一帧测到的像素值（指节宽度 / 手腕到中指根 / 食指根到指尖，见
vision/finger_width.py），输出是一个布尔电平：True = 判定为"按下了"。

两种基准模式（``baseline_mode``）：

``rolling``（默认）：基线 = 最近 N 帧的中位数，一直跟着手走。自校准、抗漂移，
    适合"手不在同一个位置、要长时间打字"的场景。

``startup``：启动后先给 ``warmup_sec`` 秒（默认 5s）摆姿势，标定期内绝不触发；
    时间到了就把那一刻的尺寸**冻结**成基准，之后只看"相对这个基准的变化量"。
    基准不再更新，所以 x 的含义非常直观：1.00 = 和标定时一样，
    1.20 = 变化了 20%。按 R 键会重新开始标定。

共同的关键处理：
    1. **相对变化**而不是绝对像素：不需要标定 f、绝对距离和真实手宽。
    2. **按压期间冻结基线**（rolling 模式）：否则按压会把基线一起拉上去，
       ratio 自己回到 1.0，按压中途自己取消。
    3. **双阈值迟滞**：enter_ratio 进入、exit_ratio 退出。
    4. **连续帧确认**：stable_frames 帧都在阈值内才算按下，抗单帧噪声。
"""

from __future__ import annotations

import statistics
import time
from collections import deque
from typing import Deque, Optional

from visualboard.core.config_loader import DepthPressSettings


class DepthPressDetector:
    def __init__(self, settings: DepthPressSettings) -> None:
        self._settings = settings
        self._samples: Deque[float] = deque(maxlen=max(2, int(settings.baseline_samples)))
        self._current: Optional[float] = None
        self._active = False
        self._count = 0
        self._frozen_base: Optional[float] = None
        self._start_time: Optional[float] = None
        self._last_now: Optional[float] = None

    def reset(self) -> None:
        """清空状态。startup 模式下等于"重新开始 5 秒标定"（按 R 键走这里）。"""
        self._samples.clear()
        self._current = None
        self._active = False
        self._count = 0
        self._frozen_base = None
        self._start_time = None
        self._last_now = None

    @property
    def active(self) -> bool:
        """当前是否处于"按下"电平。"""
        return self._active

    @property
    def warming_up(self) -> bool:
        """startup 模式下是否还在标定期（此时绝不触发）。"""
        return self._settings.baseline_mode == "startup" and self._frozen_base is None

    def warmup_remaining(self) -> Optional[float]:
        """标定还剩多少秒（只用于显示）。"""
        if not self.warming_up or self._start_time is None or self._last_now is None:
            return None
        return max(
            0.0, float(self._settings.warmup_sec) - (self._last_now - self._start_time)
        )

    def baseline(self) -> Optional[float]:
        """当前基准（startup 冻结后不再变化）。样本不足 / 还在标定时返回 None。"""
        if self._frozen_base is not None:
            return self._frozen_base
        if self._settings.baseline_mode == "startup":
            # 标定期内还没有基准：不能退回滚动中位数，否则 x 会给出一个
            # "看起来已经标定好了"的假数值（曾导致测试抓到这个问题）
            return None
        if len(self._samples) < max(2, int(self._settings.min_samples)):
            return None
        return float(statistics.median(self._samples))

    def ratio(self) -> Optional[float]:
        """当前值 / 基准。>1 表示比基准离摄像头更近（表观尺寸更大）。"""
        base = self.baseline()
        if base is None or base <= 0.0 or self._current is None:
            return None
        return float(self._current) / base

    def signal(self) -> Optional[float]:
        """按 direction 归一后的"变化量"：1.000 = 与基准相同，>1 = 朝"按下"方向变了多少。"""
        r = self.ratio()
        if r is None or r <= 0.0:
            return None
        return r if self._settings.direction == "near" else 1.0 / r

    def update(self, signal_px: Optional[float], now: Optional[float] = None) -> bool:
        """喂一帧的像素测量值，返回按下电平。

        signal_px 为 None（手不在画面 / 分割失败 / 这一帧量不出来）时：
        保持当前电平不变，也不污染基准。``now`` 省略时取 time.monotonic()。
        """
        if signal_px is None or signal_px <= 0.0:
            return self._active

        now_value = time.monotonic() if now is None else float(now)
        self._last_now = now_value
        value = float(signal_px)
        self._current = value

        if self.warming_up:
            if self._start_time is None:
                self._start_time = now_value
            self._samples.append(value)
            # 时间到 + 样本够（手确实在画面里）才冻结基准。
            # deque 的 maxlen 保证用的是"最后 baseline_samples 帧"，
            # 也就是姿势摆好之后的稳定值，而不是整段 5 秒的平均。
            elapsed = now_value - self._start_time
            if elapsed >= float(self._settings.warmup_sec) and len(self._samples) >= max(
                2, int(self._settings.min_samples)
            ):
                self._frozen_base = float(statistics.median(self._samples))
            return False

        base = self.baseline()
        if base is None or base <= 0.0:
            self._samples.append(value)  # rolling 模式：还在攒基准
            return False

        sig = value / base if self._settings.direction == "near" else base / value

        if self._active:
            if sig <= self._settings.exit_ratio:
                self._active = False
                self._count = 0
        else:
            if sig >= self._settings.enter_ratio:
                self._count += 1
                if self._count >= max(1, int(self._settings.stable_frames)):
                    self._active = True
                    self._count = 0
            else:
                self._count = 0

        if not self._active and self._frozen_base is None:
            # rolling 模式：只在非按压状态更新基准（避免按压把自己拉回 1.0）
            self._samples.append(value)

        return self._active
