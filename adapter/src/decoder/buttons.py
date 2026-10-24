"""Button bit masks for Joy-Con 2 ([FR-PY] solo_logic.py MASKS + additions).

The reference decoder reads a big-endian integer over a 3-byte slice whose start
offset differs per side (see constants.BUTTON_STATE_SLICE_*). In terms of the
raw report ([ND] hid_reports.md "Input Report 0x05", 4-byte button field at
0x04): byte 0x04 = right-hand buttons, 0x05 = shared (minus/plus/sticks/home/
capture/C), 0x06 = left-hand buttons. RIGHT state = data[3:6], so 0x05 is the
low byte; LEFT state = data[4:7], so 0x05 is the middle byte.

Status per entry (see docs/JOYCON2_PROTOCOL.md section E):
  LEFT  up/down/left/right/minus/l/zl/stick/sl/sr -- HW-verified 2026-09-28.
  RIGHT r/zr/plus/stick/c                         -- HW-verified 2026-09-06.
  RIGHT a/b/x/y/sl/sr -- the [FR-PY] table this file started from had
        a<->b, x<->y, sl<->sr swapped; HW 2026-10-24 showed ABXY lighting the
        wrong names. Now per [ND] hid_reports.md + Joy2Win (byte 0x04: Y=0x01
        X=0x02 B=0x04 A=0x08 SR=0x10 SL=0x20).
  RIGHT home, LEFT capture -- byte 0x05 bit 4 / bit 5 per [ND], Joy2Win and
        joycon2cpp; each lit exactly one bit on HW 2026-10-24.
  Sync is not in any known report layout; it is the pairing button.
"""

from __future__ import annotations

BUTTON_MASKS_RIGHT: dict[str, int] = {
    "a": 0x000800,
    "b": 0x000400,
    "x": 0x000200,
    "y": 0x000100,
    "r": 0x004000,
    "zr": 0x008000,
    "sl": 0x002000,
    "sr": 0x001000,
    "plus": 0x000002,
    "home": 0x000010,  # byte 0x05 bit 4 -- [ND]/Joy2Win/joycon2cpp
    "c": 0x000040,  # Joy-Con 2 "C" button -- HW-verified 2026-09-06 (byte 0x05 bit 6)
    "stick": 0x000004,
}

BUTTON_MASKS_LEFT: dict[str, int] = {
    "up": 0x000002,
    "down": 0x000001,
    "left": 0x000008,
    "right": 0x000004,
    "l": 0x000040,
    "zl": 0x000080,
    "sl": 0x000020,
    "sr": 0x000010,
    "minus": 0x000100,
    "capture": 0x002000,  # byte 0x05 bit 5 -- [ND]/Joy2Win/joycon2cpp
    "stick": 0x000800,
}

# Wire names, in display order. Mirrored in shared/protocol (schema.json,
# contracts.mjs); adapter/tests/test_contracts.py keeps them in sync.
BUTTONS_LEFT: tuple[str, ...] = tuple(BUTTON_MASKS_LEFT)
BUTTONS_RIGHT: tuple[str, ...] = tuple(BUTTON_MASKS_RIGHT)


def masks_for(side: str) -> dict[str, int]:
    return BUTTON_MASKS_LEFT if side == "left" else BUTTON_MASKS_RIGHT


def decode_buttons(state: int, side: str) -> dict[str, bool]:
    return {name: bool(state & mask) for name, mask in masks_for(side).items()}
