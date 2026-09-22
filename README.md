# VisualBoard — 手势虚拟键盘

基于 **OpenCV + MediaPipe Hands + pynput** 的无接触键盘：食指悬停选键，拇指–食指捏合触发，向系统焦点窗口输出按键。

## 环境要求

- Python **3.10 / 3.11**（推荐；3.12 通常可用，但需确认 MediaPipe 兼容）
- Windows（答辩机请提前验证 pynput 是否被安全软件拦截）
- 可用摄像头

## 安装

```powershell
cd e:\VisualBoard
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
```

IDE（PyCharm / Cursor）请将解释器指向：

```text
e:\VisualBoard\.venv\Scripts\python.exe
```

若仍显示旧包名（如 `krybord`），重新选择一次该 `.venv` 即可。

## 验证环境

按顺序执行；最小通过标准是 **步骤 2 能导入** + **步骤 3 测试全绿**。

### 1. 激活虚拟环境

```powershell
cd e:\VisualBoard
.\.venv\Scripts\activate
```

提示符前应出现 `(.venv)`。

### 2. 确认 Python 与依赖可导入

```powershell
python --version
python -c "import visualboard, cv2, mediapipe, pynput, yaml, numpy; print(visualboard.__version__)"
```

应打印出版本号（如 `0.1.0`），且无 `ModuleNotFoundError`。

若导入失败（尤其项目重命名后），先重装：

```powershell
pip install -e ".[dev]"
```

### 3. 跑单元测试

```powershell
pytest
```

预期全部通过（当前约 10 passed）。

### 4. 摄像头 / 手势链路（可选）

```powershell
python scripts\benchmark_fps.py
```

能读到摄像头并打出帧率，说明 OpenCV + MediaPipe 基本可用。

### 5. 启动主程序（可选）

```powershell
python -m visualboard.app.main
# 或
visualboard
```

应弹出标题为 **VisualBoard Virtual Keyboard** 的窗口；按 `Q` 退出。

## 使用方法

1. 打开记事本 / Word / 浏览器输入框并**点击获得焦点**。
2. 在本程序窗口上方移动食指，让指尖落在虚拟键上（高亮）。
3. **捏合**（拇指贴向食指）后松开，触发一次按键。

### 快捷键（OpenCV 窗口）

| 键 | 作用 |
|---|---|
| `Q` | 退出 |
| `R` | 复位触发器 / Caps / 本地缓冲 |
| `M` | 键盘模式 ↔ 鼠标模式 |

## 配置

- 默认：[`config/default.yaml`](config/default.yaml)
- 本机覆盖：复制 [`config/local.yaml.example`](config/local.yaml.example) 为 `config/local.yaml`

常用项：

- `interaction.pinch_threshold_px` — 捏合距离阈值（像素）
- `interaction.cooldown_sec` — 按键冷却
- `interaction.trigger_mode` — `pinch` / `hover` / `both`
- `ui.demo_mode` — 为 true 时隐藏手部骨架，便于录演示

### 捏合标定

```powershell
python scripts\calibrate_pinch.py
```

按 `c` 采集 10 次捏合距离，脚本会建议 `pinch_threshold_px`。

## 中文输入

程序只输出拉丁字母与功能键。请切换到**系统拼音输入法**，手势输入拼音后按空格选词（与物理键盘相同）。

## 性能

```powershell
python scripts\benchmark_fps.py
```

## WPM / 准确率（答辩指标）

1. 准备固定短文（建议 50 词英文）。
2. 计时从开始第一个字母到 Enter 结束。
3. `WPM = (字符数 / 5) / 分钟数`。
4. 记录错键次数；各测 3 次取平均，写入答辩材料。

## 架构

```text
capture → vision (MediaPipe) → pointer (EMA) → keyboard hit-test
       → trigger (pinch/hover) → pynput emitter → 系统应用
```

模块边界见 [`src/visualboard/`](src/visualboard/)：`app/main_loop.py` 为唯一编排层。

## Troubleshooting

| 现象 | 处理 |
|---|---|
| `ModuleNotFoundError: visualboard` | 确认已激活 `.venv`，并执行 `pip install -e ".[dev]"` |
| 左右操作反了 | 确认 `camera.mirror: true` |
| 频繁误触 | 增大 `pinch_threshold_px` 或 `cooldown_sec`；运行标定脚本 |
| 检测不到手 | 加强光照；手距摄像头 30–60 cm |
| pynput 无效 / 报错 | 管理员运行或换答辩机；看窗口底部红色 OSD |
| MediaPipe 安装失败 | 使用 Python 3.10/3.11 与 `mediapipe==0.10.14` |

## 许可

课程 / 竞赛作品用途。
