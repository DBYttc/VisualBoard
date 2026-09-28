from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Tuple

import yaml


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class CameraSettings:
    device_index: int
    width: int
    height: int
    mirror: bool


@dataclass(frozen=True, slots=True)
class MediaPipeSettings:
    max_num_hands: int
    min_detection_confidence: float
    min_tracking_confidence: float
    model_complexity: int


@dataclass(frozen=True, slots=True)
class InteractionSettings:
    pinch_threshold_px: float
    cooldown_sec: float
    hover_sec: float
    trigger_mode: Literal["pinch", "hover", "both"]
    pinch_fire_on: Literal["release", "stable_frames", "press_edge"]
    pinch_stable_frames: int
    # 什么算"按下"：contact = 原来的拇指-食指接触；depth = 表观尺寸变化（见 depth_press）
    pinch_source: Literal["contact", "depth", "both"] = "contact"


@dataclass(frozen=True, slots=True)
class DepthPressSettings:
    """用"手指表观宽度随距离变化"当按下信号的全部参数。

    默认 enabled=False / pinch_source="contact"，即整条链路默认不启用，
    行为与不使用该功能时完全一致。
    """

    enabled: bool = False
    # mask = 肤色分割量指节宽度；hand_scale = 手腕->中指根距离；
    # finger_length = 食指根->食指尖 的投影长度（俯视下压动作最灵敏，且不吃光照）
    source: Literal["mask", "hand_scale", "finger_length"] = "mask"
    # near = 表观尺寸变大算按下（前置机位：手指伸向镜头）
    # far  = 表观尺寸变小算按下（俯视机位：手指向桌面下压 = 远离摄像头）
    direction: Literal["near", "far"] = "far"
    # rolling = 基线取最近 N 帧中位数，一直跟着手走（自校准，抗漂移）
    # startup = 启动后先给 warmup_sec 秒摆姿势，然后把那一刻的尺寸**冻结**成基准，
    #           之后只看"相对这个基准的变化量"，不再更新基准（按 R 可重新标定）
    baseline_mode: Literal["rolling", "startup"] = "rolling"
    warmup_sec: float = 5.0  # startup 模式的摆姿势时间（从检测到手开始计时）
    enter_ratio: float = 1.12  # 相对基线变化 12% 进入按压态（1.2 = 变化 20%）
    exit_ratio: float = 1.06  # 回到 6% 以内算松开（迟滞）
    stable_frames: int = 4  # 连续 N 帧确认
    baseline_samples: int = 45  # 基线 = 最近 N 帧的中位数
    min_samples: int = 15  # 基线至少要有多少帧才可信
    latch_key: bool = True  # 按压期间锁定按下瞬间的键（抵消下压时的视差漂移）
    finger_landmarks: Tuple[int, int] = (6, 7)  # 量宽所用的指段（默认食指中节）
    half_len_px: float = 18.0  # 从中心往两侧搜索的最大半宽
    samples: int = 5  # 沿指段的采样点数
    center_tol_px: float = 3.0  # 关键点偏离皮肤时沿垂线找中心的容差
    min_segment_px: float = 8.0  # 指段投影短于此值视为不可靠
    morph_kernel: int = 5  # 掩膜形态学核（<3 表示不做）
    skin_y_min: int = 40
    skin_cr_min: int = 133
    skin_cr_max: int = 173
    skin_cb_min: int = 77
    skin_cb_max: int = 127


@dataclass(frozen=True, slots=True)
class SmoothingSettings:
    ema_alpha: float


@dataclass(frozen=True, slots=True)
class UISettings:
    keyboard_origin: Tuple[int, int]
    key_width: int
    key_height: int
    key_gap: int
    row_gap: int
    show_skeleton: bool
    show_fps: bool
    demo_mode: bool


@dataclass(frozen=True, slots=True)
class DemoSettings:
    window_name: str


@dataclass(frozen=True, slots=True)
class ModeSettings:
    default: Literal["keyboard", "mouse"]


@dataclass(frozen=True, slots=True)
class MouseSettings:
    move_enabled: bool


@dataclass(frozen=True, slots=True)
class Settings:
    camera: CameraSettings
    mediapipe: MediaPipeSettings
    interaction: InteractionSettings
    smoothing: SmoothingSettings
    ui: UISettings
    demo: DemoSettings
    mode: ModeSettings
    mouse: MouseSettings
    depth_press: DepthPressSettings = DepthPressSettings()


def _require(section: dict[str, Any], key: str, path: str) -> Any:
    if key not in section:
        raise ValueError(f"Missing required config key: {path}.{key}")
    return section[key]


