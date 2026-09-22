from __future__ import annotations

import logging
from typing import Optional

import cv2
import mediapipe as mp

from visualboard.core.config_loader import MediaPipeSettings
from visualboard.core.types import Frame, HandResult
from visualboard.vision.landmarks import landmarks_to_pixels

logger = logging.getLogger(__name__)


class HandTracker:
    def __init__(self, settings: MediaPipeSettings) -> None:
        self._mp_hands = mp.solutions.hands
        self._hands = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=settings.max_num_hands,
            model_complexity=settings.model_complexity,
            min_detection_confidence=settings.min_detection_confidence,
            min_tracking_confidence=settings.min_tracking_confidence,
        )

    def process(self, frame_bgr: Frame) -> HandResult:
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = self._hands.process(rgb)

        if not results.multi_hand_landmarks:
            return HandResult(detected=False)

        hand_landmarks = results.multi_hand_landmarks[0]
        handedness: Optional[str] = None
        if results.multi_handedness:
            handedness = results.multi_handedness[0].classification[0].label

        landmarks_px = landmarks_to_pixels(hand_landmarks, w, h)
        return HandResult(
            detected=True,
            landmarks_px=landmarks_px,
            handedness=handedness,
        )

    def close(self) -> None:
        self._hands.close()
        logger.debug("HandTracker closed")
