"""拼音音节纠正：只用内存里的键坐标，不打开摄像头，不写 experiments/raw。"""

from __future__ import annotations

from visualboard.core.types import FingerPointer, KeyId, Point2D, PointerState
from visualboard.input.pinyin_correct import (
    LetterKey,
    PinyinComposition,
    choose_letter,
    correct_event,
)
from visualboard.input.pinyin_syllables import SYLLABLES, is_legal
from visualboard.interaction.events import KeyTriggerEvent


def _key(letter: str, cx: float, width: float = 40.0) -> LetterKey:
    return LetterKey(letter, KeyId(f"key_{letter}"), cx, 0.0, width)


def test_illegal_neighbor_is_replaced_when_inside_one_key_width():
    # 缓冲 zhon，命中 f 非法；g 在一键宽内且合法，发出 g。
    letter = choose_letter("zhon", "f", 0.0, 0.0, [_key("f", 0.0), _key("g", 30.0)])
    assert letter == "g"


def test_legal_choice_is_kept_even_if_another_key_is_closer():
    # f 的键心更靠近指尖，但 g 本身合法，仍发出 g。
    keys = [_key("f", 0.0), _key("g", 50.0, width=80.0)]
    assert choose_letter("zhon", "g", 0.0, 0.0, keys) == "g"


def test_zhong_plus_g_stays_and_extends_the_buffer():
    assert is_legal("zhongg")
    composition = PinyinComposition()
    composition.text = "zhong"
    letter = choose_letter("zhong", "g", 0.0, 0.0, [_key("g", 0.0)])
    assert letter == "g"
    composition.observe(letter)
    assert composition.text == "zhongg"


def test_empty_buffer_accepts_f():
    assert choose_letter("", "f", 0.0, 0.0, [_key("f", 0.0), _key("g", 30.0)]) == "f"


def test_space_clears_buffer_before_the_next_syllable():
    composition = PinyinComposition()
    composition.text = "zhon"
    composition.observe(" ")
    assert composition.text == ""
    assert choose_letter(composition.text, "f", 0.0, 0.0, [_key("f", 0.0)]) == "f"


def test_backspace_drops_the_last_letter_only():
    composition = PinyinComposition()
    composition.text = "zhon"
    composition.observe("\b")
    assert composition.text == "zho"
    composition.text = ""
    composition.observe("\b")
    assert composition.text == ""


def test_disabled_switch_emits_the_illegal_letter():
    letter = choose_letter(
        "zhon",
        "f",
        0.0,
        0.0,
        [_key("f", 0.0), _key("g", 30.0)],
        enabled=False,
    )
    assert letter == "f"


def test_illegal_letter_is_still_emitted_when_nothing_nearby_is_legal():
    keys = [_key("f", 0.0), _key("g", 200.0)]
    assert choose_letter("zhon", "f", 0.0, 0.0, keys) == "f"


def test_syllable_legality_examples():
    assert not is_legal("xa")
    assert not is_legal("zhonf")
    assert not is_legal("ng")
    assert is_legal("zhong")
    assert is_legal("nv")
    assert is_legal("xue")
    for text in ("z", "zh", "zho", "zhong", "zhongg"):
        assert is_legal(text), text


def test_syllable_table_is_a_fixed_scheme_list():
    for syllable in ("zhong", "zhang", "guo", "nv", "lv", "xue", "ju"):
        assert syllable in SYLLABLES
    assert "xa" not in SYLLABLES
    assert "ng" not in SYLLABLES
    assert "zhonf" not in SYLLABLES
    assert 350 <= len(SYLLABLES) <= 450


def test_fuzzy_tables_are_off_unless_a_test_turns_them_on():
    # 默认打分不看模糊表。单独打开后，声母或韵母对调才可能变成合法切分。
    assert not is_legal("shong")
    assert is_legal("shong", fuzzy_initials=True)
    assert not is_legal("shong", fuzzy_finals=True)
    for text in ("bangi", "dengi", "pingi"):
        assert not is_legal(text)
        assert not is_legal(text, fuzzy_initials=True)
        assert is_legal(text, fuzzy_finals=True)


def test_uppercase_and_function_keys_follow_the_buffer_rules():
    composition = PinyinComposition()
    composition.observe("z")
    composition.observe(None)
    assert composition.text == "z"
    composition.observe("A")
    assert composition.text == ""
    composition.observe("z")
    composition.observe("1")
    assert composition.text == ""


def test_missing_finger_uses_the_index_tip():
    keyboard = _FakeKeyboard()
    index_tip = Point2D(10.0, 0.0)
    middle_tip = Point2D(90.0, 0.0)
    pointer = PointerState(
        index_px=index_tip,
        thumb_px=Point2D(0.0, 0.0),
        pinch_distance_px=80.0,
        fingers=(
            FingerPointer("index", index_tip, 10.0),
            FingerPointer("middle", middle_tip, 10.0),
        ),
    )
    # 食指在 f 上，f 离 g 超过一键宽，没有手指名时不改成 g。
    far = KeyTriggerEvent(KeyId("key_f"), "pinch", 1.0)
    assert far.finger is None
    assert correct_event(keyboard, "zhon", far, pointer).key_id == KeyId("key_f")

    # 同一布局，事件标明中指，中指在 g 上，才改发 g。
    named = KeyTriggerEvent(KeyId("key_f"), "pinch", 1.0, finger="middle")
    replaced = correct_event(keyboard, "zhon", named, pointer)
    assert replaced.key_id == KeyId("key_g")
    assert replaced.finger == "middle"
    assert replaced.timestamp == 1.0


class _FakeKeyboard:
    def __init__(self) -> None:
        self.caps_on = False
        self.shift_armed = False
        self.buttons = [
            _FakeButton(KeyId("key_f"), 0, 0, 20, 20),
            _FakeButton(KeyId("key_g"), 80, 0, 20, 20),
        ]

    def plain_letter(self, key_id: KeyId):
        return {KeyId("key_f"): "f", KeyId("key_g"): "g"}.get(key_id)

    def get_button(self, key_id: KeyId):
        for button in self.buttons:
            if button.key_id == key_id:
                return button
        return None


class _FakeButton:
    def __init__(self, key_id: KeyId, x: int, y: int, width: int, height: int) -> None:
        self.key_id = key_id
        self.x = x
        self.y = y
        self.width = width
        self.height = height
