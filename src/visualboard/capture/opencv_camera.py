from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

import cv2

from visualboard.core.config_loader import CameraSettings
from visualboard.core.types import Frame

logger = logging.getLogger(__name__)

# 打开摄像头的后端尝试顺序。
# Windows 上默认走 MSMF（Media Foundation），某些内置摄像头的驱动初始化极慢
# （实测 8~24 秒），而 DSHOW 只要 ~0.2 秒 —— 所以 auto 先试 DSHOW。
_BACKENDS: dict[str, Tuple[int, ...]] = {
    "dshow": (cv2.CAP_DSHOW,),
    "msmf": (cv2.CAP_MSMF,),
    "auto": (cv2.CAP_DSHOW, cv2.CAP_ANY),
}


class OpenCVCamera:
    def __init__(self, settings: CameraSettings) -> None:
        self._settings = settings
        self._cap = self._open(settings)
        self._output_size: Tuple[int, int] = (settings.width, settings.height)
        self._configure(settings)

    @property
    def output_size(self) -> Tuple[int, int]:
        """read() 实际交付的尺寸（等比缩放后的）。

        注意：只按宽度等比缩放，所以 4:3 的摄像头在 width=1280 时输出 1280x960。
        界面画布必须用这个尺寸，不能强行按 16:9 拉 —— 否则画面会被压扁。
        """
        return self._output_size

    @staticmethod
    def _open(settings: CameraSettings):
        order = _BACKENDS.get(settings.backend, _BACKENDS["auto"])
        for api in order:
            if api == cv2.CAP_ANY:
                logger.debug("Trying camera %d with default backend", settings.device_index)
            else:
                logger.debug("Trying camera %d with backend api=%s", settings.device_index, api)

            started = time.perf_counter()
            cap = cv2.VideoCapture(settings.device_index, api)
            elapsed_ms = (time.perf_counter() - started) * 1000.0

            if cap.isOpened():
                logger.info(
                    "Camera %d opened via %s in %.0f ms",
                    settings.device_index,
                    cap.getBackendName(),
                    elapsed_ms,
                )
                return cap

            cap.release()
            logger.warning(
                "Camera %d did not open with api=%s (%.0f ms)",
                settings.device_index,
                api,
                elapsed_ms,
            )

        raise RuntimeError(
            f"Cannot open camera device_index={settings.device_index} "
            f"(backend={settings.backend}). Try another index, close other apps "
            f"using the camera, or set camera.backend: msmf / dshow."
        )

    def _configure(self, settings: CameraSettings) -> None:
        """force: 让摄像头按目标分辨率输出；native: 保持默认分辨率，read() 里再缩放。

        注意 native 模式省掉的正是"驱动切换分辨率"这段（实测 2~3 秒），
        这是启动慢的主因。
        """
        if settings.capture == "native":
            native = (
                int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            )
            native_w, native_h = native
            if native_w > 0 and native_h > 0:
                scale = settings.width / native_w
                self._output_size = (settings.width, max(1, int(round(native_h * scale))))
            logger.info(
                "capture=native: keeping camera default %s, frames scaled to %dx%d "
                "(uniform scale, no aspect distortion)",
                f"{native_w}x{native_h}" if native_w and native_h else "(unknown yet)",
                self._output_size[0],
                self._output_size[1],
            )
            return

        started = time.perf_counter()
        request = (
            settings.capture_width or settings.width,
            settings.capture_height or settings.height,
        )
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, request[0])
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, request[1])
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        actual = (
            int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
        logger.info(
            "Requested %dx%d (%s): %.0f ms, camera reports %dx%d",
            request[0],
            request[1],
            settings.backend,
            elapsed_ms,
            actual[0],
            actual[1],
        )
        if actual != (settings.width, settings.height):
            logger.warning(
                "Camera fell back to %dx%d; frames will be scaled to %dx%d in read()",
                actual[0],
                actual[1],
                settings.width,
                settings.height,
            )
        # force 模式下摄像头应该已经给到目标分辨率；万一没有，也按比例缩放
        if actual[0] > 0 and actual[1] > 0:
            scale = settings.width / actual[0]
            self._output_size = (settings.width, max(1, int(round(actual[1] * scale))))

    def read(self) -> Optional[Frame]:
        ok, frame = self._cap.read()
        if not ok or frame is None:
            logger.warning("Camera read failed")
            return None
        if self._settings.mirror:
            frame = cv2.flip(frame, 1)

        # 等比缩放到固定宽度：像素阈值（捏合距离等）在任何摄像头下含义一致，
        # 而且**不会改变长宽比** —— 4:3 的摄像头就是 4:3，画面不会被压扁。
        target = self._output_size
        if (frame.shape[1], frame.shape[0]) != target:
            frame = cv2.resize(frame, target, interpolation=cv2.INTER_LINEAR)
        return frame

    def release(self) -> None:
        self._cap.release()
