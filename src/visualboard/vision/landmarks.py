from __future__ import annotations

from typing import Dict, List, Tuple

import mediapipe as mp

# MediaPipe hand landmark indices
WRIST = 0
THUMB_MCP = 2
THUMB_TIP = 4
INDEX_MCP = 5
INDEX_FINGER_TIP = 8
MIDDLE_MCP = 9
MIDDLE_FINGER_TIP = 12
RING_MCP = 13
RING_FINGER_TIP = 16
PINKY_MCP = 17
PINKY_TIP = 20

HAND_CONNECTIONS = mp.solutions.hands.HAND_CONNECTIONS

# Order used by multi-finger depth press / hover.
FINGER_NAMES: List[str] = ["thumb", "index", "middle", "ring", "pinky"]

# MCP -> TIP projection segment per finger (matches existing index 5->8).
FINGER_SEGMENTS: Dict[str, Tuple[int, int]] = {
    "thumb": (THUMB_MCP, THUMB_TIP),
    "index": (INDEX_MCP, INDEX_FINGER_TIP),
    "middle": (MIDDLE_MCP, MIDDLE_FINGER_TIP),
    "ring": (RING_MCP, RING_FINGER_TIP),
    "pinky": (PINKY_MCP, PINKY_TIP),
}

FINGER_TIPS: Dict[str, int] = {
    name: tip for name, (_mcp, tip) in FINGER_SEGMENTS.items()
}


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
