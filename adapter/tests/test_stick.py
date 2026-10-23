import math

import pytest

from adapter.src.calibration.stick import StickNormalizer
from adapter.src.decoder.encode import build_raw_packet
from adapter.src.decoder.packet import decode_packet, decode_stick_raw


def test_unpack_12bit_pairs():
    # placeholder the right unit reports in the unused left slot (HW 2026-09-06)
    assert decode_stick_raw(bytes.fromhex("fff77f")) == (2047, 2047)
    assert decode_stick_raw(bytes([0x00, 0x00, 0x00])) == (0, 0)
    assert decode_stick_raw(bytes([0xFF, 0xFF, 0xFF])) == (4095, 4095)
    # x low nibble-first, y high: x=0xABC, y=0x123 -> bc 3a 12
    assert decode_stick_raw(bytes([0xBC, 0x3A, 0x12])) == (0xABC, 0x123)
    assert decode_stick_raw(b"\x00\x00") == (2048, 2048)  # wrong length -> safe centre


@pytest.mark.parametrize("side", ["left", "right"])
def test_raw_roundtrip_through_the_side_specific_slot(side):
    pkt = decode_packet(build_raw_packet(side=side, stick_raw=(900, 3300)), side)
    assert pkt.stick_raw == (900, 3300)
    other = "right" if side == "left" else "left"
    assert decode_packet(build_raw_packet(side=side, stick_raw=(900, 3300)), other).stick_raw != (900, 3300)


def _settled(cx=1925, cy=2191, **kw) -> StickNormalizer:
    n = StickNormalizer(**kw)
    for i in range(10):
        n.normalize(cx + (i % 3) - 1, cy - (i % 2))  # rest jitter of a couple of counts
    assert n.center is not None
    return n


def test_offset_rest_point_reads_zero_once_settled():
    # left unit rest (HW 2026-09-28) was about (-123, +143) counts off 2048
    n = _settled()
    assert n.center == pytest.approx((1925, 2191), abs=2)
    assert n.normalize(1925, 2191) == (0.0, 0.0)
    assert n.normalize(1925 + 40, 2191 - 40) == (0.0, 0.0)  # inside the dead zone


def test_full_push_reaches_one_in_every_direction_and_signs_are_right():
    n = _settled(2047, 2047)
    for raw, want in [((2047 + 1250, 2047), (1, 0)), ((2047 - 1150, 2047), (-1, 0)),
                      ((2047, 2047 + 1250), (0, 1)), ((2047, 2047 - 1150), (0, -1))]:
        x, y = n.normalize(*raw)
        assert (x, y) == pytest.approx(want, abs=1e-2)  # sub-count centre jitter


def test_extent_grows_so_a_partial_push_is_not_inflated_forever():
    n = _settled(2048, 2048)
    assert n.normalize(2048 + 1100, 2048)[0] == pytest.approx(1.0)
    n.normalize(2048 + 1300, 2048)  # a harder push teaches the real extent
    assert n.normalize(2048 + 1100, 2048)[0] == pytest.approx((1100 / 1300 - 0.08) / 0.92, abs=1e-3)
    assert n.normalize(2048 + 1300, 2048)[0] == pytest.approx(1.0)
    assert n.normalize(2048 - 1100, 2048)[0] == pytest.approx(-1.0, abs=1e-3), "each direction learns separately"


def test_diagonal_is_clamped_to_the_unit_circle():
    n = _settled(2048, 2048)
    x, y = n.normalize(2048 + 1100, 2048 + 1100)  # square-gate corner
    assert math.hypot(x, y) == pytest.approx(1.0)
    assert x == pytest.approx(y)
    x, y = n.normalize(2048 + 778, 2048 + 778)  # round gate at 45 deg, radius 1100
    assert math.hypot(x, y) == pytest.approx(1.0, abs=0.01)


def test_dead_zone_is_radial_and_rescaled():
    n = _settled(2048, 2048, deadzone=0.1)
    assert n.normalize(2048 + 100, 2048) == (0.0, 0.0)  # 0.091 < 0.1
    x, _ = n.normalize(2048 + 165, 2048)  # 0.15 -> (0.15-0.1)/0.9
    assert x == pytest.approx(0.05 / 0.9, abs=1e-3)


def test_no_centre_is_learned_while_the_stick_is_held_at_connect():
    n = StickNormalizer()
    for _ in range(50):
        n.normalize(2048 + 900, 2048)  # held right, steady
    assert n.center is None
    assert n.normalize(2048 + 900, 2048)[0] > 0.7  # still usable with the nominal centre
    for _ in range(10):
        n.normalize(2040, 2056)  # let go
    assert n.center == pytest.approx((2040, 2056))


def test_moving_stick_never_settles_and_extents_wait_for_a_centre():
    n = StickNormalizer()
    for i in range(40):
        n.normalize(2048 + (i % 2) * 200, 2048)  # wobbling inside the band
    assert n.center is None
    n.normalize(2048 + 1500, 2048)
    assert n.extents[1] == n.initial_extent
