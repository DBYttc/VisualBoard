from __future__ import annotations

import mediapipe as mp

# MediaPipe hand landmark indices
WRIST = 0
THUMB_TIP = 4
INDEX_FINGER_TIP = 8
MIDDLE_FINGER_TIP = 12

HAND_CONNECTIONS = mp.solutions.hands.HAND_CONNECTIONS


def landmarks_to_pixels(
    landmarks,
    frame_width: int,
    frame_height: int,
):
    import numpy as np

    pts = np.zeros((21, 2), dtype=np.float64)
    for i, lm in enumerate(landmarks.landmark):
        pts[i, 0] = lm.x * frame_width
        pts[i, 1] = lm.y * frame_height
    return pts
