import itertools

import pytest

from adapter.src.decoder.buttons import BUTTON_MASKS_LEFT, BUTTON_MASKS_RIGHT, decode_buttons
from adapter.src.decoder.encode import build_raw_packet
from adapter.src.decoder.packet import decode_packet
from adapter.src.protocol import constants as C

MASKS = {"left": BUTTON_MASKS_LEFT, "right": BUTTON_MASKS_RIGHT}


@pytest.mark.parametrize("side", ["left", "right"])
def test_each_mask_is_one_distinct_bit(side):
    masks = list(MASKS[side].values())
    assert all(m and (m & (m - 1)) == 0 for m in masks), "every mask must be a single bit"
    assert len(set(masks)) == len(masks), "no two buttons may share a bit"


def test_full_physical_button_set():
    assert set(BUTTON_MASKS_LEFT) == {
        "up", "down", "left", "right", "l", "zl", "sl", "sr", "minus", "capture", "stick"}
    assert set(BUTTON_MASKS_RIGHT) == {
        "a", "b", "x", "y", "r", "zr", "sl", "sr", "plus", "home", "c", "stick"}


def _raw_with_bit(byte_off: int, bit: int) -> bytes:
    raw = bytearray(build_raw_packet(side="left"))
    raw[byte_off] |= bit
    return bytes(raw)


@pytest.mark.parametrize("side,name,byte_off,bit", [
    # [ND] hid_reports.md button bytes at 0x04..0x06 (independent of the FR-PY masks)
    ("right", "y", 0x04, 0x01),
    ("right", "x", 0x04, 0x02),
    ("right", "b", 0x04, 0x04),
    ("right", "a", 0x04, 0x08),
    ("right", "sr", 0x04, 0x10),
    ("right", "sl", 0x04, 0x20),
    ("right", "r", 0x04, 0x40),
    ("right", "zr", 0x04, 0x80),
    ("right", "home", 0x05, 0x10),
    ("right", "c", 0x05, 0x40),
    ("right", "plus", 0x05, 0x02),
    ("right", "stick", 0x05, 0x04),
    ("left", "capture", 0x05, 0x20),
    ("left", "minus", 0x05, 0x01),
    ("left", "stick", 0x05, 0x08),
    ("left", "zl", 0x06, 0x80),
    ("left", "l", 0x06, 0x40),
    ("left", "sl", 0x06, 0x20),
    ("left", "sr", 0x06, 0x10),
    ("left", "left", 0x06, 0x08),
    ("left", "right", 0x06, 0x04),
    ("left", "up", 0x06, 0x02),
    ("left", "down", 0x06, 0x01),
])
def test_shared_byte_positions(side, name, byte_off, bit):
    pkt = decode_packet(_raw_with_bit(byte_off, bit), side)
    assert [k for k, v in pkt.buttons.items() if v] == [name]


def test_right_face_byte_belongs_to_right_only():
    # byte 0x04 is the right-hand cluster; the left decoder must not see it
    for bit in (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80):
        assert not any(decode_packet(_raw_with_bit(0x04, bit), "left").buttons.values())
        assert sum(decode_packet(_raw_with_bit(0x04, bit), "right").buttons.values()) == 1


def test_counter_byte_never_reads_as_a_button():
    # the right slice data[3:6] includes the counter's top byte
    raw = bytearray(build_raw_packet(side="right", seq=0xFF000000))
    assert raw[3] == 0xFF
    assert not any(decode_packet(bytes(raw), "right").buttons.values())


@pytest.mark.parametrize("side", ["left", "right"])
def test_every_pair_of_buttons_decodes_as_exactly_that_pair(side):
    for a, b in itertools.combinations(MASKS[side], 2):
        pkt = decode_packet(build_raw_packet(side=side, buttons={a: True, b: True}), side)
        assert {k for k, v in pkt.buttons.items() if v} == {a, b}


@pytest.mark.parametrize("side", ["left", "right"])
def test_all_buttons_at_once_and_none(side):
    names = list(MASKS[side])
    pkt = decode_packet(build_raw_packet(side=side, buttons=dict.fromkeys(names, True)), side)
    assert all(pkt.buttons.values()) and set(pkt.buttons) == set(names)
    assert not any(decode_buttons(0, side).values())


def test_slices_cover_the_shared_byte():
    assert 0x05 in range(C.BUTTON_STATE_SLICE_LEFT.start, C.BUTTON_STATE_SLICE_LEFT.stop)
    assert 0x05 in range(C.BUTTON_STATE_SLICE_RIGHT.start, C.BUTTON_STATE_SLICE_RIGHT.stop)
