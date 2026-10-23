"""Decode a raw Joy-Con 2 BLE notification into structured values.

All offsets / scales are from docs/JOYCON2_PROTOCOL.md (source [FR-PY], layout by
@german77). Fields flagged "unverified" there are decoded here too, but the
adapter only forwards the ones we're confident about.

Units out of this module:
  accel     -> g       (raw / 4096)
  gyro      -> deg/s   (raw * 360 / 48000)
  stick_raw -> (x, y)  12-bit counts, 0..4095, exactly as reported
  stick     -> [-1, 1] stateless nominal scaling (centre 2048, STICK_NOMINAL_EXTENT),
               no dead zone. The adapter replaces it with the per-controller
               calibration.stick.StickNormalizer output before broadcasting.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..protocol import constants as C
from .buttons import decode_buttons


class PacketTooShort(ValueError):
    pass


@dataclass
class Vec3:
    x: float
    y: float
    z: float

    def as_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z}


@dataclass
class DecodedPacket:
    seq: int
    side: str
    buttons: dict[str, bool]
    stick: tuple[float, float]
    stick_raw: tuple[int, int]
    accel_g: Vec3
    gyro_dps: Vec3
    battery_v: float | None
    battery_ma: float | None
    temperature_c: float | None
    raw_len: int


def _s16le(data: bytes, off: int) -> int:
    return int.from_bytes(data[off:off + 2], "little", signed=True)


def _u16le(data: bytes, off: int) -> int:
    return int.from_bytes(data[off:off + 2], "little", signed=False)


def decode_stick_raw(three_bytes: bytes) -> tuple[int, int]:
    """Two 12-bit values packed little-endian into 3 bytes ([FR-PY] decode_joystick)."""
    if len(three_bytes) != 3:
        return int(C.STICK_CENTER), int(C.STICK_CENTER)
    b0, b1, b2 = three_bytes[0], three_bytes[1], three_bytes[2]
    x = ((b1 & 0x0F) << 8) | b0
    y = (b2 << 4) | ((b1 & 0xF0) >> 4)
    return x, y


def nominal_stick(raw: tuple[int, int]) -> tuple[float, float]:
    nx = (raw[0] - C.STICK_CENTER) / C.STICK_NOMINAL_EXTENT
    ny = (raw[1] - C.STICK_CENTER) / C.STICK_NOMINAL_EXTENT
    return max(-1.0, min(1.0, nx)), max(-1.0, min(1.0, ny))


def decode_stick(three_bytes: bytes) -> tuple[float, float]:
    return nominal_stick(decode_stick_raw(three_bytes))


def decode_accel(data: bytes) -> Vec3:
    return Vec3(
        _s16le(data, C.OFF_ACCEL + 0) / C.ACCEL_RAW_PER_G,
        _s16le(data, C.OFF_ACCEL + 2) / C.ACCEL_RAW_PER_G,
        _s16le(data, C.OFF_ACCEL + 4) / C.ACCEL_RAW_PER_G,
    )


def decode_gyro(data: bytes) -> Vec3:
    return Vec3(
        _s16le(data, C.OFF_GYRO + 0) * C.GYRO_DPS_PER_RAW,
        _s16le(data, C.OFF_GYRO + 2) * C.GYRO_DPS_PER_RAW,
        _s16le(data, C.OFF_GYRO + 4) * C.GYRO_DPS_PER_RAW,
    )


def decode_packet(data: bytes, side: str) -> DecodedPacket:
    """side: 'left' | 'right'. Raises PacketTooShort if IMU bytes are absent."""
    if len(data) < C.MIN_IMU_PACKET_LEN:
        raise PacketTooShort(f"{len(data)} < {C.MIN_IMU_PACKET_LEN} (IMU not enabled?)")

    seq = _u16le(data, C.OFF_PACKET_ID) | (_u16le(data, C.OFF_PACKET_ID + 2) << 16)

    btn_slice = C.BUTTON_STATE_SLICE_LEFT if side == "left" else C.BUTTON_STATE_SLICE_RIGHT
    state = int.from_bytes(data[btn_slice], "big")
    buttons = decode_buttons(state, side)

    stk_slice = C.STICK_SLICE_LEFT if side == "left" else C.STICK_SLICE_RIGHT
    stick_raw = decode_stick_raw(data[stk_slice])

    batt_v = _u16le(data, C.OFF_BATTERY_VOLTAGE) / C.BATTERY_MV_PER_V
    batt_ma = _s16le(data, C.OFF_BATTERY_CURRENT) / C.BATTERY_RAW_PER_MA
    temp = C.TEMP_BASE_C + _s16le(data, C.OFF_TEMPERATURE) / C.TEMP_RAW_DIVISOR

    return DecodedPacket(
        seq=seq,
        side=side,
        buttons=buttons,
        stick=nominal_stick(stick_raw),
        stick_raw=stick_raw,
        accel_g=decode_accel(data),
        gyro_dps=decode_gyro(data),
        battery_v=batt_v if batt_v > 0 else None,
        battery_ma=batt_ma,
        temperature_c=temp,
        raw_len=len(data),
    )
