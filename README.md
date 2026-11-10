# VisualBoard

单目摄像头上的无接触虚拟键盘。手指悬停选中屏幕上的键，向桌面下压后，程序把该键送进当前焦点窗口。

默认触发不是捏合。俯视时手指下压会离摄像头更远，指段投影变短。程序用相对基线的变化判断按下：

```text
signal = baseline / value
```

`signal` 达到 `enter_ratio` 并连续 `stable_frames` 帧后视为按下，回到 `exit_ratio` 以下视为松开。五指各有一个检测器。拇指与食指的像素距离只作为对照基线。

## 环境

- Windows 10/11
- Python 3.10 或 3.11（3.12 需自行确认 MediaPipe 能否安装）
- 可用摄像头
- 答辩前在目标电脑上确认 pynput 没有被安全软件拦截

## 安装

在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev,experiments]"
```

`experiments` 只为出图安装 matplotlib。解释器指向 `.venv\Scripts\python.exe`。若 IDE 仍显示旧包名 `krybord`，重新选择一次该虚拟环境。

检查安装：

```powershell
python -c "import visualboard, cv2, mediapipe, pynput, yaml, numpy; print(visualboard.__version__)"
pytest
```

## 打字

1. 先让记事本、Word 或浏览器输入框获得焦点。
2. 启动：

```powershell
python -m visualboard.app.main
```

安装后的命令名是 `krybord`，作用相同。

3. 把手放在画面里，指尖移到虚拟键上，键面会高亮。
4. 手指向桌面压下再抬起，触发一次。

窗口标题是 **VisualBoard Virtual Keyboard**。

| 键 | 作用 |
|---|---|
| `Q` | 退出 |
| `R` | 复位触发器、Caps、窗口内缓冲和本次拼音缓冲 |
| `M` | 键盘模式与鼠标模式切换 |

## 中文输入

中文请切到系统拼音输入法，用本程序输入拼音，再按空格选词。程序不选汉字：`zhong` 是「中」还是「钟」，仍由系统输入法决定。

`config/default.yaml` 里 `interaction.pinyin_correct` 为 `true`。发出字母之前，程序检查它能不能接上已经发出的拼音。接不上，并且触发这根手指的指尖一键宽内有能接上的字母键，就改发那个字母。能接上就保持原键，即使旁边有更近的键。周围没有能接上的键时，原来的字母照发。Caps 或 Shift 打开时不改键。空格、回车和数字会清空这次拼音缓冲，退格只删最后一个拼音字母。按 `R` 也会清空。

音节表是《汉语拼音方案》里的无声调音节，ü 在 `j/q/x/y` 后写成 `u`，在 `n/l` 后写成 `v`。声母模糊（z/zh、c/ch、s/sh、n/l）和韵母模糊（an/ang、en/eng、in/ing）写在 [`src/visualboard/input/pinyin_syllables.py`](src/visualboard/input/pinyin_syllables.py) 里，实时纠正默认不用这两张表。把 `interaction.pinyin_correct` 设回 `false` 后，字母恢复原样发出。

这一层只改组不成音节的字母，不改按压判决，也不改「最近扫过的键」。`press_key_from_trail` 管的是勾手指时指尖跳排，拼音纠正管的是跳过去的字母已经组不成音节。

## 当前参数

主程序读取 [`config/default.yaml`](config/default.yaml)，若存在 `config/local.yaml` 则覆盖它。默认按下参数是：

| 参数 | 默认 | 含义 |
|---|---|---|
| `depth_press.enter_ratio` | 1.12 | 相对基线变化 12% 后进入按下 |
| `depth_press.exit_ratio` | 1.06 | 回到 6% 以内算松开 |
| `depth_press.stable_frames` | 4 | 连续确认帧数 |
| `depth_press.direction` | `far` | 投影变短算按下，对应俯视 |
| `interaction.pinch_source` | `depth` | `contact` 才改用捏合 |

40 cm 真人会话的扫参结果在 [`config/optimal_overlay.yaml`](config/optimal_overlay.yaml)，**不会自动生效**。那次选出的工作点是 `enter_ratio=1.06`、`exit_ratio=1.04`、`stable_frames=1`。20 次真按检出 11 次、漏掉 9 次，20 次干扰误触 1 次，测试率 0.75，误触率 0.05。事先写定的满意线是测试率不低于 0.85 且误触率不超过 0.15，这次没有达到。要沿用这组参数，把该文件里的键抄进 `config/local.yaml`。

## 复现实验

规则在 [`experiments/protocol.yaml`](experiments/protocol.yaml)。测试率是判对的正负样本段所占比例。最优刻度是网格上测试率最高的实测点，不在两格之间插值。没有 `data_kind=real` 的录像时，出图脚本会失败，不会画示意曲线。

已有的 40 cm 选择会话：

```powershell
python scripts\sweep_params.py --raw experiments\raw\session_select_40cm_20261021_211329.csv
python scripts\plot_curves.py
python scripts\fill_report.py
```

重新录制时，先把摄像头固定在手的上方并补光：

```powershell
python scripts\record_session.py --distance-cm 40 --role select
```

窗口先累计基线。基线完成后：

- `P`：开始 1.5 秒。这段里手指向桌面压下再抬起。做 20 次。
- `N`：开始 2 秒。这段里手可以移动，不要下压。做 20 次。
- `S`：两种都满 20 次后保存。
- `Q`：退出且不保存。

`P` 和 `N` 是记录窗口的开关，不会把字母打进其他软件。第二距离用 `--role transfer`，该文件不参与选参。本次仓库里没有第二距离录像。

### 视频回放

把录好的输入视频当成摄像头，喂给和实时打字完全相同的流水线（MediaPipe → 判定 → 出字）。同一段视频配不同参数，输入完全相同，适合对比两套参数，排除人的手抖和学习效应。

注意：必须是**摄像头视角**的录像（OBS 选 Video Capture Device），不是屏幕录制；机位、光照、`camera.mirror` 要和平时一致，否则画面左右反、按键全偏。

```powershell
# 直接播放：按视频速度走，弹窗显示画面
python scripts\replay_video.py test\typing_01.mp4 --label baseline

