from __future__ import annotations

from visualboard.core.types import KeyId, Point2D
from visualboard.ui.virtual_keyboard import VirtualKeyboard


def _center(kb: VirtualKeyboard, kid: str) -> Point2D:
    btn = next(b for b in kb.buttons if b.key_id == KeyId(kid))
    return Point2D(btn.x + btn.width / 2, btn.y + btn.height / 2)


def test_hit_test_finds_letter_key(ui_settings):
    kb = VirtualKeyboard(ui_settings)
    btn = next(b for b in kb.buttons if b.key_id == KeyId("key_a"))
    cx = btn.x + btn.width / 2
    cy = btn.y + btn.height / 2
    assert kb.hit_test(cx, cy) == KeyId("key_a")


def test_hover_exclusive(ui_settings):
    kb = VirtualKeyboard(ui_settings)
    btn = next(b for b in kb.buttons if b.key_id == KeyId("key_q"))
    cx = btn.x + btn.width / 2
    cy = btn.y + btn.height / 2
    hover = kb.update_hover(Point2D(cx, cy))
    assert hover == KeyId("key_q")
    hovered = [b for b in kb.buttons if b.is_hovered]
    assert len(hovered) == 1


def test_caps_toggle_and_resolve(ui_settings):
    kb = VirtualKeyboard(ui_settings)
    assert kb.resolve_output(KeyId("key_caps")) is None
    assert kb.caps_on is True
    assert kb.resolve_output(KeyId("key_a")) == "A"
    assert kb.resolve_output(KeyId("key_a")) == "A"
    kb.resolve_output(KeyId("key_caps"))
    assert kb.caps_on is False
    assert kb.resolve_output(KeyId("key_a")) == "a"


def test_trail_last_is_most_recent_key(ui_settings):
    """按下时用"最近扫过的键"：队尾是最后进入的那个。"""
    kb = VirtualKeyboard(ui_settings)

    t = 0.0
    for kid in ("key_a", "key_s", "key_d"):
        kb.update_hovers({"index": _center(kb, kid)}, t)
        t += 0.033

    assert kb.trail_last("index") == KeyId("key_d")
    assert kb.trail_last("index") == KeyId("key_d")  # 只看，不移出
    assert kb.trail_last("thumb") is None  # 没碰过键盘的手指没有队列


def test_trail_last_skips_key_just_grabbed(ui_settings):
    """勾手指时 hover 会先跳到下面的键；min_dwell 让刚滑上去的键不算。"""
    kb = VirtualKeyboard(ui_settings)

    # a 停了 300ms，然后滑到 s 只停 30ms（模拟勾的时候抢先跳到下面一排）
    kb.update_hovers({"index": _center(kb, "key_a")}, 0.00)
    kb.update_hovers({"index": _center(kb, "key_a")}, 0.30)
    kb.update_hovers({"index": _center(kb, "key_s")}, 0.33)

    assert kb.trail_last("index") == KeyId("key_s")  # 不过滤：就是抢跳的那个
    assert (
        kb.trail_last("index", min_dwell_ms=100, now=0.36) == KeyId("key_a")
    )  # 过滤掉只停了 30ms 的 s，退回上一个


def test_trail_cleared_on_reset(ui_settings):
    kb = VirtualKeyboard(ui_settings)
    kb.update_hovers({"index": _center(kb, "key_q")}, 0.0)
    assert kb.trail_last("index") is not None
    kb.reset()
    assert kb.trail_last("index") is None
