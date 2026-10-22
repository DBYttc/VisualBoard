# **《计算机系统项目综合实践》**
# **项目报告书**

**项目题目：** 基于单目表观尺寸变化的手势虚拟键盘按压检测系统（VisualBoard）

**组    长：班级：** 【待填】 **学号：** 【待填】 **姓名：** 【待填】  
**在本项实践中的贡献百分比：** 【待填】 %

**组  员1：班级：** 【待填】 **学号：** 【待填】 **姓名：** 【待填】  
**在本项实践中的贡献百分比：** 【待填】 %

**组  员2：班级：** 【待填】 **学号：** 【待填】 **姓名：** 【待填】  
**在本项实践中的贡献百分比：** 【待填】 %

**日    期：** 【待填】

---

## 第一章  项目开发计划

### 1.1 项目研究背景及意义

传统键盘依赖物理接触，在公共卫生、远程演示、无障碍交互等场景存在局限。单目 RGB 摄像头普及率高，但缺少可靠深度信息，难以直接判定“手指是否按下”。本项目面向课程综合实践，构建 **VisualBoard**：在 OpenCV + MediaPipe Hands 检测手部关键点的基础上，利用手指投影长度/表观尺寸相对基线的变化估计按压意图，驱动屏幕虚拟 QWERTY 键盘，并通过 pynput 向系统焦点窗口输出按键。

科研意义在于：不仅实现可用 demo，还把 **灵敏度参数（enter_ratio 等）** 做成可复现的离线扫参。40 cm 选择会话 `experiments/raw/session_select_40cm_20261021_211329.csv` 已扫完。采用格为 enter_ratio=1.06、exit_ratio=1.04、stable_frames=1，测试率 0.75，FAR 0.05，未达到满意线。数字与曲线见综合实践报告第三、四节。第二距离未采集。

### 1.2 项目研究现状

开源虚拟键盘多采用拇指–食指像素距离捏合或悬停计时（如各类 MediaPipe + OpenCV 教程项目）。其问题是：俯视桌面打字时捏合动作不自然，且绝对像素阈值对距离敏感。本项目采用相对表观尺寸 + 双阈值迟滞 + 稳定帧确认。与 contact 基线的对比写在 `experiments/protocol.yaml`，数字要等真人 CSV，见综合实践报告第三、四节。

### 1.3 项目研究内容及目标

1. 实时手部跟踪与虚拟键盘命中测试；  
2. depth_press / multi_finger_depth 按压检测；  
3. 触发引擎（冷却、press_edge、锁键）；  
4. 系统级按键输出与键鼠模式；  
5. **参数寻优管线**与报告级真图（`experiments/`）。

目标：可演示输入；pytest 通过；完成两份课程文档；用真实 CSV 支撑灵敏度结论。

### 1.4 使用技术介绍

| 技术 | 用途 |
|---|---|
| Python 3.10/3.11 | 主语言 |
| OpenCV | 摄像头采集、画面绘制 |
| MediaPipe Hands | 21 点手部关键点 |
| NumPy | 几何与数值 |
| pynput | 系统键盘/鼠标模拟 |
| PyYAML | 配置 |
| pytest | 单元/链路测试 |
| matplotlib | 有真人 sweep 之后出测试率曲线（可选依赖 `experiments`） |

角色建议：项目经理、技术经理（算法）、软件工程师（集成/UI）、测试工程师（扫参与用例）、文档工程师。

---

## 第二章  可行性研究

### 2.1 可行性分析概述

硬件仅需普通笔记本摄像头与补光；软件栈均为开源；开发周期与课程周次匹配。主要风险在光照、个体手型差异与误触，通过标定、迟滞与实验寻优缓解。

### 2.2 技术可行性

MediaPipe Hands 可在 CPU 上接近实时；相对尺寸信号不依赖深度相机；项目已实现 rolling/startup 基线、五指投影与单元测试。录制、扫参和出图脚本是 `scripts/record_session.py`、`scripts/sweep_params.py`、`scripts/plot_curves.py`。没有 `data_kind=real` 的 CSV 时，出图脚本非零退出，不画占位曲线。

### 2.3 管理可行性