# 开"最近扫过的键"，并只认停留 100 ms 以上的键
python scripts\replay_video.py test\typing_01.mp4 --label trail100 --trail --dwell-ms 100

# 不弹窗、不等待，尽快跑完（快速试参数）
python scripts\replay_video.py test\typing_01.mp4 --label quick --fast --no-window
```

播放窗口里画面和实时打字时一样：虚拟键盘、手部骨架、悬停高亮，右上角另标四行——帧号与视频时间、当前悬停键、最近扫过的队列、最近出的字。

| 按键 | 作用 |
|---|---|
| `空格` | 暂停 / 继续（暂停时画面停住，便于逐帧核对） |
| `Q` | 退出 |
| `R` | 重新标定 |
| `M` | 键盘模式与鼠标模式切换 |

时间基准取视频时间（帧号除以视频帧率），所以 `warmup_sec`、`cooldown_sec`、`trail_min_dwell_ms` 这些按秒写的参数在回放时和录制时含义一致；`--fast` 只跳过等待，不改时间基准。

默认不真的按键，出字顺序收集起来最后打印，并写一份 CSV 到视频旁边（`<视频名>.replay_<label>.csv`），每次按下一行，含 `trail_last`、`trail_prev`、`trail_filtered`。加 `--type` 才用 pynput 真的打进当前窗口。

回放和 `record_session.py` 的区别：后者存的是五指投影长度数值，重放时跳过检测；视频回放会真的跑 MediaPipe，能重现悬停跳行、遮挡这类识别问题。

只看测量线、不写实验表：

```powershell
python scripts\tune_depth_press.py
python scripts\calibrate_pinch.py
python scripts\benchmark_fps.py
```

`calibrate_pinch.py` 只给捏合对照建议像素阈值。

## 结构

```text
摄像头 → MediaPipe 21 点 → 指尖平滑与五指投影
      → 虚拟键盘命中 → 触发 → 可选拼音纠正 → pynput
录像 → 重放 DepthPressDetector → 测试率曲线 → 课程报告
视频 → 摄像头替身 → 同一条流水线 → 出字序列 + CSV
```

编排在 [`src/visualboard/app/main_loop.py`](src/visualboard/app/main_loop.py)。按压判决在 [`src/visualboard/interaction/depth_press.py`](src/visualboard/interaction/depth_press.py)，拼音纠正在 [`src/visualboard/input/pinyin_correct.py`](src/visualboard/input/pinyin_correct.py)，离线指标在 [`src/visualboard/eval/`](src/visualboard/eval/)，视频回放在 [`scripts/replay_video.py`](scripts/replay_video.py)。

## 常见问题

| 现象 | 处理 |
|---|---|
| 导入失败 | 激活 `.venv` 后执行 `pip install -e ".[dev,experiments]"` |
| 左右相反 | 确认 `camera.mirror: true` |
| 下压没有触发 | 手保持在画面内约 1 秒，让基线形成；按下幅度加大。也可把 `enter_ratio` 调小 |
| 悬停时误触 | 增大 `enter_ratio` 或 `stable_frames` |
| 看不到手 | 补光，手距摄像头大约 30–60 cm |
| 按键没有进目标软件 | 先点击目标输入框；看窗口底部的红色错误。必要时换一台没有拦截 pynput 的电脑 |
| 拼音把邻近字母改了 | 把 `interaction.pinyin_correct` 设回 `false`。这一层只改组不成音节的字母，不选汉字 |
| MediaPipe 装不上 | 使用 Python 3.10/3.11，并安装 `mediapipe==0.10.14` |

课程报告是仓库根目录下的两份 Markdown。综合实践报告中的测试率和曲线来自上面的 40 cm 会话。
