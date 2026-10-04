"""Button bit masks for Joy-Con 2 ([FR-PY] solo_logic.py MASKS).

The reference decoder reads a big-endian integer over a 3-byte slice whose start
offset differs per side (see constants.BUTTON_STATE_SLICE_*).

RIGHT masks verified on hardware 2026-09-06 (see docs/HARDWARE_BRINGUP.md): every
face/shoulder/rail button toggled its listed bit exactly, and the new Joy-Con 2
"C" button was captured at 0x000040 (byte 0x05, bit 6). LEFT masks verified on
hardware 2026-09-28: all ten buttons (D-pad, minus, L, ZL, stick click, SL, SR)
toggled their listed bit exactly, no changes needed.
"""

from __future__ import annotations

BUTTON_MASKS_RIGHT: dict[str, int] = {
    "a": 0x000400,
    "b": 0x000800,
    "x": 0x000100,
    "y": 0x000200,
    "plus": 0x000002,
    "r": 0x004000,
    "zr": 0x008000,
    "stick": 0x000004,
    "sl": 0x001000,
    "sr": 0x002000,
    "c": 0x000040,  # Joy-Con 2 "C" button -- HW-verified 2026-09-06 (byte 0x05 bit 6)
}

BUTTON_MASKS_LEFT: dict[str, int] = {
    "up": 0x000002,
    "down": 0x000001,
    "left": 0x000008,
    "right": 0x000004,
    "minus": 0x000100,
    "l": 0x000040,
    "zl": 0x000080,
    "stick": 0x000800,
    "sl": 0x000020,
    "sr": 0x000010,
}


def decode_buttons(state: int, side: str) -> dict[str, bool]:
    masks = BUTTON_MASKS_LEFT if side == "left" else BUTTON_MASKS_RIGHT
    return {name: bool(state & mask) for name, mask in masks.items()}
