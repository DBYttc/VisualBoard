from __future__ import annotations

from typing import Optional, Protocol

from visualboard.core.types import Frame


class FrameSource(Protocol):
    def read(self) -> Optional[Frame]: ...

    def release(self) -> None: ...
