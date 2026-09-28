from __future__ import annotations

import cv2

from visualboard.core.types import Frame, HandResult, Point2D
from visualboard.vision.landmarks import HAND_CONNECTIONS


def draw_hand_skeleton(frame: Frame, hand: HandResult) -> None:
    if not hand.detected or hand.landmarks_px is None:
        return
    pts = hand.landmarks_px
    for start, end in HAND_CONNECTIONS:
        x1, y1 = int(pts[start][0]), int(pts[start][1])
        x2, y2 = int(pts[end][0]), int(pts[end][1])
        cv2.line(frame, (x1, y1), (x2, y2), (0, 200, 0), 2)
    for x, y in pts:
        cv2.circle(frame, (int(x), int(y)), 3, (0, 255, 0), -1)


def draw_pointer_dot(frame: Frame, point: Point2D, color=(0, 255, 255)) -> None:
    cv2.circle(frame, (int(point.x), int(point.y)), 8, color, -1)
    cv2.circle(frame, (int(point.x), int(point.y)), 10, (255, 255, 255), 2)


def draw_measure_line(frame: Frame, a: Point2D, b: Point2D, color=(255, 200, 0)) -> None:
    """把"量出来的手指宽度"画出来（调试深度按压时看这一条线是否贴着手指两侧）。"""
    ax, ay, bx, by = int(a.x), int(a.y), int(b.x), int(b.y)
    cv2.line(frame, (ax, ay), (bx, by), color, 2)
    cv2.circle(frame, (ax, ay), 3, (255, 255, 255), -1)
    cv2.circle(frame, (bx, by), 3, (255, 255, 255), -1)
