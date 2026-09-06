"""Joy-Con 2 BLE protocol constants.

Sources (see docs/JOYCON2_PROTOCOL.md for full attribution):
  [FR-PY]  TheFrano/joycon2py  -- main.py / solo_logic.py, layout by @german77
  [FR-CPP] TheFrano/joycon2cpp
  [MIS]    Misaka10571/joycon2-connector
  [EIMU]   matiaspalmac/everything-imu  -- 62 Hz sampling, hardware-validated

STATUS: EXPERIMENTAL -- not verified on real hardware in this environment.
Offsets marked "unverified" in the protocol doc are cross-checked at runtime
by adapter/src/bluetooth/prototype.py against a real Joy-Con 2.
"""

from __future__ import annotations

import math

# --- BLE advertisement identification -------------------------------------  [FR-PY]
MANUFACTURER_ID = 1363  # 0x0553, Nintendo Switch 2 controller family
MANUFACTURER_PREFIX = bytes([0x01, 0x00, 0x03, 0x7E])

# --- GATT characteristics ----------------------------------------------------  [FR-PY]
INPUT_REPORT_UUID = "ab7de9be-89fe-49ad-828f-118f09df7fd2"   # Notify
WRITE_COMMAND_UUID = "649d4ac9-8eb7-4e6c-af44-1ea54fe5f005"  # Write
# Service UUID: unverified -- dump full GATT tree on real hardware (protocol doc C.1)

# --- Command / subcommand ids ---------------------------------------------  [FR-PY]
COMMAND_LEDS = 0x09
COMMAND_VIBRATION = 0x0A
COMMAND_CONFIG = 0x0C  # inferred: config/IMU domain (first byte of ENABLE_IMU_*)

SUBCOMMAND_SET_PLAYER_LEDS = 0x07
SUBCOMMAND_PLAY_VIBRATION_PRESET = 0x02

# Two raw 12-byte writes to WRITE_COMMAND_UUID, ~0.5s apart, enable the IMU.  [FR-PY]
ENABLE_IMU_1 = bytes([0x0C, 0x91, 0x01, 0x02, 0x00, 0x04, 0x00, 0x00, 0x2F, 0x00, 0x00, 0x00])
ENABLE_IMU_2 = bytes([0x0C, 0x91, 0x01, 0x04, 0x00, 0x04, 0x00, 0x00, 0x2F, 0x00, 0x00, 0x00])
ENABLE_IMU_GAP_S = 0.5

# Player LED bit patterns P1..P8 (reproduces Switch pattern).                 [FR-PY]
LED_PATTERN_BY_PLAYER = {
    1: 0x01, 2: 0x03, 3: 0x07, 4: 0x0F,
    5: 0x09, 6: 0x05, 7: 0x0D, 8: 0x06,
}

# --- Packet layout (Left Joy-Con, IMU enabled, ~62 bytes) ----------------  [FR-PY]
# Byte offsets. IMU / battery / temperature offsets are identical for L and R;
# button + stick reads differ per side (see BUTTON_STATE_* and STICK_SLICE_*).
OFF_PACKET_ID = 0x00        # uint32 LE, sequence/timestamp
OFF_BUTTONS = 0x04          # button bitmap region
OFF_LEFT_STICK = 0x08       # 3 bytes, 12-bit packed  (doc: layout table)
OFF_RIGHT_STICK = 0x0B      # 3 bytes, 12-bit packed
OFF_MOUSE_X = 0x0E
OFF_MOUSE_Y = 0x10
OFF_MAG_X = 0x16
OFF_MAG_Y = 0x18
OFF_MAG_Z = 0x1A
OFF_BATTERY_VOLTAGE = 0x1C  # uint16 LE, mV
OFF_BATTERY_CURRENT = 0x1E  # int16 LE, /100 = mA
OFF_TEMPERATURE = 0x2E      # int16 LE, 25 + raw/127 (deg C)
OFF_ACCEL = 0x30            # 3x int16 LE
OFF_GYRO = 0x36             # 3x int16 LE
OFF_TRIGGER_L = 0x3C        # uint8
OFF_TRIGGER_R = 0x3D        # uint8

MIN_IMU_PACKET_LEN = 0x3E   # 62 bytes

# Button-state window as used by the reference decoder ([FR-PY] solo_logic.py):
#   big-endian int over a 3-byte slice, start offset differs per side.
BUTTON_STATE_SLICE_LEFT = slice(4, 7)
BUTTON_STATE_SLICE_RIGHT = slice(3, 6)

# Stick slice as used by the reference decoder ([FR-PY] solo_logic.py) --
# note this differs from the layout table (0x08 / 0x0B) by ~2 bytes; unverified.
STICK_SLICE_LEFT = slice(10, 13)
STICK_SLICE_RIGHT = slice(13, 16)

# --- Scaling ---------------------------------------------------------------  [FR-PY]
ACCEL_RAW_PER_G = 4096.0            # raw / 4096 -> g
GYRO_RAW_PER_360DPS = 48000.0      # raw * 360 / 48000 -> deg/s
GYRO_DPS_PER_RAW = 360.0 / GYRO_RAW_PER_360DPS
GYRO_RADPS_PER_RAW = GYRO_DPS_PER_RAW * math.pi / 180.0

STICK_CENTER = 2048.0              # 12-bit, 0..4095
STICK_HALF_RANGE = 2048.0

BATTERY_MV_PER_V = 1000.0
BATTERY_RAW_PER_MA = 100.0
TEMP_BASE_C = 25.0
TEMP_RAW_DIVISOR = 127.0

# --- Behaviour quirks --------------------------------------------------  [FR-PY][MIS]
# Rapid reconnect attempts trigger a controller-level cooldown; the device
# refuses connections for several minutes. Handled by ReconnectPolicy.
RECONNECT_COOLDOWN_HINT_S = 180

# --- Sampling ------------------------------------------------------------------ [EIMU]
NOMINAL_SAMPLE_RATE_HZ = 62