任务按模块与实验 Phase 分解（协议→管线→采集→出图→文档），组长协调时间节点，成员按算法/集成/测试/文档分工。

### 2.4 经济可行性

无额外服务器与商用 SDK；预算主要为可选 USB 摄像头与补光（百元级）。

### 2.5 操作可行性

提供 README、捏合标定、深度调参脚本和 `experiments/protocol.yaml`。演示前固定距离与补光。真人扫参步骤见综合实践报告第三节。

---

## 第三章  需求分析

### 3.1 需求分析的定义及任务

明确功能边界、性能指标、运行环境、输入输出与故障处理，作为设计与测试依据。

### 3.2 功能需求

1. 实时显示镜像画面与虚拟键盘；  
2. 指尖悬停高亮；  
3. 按压/捏合触发按键；  
4. 向任意焦点应用输出；  
5. 键盘/鼠标模式切换（M）、复位（R）、退出（Q）；  
6. 配置覆盖（`config/local.yaml`）；  
7. 实验采集与参数扫参（课程扩展需求）。

### 3.3 系统运行环境需求

Windows 10/11；Python 3.10+；摄像头；建议 8GB 内存。答辩机需确认 pynput 不被拦截。

### 3.4 输入输出需求

输入：摄像头帧、YAML 配置、实验时按 P/N 划定的正负样本段。  
输出：系统按键事件、OSD/HUD、实验 CSV 与 figures PNG。

### 3.5 故障处理需求

摄像头打不开时提示；手丢失时复位深度基线相关状态；发射失败在 OSD 显示错误；实验缺 CSV 时绘图脚本失败而非伪造曲线。

### 3.6 性能需求

| 指标 | 目标 |
|---|---|
| 跟踪帧率 | 尽量稳定可用（以 `benchmark_fps.py` 实测为准） |
| 触发可控 | 冷却与迟滞抑制连发/抖触 |
| 测试率 | 40 cm 采用格测试率 0.75、FAR 0.05，未达到测试率 ≥ 0.85 且 FAR ≤ 0.15 |

---

## 第四章  总体设计

### 4.1 系统的设计原则

模块化分层；配置与代码分离；检测与系统注入解耦；实验可复现；最小改动扩展评测。

### 4.2 系统功能结构图

结构图尚未从运行画面导出。数据流如下：

`capture → vision →（pointer EMA 与五指 depth_press 并行）→ keyboard hit-test → trigger → pynput`

离线实验不经过击键：`record_session` 保存五指投影与捏合距离，`sweep_params` 重放 `DepthPressDetector`。

---

## 第五章  详细设计

> 本章原“数据库设计”按本项目性质改写为 **配置与实验数据设计**（无传统业务数据库）。

### 5.1 配置与实验数据设计概述

系统持久化需求主要是：运行参数（YAML）与实验原始表（CSV）。概念上分为 **Config Store** 与 **Experiment Store**。

### 5.2 概念结构设计

- 实体 ConfigProfile：camera / mediapipe / interaction / depth_press / smoothing / ui …  
- 实体 GridPoint：某参数取值下的 TP/FN/FP/TN 与测试率  
- 实体 FigureArtifact：只由 `data_kind=real` 的 sweep CSV 生成的 PNG，必须能追溯到 raw 文件。当前还没有这批 PNG。  

### 5.3 逻辑设计（字段）

原始会话由 `scripts/record_session.py` 写成，注释头含 `data_kind=real`，列为  
`timestamp, label, segment_id, len_thumb, len_index, len_middle, len_ring, len_pinky, pinch_distance_px`。  
扫参表由 `scripts/sweep_params.py` 写成，列为  
`enter_ratio, exit_ratio, stable_frames, pinch_threshold_px, tp, fn, fp, tn, test_rate, recall, far, latency_mean, n`。

### 5.4 物理设计（文件布局）

```
config/default.yaml
config/local.yaml          # 本机覆盖（可选）
experiments/raw/session_select_40cm_20261021_211329.csv
experiments/sweeps/*.csv
experiments/figures/*.png
experiments/protocol.yaml
experiments/optimal.yaml
```

### 5.5 配置“连接”方式

