from __future__ import annotations

import logging
from typing import Optional

import cv2

from visualboard.core.config_loader import CameraSettings
from visualboard.core.types import Frame

logger = logging.getLogger(__name__)


class OpenCVCamera:
    def __init__(self, settings: CameraSettings) -> None:
        self._settings = settings
        self._cap = cv2.VideoCapture(settings.device_index)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"Cannot open camera device_index={settings.device_index}"
            )
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.height)

    def read(self) -> Optional[Frame]:
        ok, frame = self._cap.read()
        if not ok or frame is None:
            logger.warning("Camera read failed")
            return None
        if self._settings.mirror:
            frame = cv2.flip(frame, 1)
        return frame

    def release(self) -> None:
        self._cap.release()
