from __future__ import annotations

from dataclasses import dataclass

from visualboard.core.types import KeyId


@dataclass
class Button:
    key_id: KeyId
    label: str
    x: int
    y: int
    width: int
    height: int
    is_hovered: bool = False
    is_pressed_flash: bool = False
    is_special: bool = False

    def contains(self, px: float, py: float) -> bool:
        return (
            self.x <= px <= self.x + self.width
            and self.y <= py <= self.y + self.height
        )

    def rect(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)