`visualboard.core.config_loader.load_settings` 读取 `config/default.yaml`，若存在 `config/local.yaml` 则合并。扫参生成的 `config/optimal_overlay.yaml` 不会自动合并，需要实验者自行抄进 `local.yaml`。

### 5.6 采集与视觉模块

`OpenCVCamera` 负责取流与镜像；`HandTracker` 封装 MediaPipe Hands，输出像素坐标关键点。

### 5.7 深度按压模块

`DepthPressDetector`：相对基线 signal、enter/exit 迟滞、stable_frames。  
`MultiFingerDepthPress`：五指 MCP→TIP 投影，俯视 `direction=far`。

### 5.8 触发与指针模块

`PointerStateTracker`（EMA）；`TriggerEngine`（contact/depth/hover、冷却、锁键）。

### 5.9 UI 与输出模块

`VirtualKeyboard` 布局与命中；`KeyboardEmitter` / `MouseEmitter`；`Presenter` 绘制骨架与 HUD。

主界面与调参界面截图：

主界面与录制界面截图已保存为 `experiments/figures/S2_main_ui.png`、`experiments/figures/S3_record_or_tune.png`。

---

## 第六章  系统编码

### 6.1 配置加载

模块：`src/visualboard/core/config_loader.py`  
功能：YAML→Settings；支持 overrides 供扫参。

### 6.2 主循环编排

模块：`src/visualboard/app/main_loop.py`  
功能：唯一编排层，串联检测、触发与发射。

### 6.3 深度按压

模块：`src/visualboard/interaction/depth_press.py`  
关键：`signal = baseline/value`（far）或 `value/baseline`（near）；enter/exit 迟滞。

### 6.4 多指投影

模块：`src/visualboard/interaction/multi_finger_depth.py`

### 6.5 触发引擎

模块：`src/visualboard/interaction/trigger_engine.py`

### 6.6 虚拟键盘

模块：`src/visualboard/ui/virtual_keyboard.py`

### 6.7 实验采集

模块：`scripts/record_session.py`  
P 开始 1.5 秒正样本段，N 开始 2.0 秒负样本段。满 20 段正样本和 20 段负样本后按 S 保存。空闲帧只用于滚动基线，不进测试率分母。

### 6.8 扫参与出图

`scripts/sweep_params.py` 做坐标下降、enter×exit 热力表和 pinch 对照。`scripts/plot_curves.py` 在没有 real sweep 时非零退出，不生成占位图。`scripts/fill_report.py` 只接受 `data_kind=real` 的 `experiments/optimal.yaml`。

---

## 第七章  系统的测试与维护

### 7.1 软件测试概述

采用综合策略：静态阅读关键路径 + 动态单元测试 + 真人标注扫参实验。

### 7.2 软件测试常用方法

黑盒（触发是否发出）、白盒（基线冻结/rolling）、对比实验（contact vs depth）、参数敏感性分析。

### 7.3 系统测试用例

| 编号 | 用例 | 预期 |
|---|---|---|
| T1 | pytest 全量 | 全部通过 |
| T2 | 主程序启动 | 窗口显示键盘 |
| T3 | depth 下压 | 有键触发（配置启用时） |
| T4 | `plot_curves.py` 无 real sweep | 退出码≠0，不生成假曲线 |
| T5 | enter_ratio 扫参 | 已由上述 40 cm CSV 生成 E2 |
| T6 | depth 与 contact | 同一 CSV、同一测试率规则；见综合实践报告第四节 |

参数实验结果图已由 `scripts/plot_curves.py` 写入 `experiments/figures/E2_enter_ratio.png`、`E3_stable_frames.png`、`E4_exit_ratio.png`、`E5_enter_x_exit_heatmap.png`。

维护：保留 `experiments/raw` 原始表；改算法后重跑扫参；可选覆盖在 `config/optimal_overlay.yaml`，主程序不会自动加载它。

---

## 参考文献

[1] MediaPipe Hands 官方文档. Google.  
[2] Bradski G. The OpenCV Library.  
[3] 课程项目方案：`项目方案_基于视觉识别的手势虚拟键盘输入系统.md`  
[4] 本仓库实验协议：`experiments/protocol.yaml`
