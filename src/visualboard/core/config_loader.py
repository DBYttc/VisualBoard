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
    pinch_fire_on: Literal["release", "stable_frames"]
    pinch_stable_frames: int


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


def _require(section: dict[str, Any], key: str, path: str) -> Any:
    if key not in section:
        raise ValueError(f"Missing required config key: {path}.{key}")
    return section[key]


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