def _parse_depth_press(section: Any) -> DepthPressSettings:
    """depth_press 是可选段：缺失/为 None 都退回默认值（默认关闭）。"""
    if not isinstance(section, dict):
        return DepthPressSettings()

    lm = section.get("finger_landmarks", (6, 7))
    if not isinstance(lm, (list, tuple)) or len(lm) != 2:
        raise ValueError("depth_press.finger_landmarks must be [i, j]")

    defaults = DepthPressSettings()
    return DepthPressSettings(
        enabled=bool(section.get("enabled", defaults.enabled)),
        source=str(section.get("source", defaults.source)),
        direction=str(section.get("direction", defaults.direction)),
        baseline_mode=str(section.get("baseline_mode", defaults.baseline_mode)),
        warmup_sec=float(section.get("warmup_sec", defaults.warmup_sec)),
        enter_ratio=float(section.get("enter_ratio", defaults.enter_ratio)),
        exit_ratio=float(section.get("exit_ratio", defaults.exit_ratio)),
        stable_frames=int(section.get("stable_frames", defaults.stable_frames)),
        baseline_samples=int(
            section.get("baseline_samples", defaults.baseline_samples)
        ),
        min_samples=int(section.get("min_samples", defaults.min_samples)),
        latch_key=bool(section.get("latch_key", defaults.latch_key)),
        finger_landmarks=(int(lm[0]), int(lm[1])),
        half_len_px=float(section.get("half_len_px", defaults.half_len_px)),
        samples=int(section.get("samples", defaults.samples)),
        center_tol_px=float(section.get("center_tol_px", defaults.center_tol_px)),
        min_segment_px=float(section.get("min_segment_px", defaults.min_segment_px)),
        morph_kernel=int(section.get("morph_kernel", defaults.morph_kernel)),
        skin_y_min=int(section.get("skin_y_min", defaults.skin_y_min)),
        skin_cr_min=int(section.get("skin_cr_min", defaults.skin_cr_min)),
        skin_cr_max=int(section.get("skin_cr_max", defaults.skin_cr_max)),
        skin_cb_min=int(section.get("skin_cb_min", defaults.skin_cb_min)),
        skin_cb_max=int(section.get("skin_cb_max", defaults.skin_cb_max)),
    )


def _parse_settings(data: dict[str, Any]) -> Settings:
    cam = data.get("camera")
    mp = data.get("mediapipe")
    inter = data.get("interaction")
    smooth = data.get("smoothing")
    ui = data.get("ui")
    demo = data.get("demo")
    mode = data.get("mode")
    mouse = data.get("mouse")

    for name, val in [
        ("camera", cam),
        ("mediapipe", mp),
        ("interaction", inter),
        ("smoothing", smooth),
        ("ui", ui),
        ("demo", demo),
        ("mode", mode),
        ("mouse", mouse),
    ]:
        if not isinstance(val, dict):
            raise ValueError(f"Missing or invalid config section: {name}")

    origin = _require(ui, "keyboard_origin", "ui")
    if not isinstance(origin, (list, tuple)) or len(origin) != 2:
        raise ValueError("ui.keyboard_origin must be [x, y]")

    return Settings(
        camera=CameraSettings(
            device_index=int(_require(cam, "device_index", "camera")),
            width=int(_require(cam, "width", "camera")),
            height=int(_require(cam, "height", "camera")),
            mirror=bool(_require(cam, "mirror", "camera")),
        ),
        mediapipe=MediaPipeSettings(
            max_num_hands=int(_require(mp, "max_num_hands", "mediapipe")),
            min_detection_confidence=float(
                _require(mp, "min_detection_confidence", "mediapipe")
            ),
            min_tracking_confidence=float(
                _require(mp, "min_tracking_confidence", "mediapipe")
            ),
            model_complexity=int(_require(mp, "model_complexity", "mediapipe")),
        ),
        interaction=InteractionSettings(
            pinch_threshold_px=float(
                _require(inter, "pinch_threshold_px", "interaction")
            ),
            cooldown_sec=float(_require(inter, "cooldown_sec", "interaction")),
            hover_sec=float(_require(inter, "hover_sec", "interaction")),
            trigger_mode=_require(inter, "trigger_mode", "interaction"),
            pinch_fire_on=_require(inter, "pinch_fire_on", "interaction"),
            pinch_stable_frames=int(
                _require(inter, "pinch_stable_frames", "interaction")
            ),
            pinch_source=str(inter.get("pinch_source", "contact")),
        ),
        smoothing=SmoothingSettings(
            ema_alpha=float(_require(smooth, "ema_alpha", "smoothing")),
        ),
        ui=UISettings(
            keyboard_origin=(int(origin[0]), int(origin[1])),
            key_width=int(_require(ui, "key_width", "ui")),
            key_height=int(_require(ui, "key_height", "ui")),
            key_gap=int(_require(ui, "key_gap", "ui")),
            row_gap=int(_require(ui, "row_gap", "ui")),
            show_skeleton=bool(_require(ui, "show_skeleton", "ui")),
            show_fps=bool(_require(ui, "show_fps", "ui")),
            demo_mode=bool(_require(ui, "demo_mode", "ui")),
        ),
        demo=DemoSettings(
            window_name=str(_require(demo, "window_name", "demo")),
        ),
        mode=ModeSettings(default=_require(mode, "default", "mode")),
        mouse=MouseSettings(
            move_enabled=bool(_require(mouse, "move_enabled", "mouse")),
        ),
        depth_press=_parse_depth_press(data.get("depth_press")),
    )


def load_settings(config_dir: Path | None = None) -> Settings:
    root = config_dir or Path(__file__).resolve().parents[3] / "config"
    default_path = root / "default.yaml"
    local_path = root / "local.yaml"

    if not default_path.is_file():
        raise FileNotFoundError(f"Config not found: {default_path}")

    with default_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if local_path.is_file():
        with local_path.open(encoding="utf-8") as f:
            local = yaml.safe_load(f) or {}
        if isinstance(local, dict):
            data = _deep_merge(data, local)

    return _parse_settings(data)
