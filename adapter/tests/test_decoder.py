import math
from pathlib import Path

import pytest

from adapter.src.decoder.encode import build_raw_packet
from adapter.src.decoder.packet import PacketTooShort, decode_packet, decode_stick

FIXTURE = Path(__file__).parent / "fixtures" / "left_idle.hex"


def _load_fixture() -> bytes:
    for line in FIXTURE.read_text().splitlines():
        line = line.strip().replace(" ", "")
        if line and not line.startswith("#"):
            return bytes.fromhex(line)
    raise AssertionError("no packet in fixture")


def test_reference_sample_is_physically_sane():
    """joycon2py README sample: at rest, |accel| ~= 1 g and gyro ~= 0.

    This is the little-endian consistency check documented in JOYCON2_PROTOCOL.md H.
    """
    pkt = decode_packet(_load_fixture(), "left")
    mag = math.sqrt(pkt.accel_g.x**2 + pkt.accel_g.y**2 + pkt.accel_g.z**2)
    assert 0.9 < mag < 1.1
    assert abs(pkt.gyro_dps.x) < 5 and abs(pkt.gyro_dps.y) < 5 and abs(pkt.gyro_dps.z) < 5
    assert pkt.seq == 26376
    assert -0.05 < pkt.stick[0] < 0.05 and -0.05 < pkt.stick[1] < 0.05


def test_short_packet_rejected():
    with pytest.raises(PacketTooShort):
        decode_packet(b"\x00" * 20, "left")


@pytest.mark.parametrize("side", ["left", "right"])
def test_roundtrip_accel_gyro(side):
    raw = build_raw_packet(
        side=side, seq=12345,
        accel_g=(0.25, -0.5, 0.9),
        gyro_dps=(120.0, -240.0, 33.0),
    )
    pkt = decode_packet(raw, side)
    assert pkt.seq == 12345
    assert pkt.accel_g.x == pytest.approx(0.25, abs=1 / 4096)
    assert pkt.accel_g.y == pytest.approx(-0.5, abs=1 / 4096)
    assert pkt.gyro_dps.x == pytest.approx(120.0, abs=0.1)
    assert pkt.gyro_dps.z == pytest.approx(33.0, abs=0.1)


@pytest.mark.parametrize("side", ["left", "right"])
def test_roundtrip_stick_and_buttons(side):
    btn = {"a": True} if side == "right" else {"up": True, "l": True}
    raw = build_raw_packet(side=side, stick=(0.5, -0.75), buttons=btn)
    pkt = decode_packet(raw, side)
    assert pkt.stick[0] == pytest.approx(0.5, abs=0.01)
    assert pkt.stick[1] == pytest.approx(-0.75, abs=0.01)
    for k, v in btn.items():
        assert pkt.buttons[k] is True
    assert sum(pkt.buttons.values()) == len(btn)


def test_stick_center_is_zero():
    assert decode_stick(bytes([0x00, 0x08, 0x80])) == pytest.approx((0.0, 0.0), abs=1e-3)
    assert decode_stick(b"\x00\x00") == (0.0, 0.0)  # wrong length -> safe zero
