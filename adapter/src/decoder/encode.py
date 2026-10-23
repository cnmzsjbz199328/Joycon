"""Build synthetic raw Joy-Con 2 notification bytes.

Used by the synthetic frame source and by decoder tests. This is the inverse of
decoder.packet for the fields we care about; other bytes are left zero.
"""

from __future__ import annotations

from ..protocol import constants as C


def _put_s16le(buf: bytearray, off: int, value: int) -> None:
    buf[off:off + 2] = int(max(-32768, min(32767, value))).to_bytes(2, "little", signed=True)


def _put_u16le(buf: bytearray, off: int, value: int) -> None:
    buf[off:off + 2] = int(max(0, min(65535, value))).to_bytes(2, "little", signed=False)


def build_raw_packet(
    *,
    side: str = "left",
    seq: int = 0,
    accel_g: tuple[float, float, float] = (0.0, 0.0, 1.0),
    gyro_dps: tuple[float, float, float] = (0.0, 0.0, 0.0),
    stick: tuple[float, float] = (0.0, 0.0),
    stick_raw: tuple[int, int] | None = None,
    buttons: dict[str, bool] | None = None,
    battery_v: float = 3.9,
    temperature_c: float = 30.0,
) -> bytes:
    buf = bytearray(C.MIN_IMU_PACKET_LEN)

    _put_u16le(buf, C.OFF_PACKET_ID, seq & 0xFFFF)
    _put_u16le(buf, C.OFF_PACKET_ID + 2, (seq >> 16) & 0xFFFF)

    for i, v in enumerate(accel_g):
        _put_s16le(buf, C.OFF_ACCEL + 2 * i, round(v * C.ACCEL_RAW_PER_G))
    for i, v in enumerate(gyro_dps):
        _put_s16le(buf, C.OFF_GYRO + 2 * i, round(v / C.GYRO_DPS_PER_RAW))

    if stick_raw is None:
        sx = int(round(stick[0] * C.STICK_NOMINAL_EXTENT + C.STICK_CENTER)) & 0x0FFF
        sy = int(round(stick[1] * C.STICK_NOMINAL_EXTENT + C.STICK_CENTER)) & 0x0FFF
    else:
        sx, sy = stick_raw[0] & 0x0FFF, stick_raw[1] & 0x0FFF
    b0 = sx & 0xFF
    b1 = ((sx >> 8) & 0x0F) | ((sy & 0x0F) << 4)
    b2 = (sy >> 4) & 0xFF
    stk_slice = C.STICK_SLICE_LEFT if side == "left" else C.STICK_SLICE_RIGHT
    buf[stk_slice] = bytes([b0, b1, b2])

    if buttons:
        from .buttons import BUTTON_MASKS_LEFT, BUTTON_MASKS_RIGHT

        masks = BUTTON_MASKS_LEFT if side == "left" else BUTTON_MASKS_RIGHT
        state = 0
        for name, on in buttons.items():
            if on and name in masks:
                state |= masks[name]
        btn_slice = C.BUTTON_STATE_SLICE_LEFT if side == "left" else C.BUTTON_STATE_SLICE_RIGHT
        width = btn_slice.stop - btn_slice.start
        buf[btn_slice] = state.to_bytes(width, "big")

    _put_u16le(buf, C.OFF_BATTERY_VOLTAGE, round(battery_v * C.BATTERY_MV_PER_V))
    _put_s16le(buf, C.OFF_TEMPERATURE, round((temperature_c - C.TEMP_BASE_C) * C.TEMP_RAW_DIVISOR))

    return bytes(buf)
