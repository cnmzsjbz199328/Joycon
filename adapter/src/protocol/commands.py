"""Builders for Joy-Con 2 Write Command characteristic payloads.

Generic frame ([FR-PY] main.py write_command):
    cmd_id | 0x91 0x01 | subcmd_id | 0x00 | len(payload) | 0x00 0x00 | payload
payload padded to >= 8 bytes ([FR-PY] notes short buffers can crash the controller).
"""

from __future__ import annotations

from . import constants as C


def build_command(command_id: int, subcommand_id: int, payload: bytes) -> bytes:
    payload = payload.ljust(8, b"\x00")
    return (
        bytes([command_id])
        + b"\x91\x01"
        + bytes([subcommand_id])
        + b"\x00"
        + bytes([len(payload)])
        + b"\x00\x00"
        + payload
    )


def set_player_leds(player_number: int) -> bytes:
    n = max(1, min(8, player_number))
    return build_command(
        C.COMMAND_LEDS,
        C.SUBCOMMAND_SET_PLAYER_LEDS,
        bytes([C.LED_PATTERN_BY_PLAYER[n]]),
    )


def enable_imu_sequence() -> tuple[bytes, bytes]:
    """The two raw writes that turn the IMU on. Send with ENABLE_IMU_GAP_S between."""
    return C.ENABLE_IMU_1, C.ENABLE_IMU_2


def read_flash(address: int, length: int) -> bytes:
    """[ND] commands.md 0x02/0x04 "Memory Read" (max 0x4F bytes over BLE).

    The reply arrives on COMMAND_RESPONSE_UUID as an 8-byte header, then
    length|00 00 00|address u32 LE, then the data (see parse_flash_read)."""
    payload = bytes([length & 0xFF, 0x7E, 0x00, 0x00]) + address.to_bytes(4, "little")
    return build_command(C.COMMAND_FLASH, C.SUBCOMMAND_FLASH_READ, payload)


def parse_flash_read(resp: bytes, address: int) -> bytes | None:
    """Data bytes of a read_flash() reply for `address`, or None if it is another reply."""
    if (len(resp) < 16 or resp[0] != C.COMMAND_FLASH or resp[3] != C.SUBCOMMAND_FLASH_READ
            or int.from_bytes(resp[12:16], "little") != address):
        return None
    return resp[16:16 + resp[8]]


def play_vibration_preset(preset_id: int) -> bytes:
    # Not a deliverable (GOAL non-goal); kept for completeness / future rumble.
    return build_command(
        C.COMMAND_VIBRATION,
        C.SUBCOMMAND_PLAY_VIBRATION_PRESET,
        bytes([preset_id & 0xFF]),
    )
