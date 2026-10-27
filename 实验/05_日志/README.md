# 运行日志（原始证据）

每次调参/采集都存一份日志，文件名带参数，方便回溯：

```
实验/05_日志/run_20261021_1050_A2_enter110_exit106_stable2.txt
```

生成方式（不改程序）：

```powershell
cd D:\VisualBoard
$env:PYTHONUNBUFFERED="1"
.\.venv\Scripts\python.exe -m visualboard.app.main 2>&1 |
  Tee-Object -FilePath "实验\05_日志\run_$(Get-Date -Format yyyyMMdd_HHmm)_A2_enter110.txt"
```

## 日志里能数出什么

| 内容 | 用途 |
|---|---|
| `Camera 0 opened via DSHOW in 454 ms` | 启动性能记录（写报告"启动优化"一节） |
| `capture=native: ... scaled to 1280x960` | 确认当次分辨率与缩放方式 |
| `Emitted key=key_a source=depth` | **实际触发次数**（Excel 数行） |
| `depth(5f): ...` | 当时的信号值与状态（用于核对标注） |

**注意**：
- 日志只记录"出了什么"，**不能**判断"该不该出"——误触/漏触必须配合 `02_数据集/标注模板.csv`
- 这些 `.txt`/`.log` 已被 `.gitignore` 忽略（避免每次运行都让 `git status` 变脏），但**交材料时要一起打包**
