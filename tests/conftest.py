from __future__ import annotations

import pytest

from visualboard.core.config_loader import (
    InteractionSettings,
    SmoothingSettings,
    UISettings,
)


@pytest.fixture
def interaction_settings() -> InteractionSettings:
    return InteractionSettings(
        pinch_threshold_px=40,
        cooldown_sec=0.4,
        hover_sec=0.5,
        trigger_mode="pinch",
        pinch_fire_on="release",
        pinch_stable_frames=3,
    )


@pytest.fixture
def ui_settings() -> UISettings:
    return UISettings(
        canvas_width=1280,
        canvas_height=720,
        keyboard_margin=0,
        keyboard_bottom=20,
        key_gap=6,
        row_gap=8,
        key_aspect=1.0,
        keyboard_opacity=0.5,
        show_skeleton=True,
        show_fps=True,
        demo_mode=False,
    )


@pytest.fixture
def smoothing_settings() -> SmoothingSettings:
    return SmoothingSettings(ema_alpha=0.5)
