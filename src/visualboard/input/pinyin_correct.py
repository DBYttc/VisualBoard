"""发出字母之前，按当前拼音能否接成音节选择键。

不选汉字。zhong 交给系统输入法决定是「中」还是「钟」。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

from visualboard.core.types import KeyId, Point2D, PointerState
from visualboard.input.pinyin_syllables import is_legal
from visualboard.interaction.events import KeyTriggerEvent


@dataclass(frozen=True, slots=True)
class LetterKey:
    letter: str
    key_id: KeyId
    cx: float
    cy: float
    width: float


class _LetterKeyboard(Protocol):
    @property
    def caps_on(self) -> bool: ...

    @property
    def shift_armed(self) -> bool: ...

    def plain_letter(self, key_id: KeyId) -> Optional[str]: ...

    def get_button(self, key_id: KeyId): ...

    @property
    def buttons(self) -> Sequence: ...


class PinyinComposition:
    """本次组字已经发出的小写拼音。和界面上的 _typed_buffer 不是同一条。"""

    def __init__(self) -> None:
        self.text = ""

    def clear(self) -> None:
        self.text = ""

    def observe(self, char: Optional[str]) -> None:
        if char is None:
            return
        if char == "\b":
            if self.text:
                self.text = self.text[:-1]
            return
        if len(char) == 1 and "a" <= char <= "z":
            self.text += char
            return
        self.text = ""


def choose_letter(
    buffer: str,
    chosen: str,
    tip_x: float,
    tip_y: float,
    keys: Sequence[LetterKey],
    *,
    enabled: bool = True,
) -> str:
    """选定字母还能接上就原样返回。接不上才在一键宽内挑最近的合法字母。"""
    if not enabled:
        return chosen
    if is_legal(buffer + chosen):
        return chosen
    chosen_key = next((key for key in keys if key.letter == chosen), None)
    if chosen_key is None:
        return chosen
    legal: list[LetterKey] = []
    for key in keys:
        if key.letter != chosen and _distance(tip_x, tip_y, key.cx, key.cy) > chosen_key.width:
            continue
        if is_legal(buffer + key.letter):
            legal.append(key)
    if not legal:
        return chosen
    nearest = min(legal, key=lambda item: _distance(tip_x, tip_y, item.cx, item.cy))
    return nearest.letter


def correct_event(
    keyboard: _LetterKeyboard,
    buffer: str,
    event: KeyTriggerEvent,
    pointer: PointerState,
) -> KeyTriggerEvent:
    """Caps / Shift 打开时不改键。否则可能把事件里的字母键换成邻近合法键。"""
    if keyboard.caps_on or keyboard.shift_armed:
        return event
    chosen = keyboard.plain_letter(event.key_id)
    if chosen is None:
        return event
    button = keyboard.get_button(event.key_id)
    if button is None:
        return event
    tip = tip_from_pointer(pointer, event.finger)
    keys = _letter_keys(keyboard)
    replacement = choose_letter(buffer, chosen, tip.x, tip.y, keys)
    if replacement == chosen:
        return event
    for key in keys:
        if key.letter == replacement:
            return KeyTriggerEvent(
                key_id=key.key_id,
                source=event.source,
                timestamp=event.timestamp,
                finger=event.finger,
            )
    return event


def tip_from_pointer(pointer: PointerState, finger: Optional[str]) -> Point2D:
    name = finger or "index"
    for item in pointer.fingers:
        if item.name == name:
            return item.tip_px
    return pointer.index_px


def _letter_keys(keyboard: _LetterKeyboard) -> list[LetterKey]:
    keys: list[LetterKey] = []
    for button in keyboard.buttons:
        letter = keyboard.plain_letter(button.key_id)
        if letter is None:
            continue
        keys.append(
            LetterKey(
                letter=letter,
                key_id=button.key_id,
                cx=button.x + button.width / 2.0,
                cy=button.y + button.height / 2.0,
                width=float(button.width),
            )
        )
    return keys


def _distance(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)
