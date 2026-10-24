"""Joy-Con 2 BLE protocol constants.

Sources (see docs/JOYCON2_PROTOCOL.md for full attribution):
  [FR-PY]  TheFrano/joycon2py  -- main.py / solo_logic.py, layout by @german77
  [FR-CPP] TheFrano/joycon2cpp
  [MIS]    Misaka10571/joycon2-connector
  [EIMU]   matiaspalmac/everything-imu  -- 62 Hz sampling, hardware-validated
  [ND]     ndeadly/switch2_controller_research -- hid_reports.md,
           bluetooth_interface.md, commands.md, memory_layout.md

STATUS: core link verified on real hardware (macOS, both sides). Per-field
status is in the comments below and in docs/JOYCON2_PROTOCOL.md section J.
"""

from __future__ import annotations

import math

# --- BLE advertisement identification -------------------------------------  [FR-PY]
MANUFACTURER_ID = 1363  # 0x0553, Nintendo Switch 2 controller family
MANUFACTURER_PREFIX = bytes([0x01, 0x00, 0x03, 0x7E])

# --- GATT characteristics ----------------------------------------------------  [FR-PY]
INPUT_REPORT_UUID = "ab7de9be-89fe-49ad-828f-118f09df7fd2"   # Notify
WRITE_COMMAND_UUID = "649d4ac9-8eb7-4e6c-af44-1ea54fe5f005"  # Write
# Service UUID: verified on hardware 2026-09-06 (macOS, both Joy-Con 2 units) --
# both characteristics above live under this proprietary primary service.
INPUT_SERVICE_UUID = "ab7de9be-89fe-49ad-828f-118f09df7fd0"
# Command responses arrive here ([ND] bluetooth_interface.md, "Command Response #1";
# Joy2Win controller_command.py uses the same UUID). Only used for the
# best-effort factory stick-calibration read.
COMMAND_RESPONSE_UUID = "c765a961-d9d8-4d36-a20a-5315b111836a"

# Side-specific characteristics ([ND] bluetooth_interface.md, handle 0x000E):
# only a LEFT unit exposes the first, only a RIGHT unit the second. Used to
# confirm the side after connecting when the advertisement did not say.
SIDE_CHAR_LEFT = "cc1bbbb5-7354-4d32-a716-a81cb241a32a"
SIDE_CHAR_RIGHT = "d5a9e01e-2ffc-4cca-b20c-8b67142bf442"

# Advertisement product id ([ND] bluetooth_interface.md manufacturer data
# offset 0x7, i.e. index 5..6 of bleak's manufacturer_data payload, LE;
# ids from [ND] descriptors.md).
ADV_PRODUCT_ID_SLICE = slice(5, 7)
PRODUCT_ID_RIGHT = 0x2066
PRODUCT_ID_LEFT = 0x2067

# --- Command / subcommand ids ---------------------------------------------  [FR-PY]
COMMAND_FLASH = 0x02  # [ND] commands.md "Flash Memory"
COMMAND_LEDS = 0x09
COMMAND_VIBRATION = 0x0A
COMMAND_CONFIG = 0x0C  # inferred: config/IMU domain (first byte of ENABLE_IMU_*)

SUBCOMMAND_SET_PLAYER_LEDS = 0x07
SUBCOMMAND_PLAY_VIBRATION_PRESET = 0x02
SUBCOMMAND_FLASH_READ = 0x04  # [ND] "Memory Read": payload len|0x7E|00 00|addr u32 LE

# Flash addresses ([ND] memory_layout.md). The console reads both while
# connecting a Joy-Con 2 ([ND] bluetooth_interface.md connection log).
FLASH_FACTORY_STICK_CAL = 0x130A8   # 9 bytes, "Primary analog stick calibration"
FLASH_USER_STICK_CAL = 0x1FC040     # 11 bytes, all 0xFF unless user-calibrated

# Two raw 12-byte writes to WRITE_COMMAND_UUID, ~0.5s apart, enable the IMU.  [FR-PY]
ENABLE_IMU_1 = bytes([0x0C, 0x91, 0x01, 0x02, 0x00, 0x04, 0x00, 0x00, 0x2F, 0x00, 0x00, 0x00])
ENABLE_IMU_2 = bytes([0x0C, 0x91, 0x01, 0x04, 0x00, 0x04, 0x00, 0x00, 0x2F, 0x00, 0x00, 0x00])
ENABLE_IMU_GAP_S = 0.5

# Player LED bit patterns P1..P8 (reproduces Switch pattern).                 [FR-PY]
LED_PATTERN_BY_PLAYER = {
    1: 0x01, 2: 0x03, 3: 0x07, 4: 0x0F,
    5: 0x09, 6: 0x05, 7: 0x0D, 8: 0x06,
}

# --- Packet layout (IMU enabled) -----------------------------------  [FR-PY] + HW
# Byte offsets. IMU / battery / temperature offsets are identical for L and R;
# button + stick reads differ per side (see BUTTON_STATE_* and STICK_SLICE_*).
# "HW" notes: right Joy-Con 2, macOS CoreBluetooth, 2026-09-06
# (see docs/HARDWARE_BRINGUP.md). Real packets are 63 bytes, not 62.
OFF_PACKET_ID = 0x00        # uint32 LE -- HW: millisecond timestamp (~1000/s), monotonic
OFF_BUTTONS = 0x04          # button bitmap region -- HW: bits live in bytes 0x04 / 0x05
OFF_LEFT_STICK = 0x08       # 3 bytes, 12-bit packed  (doc: layout table)
OFF_RIGHT_STICK = 0x0B      # 3 bytes, 12-bit packed
OFF_MOUSE_X = 0x0E
OFF_MOUSE_Y = 0x10
OFF_MAG_X = 0x16
OFF_MAG_Y = 0x18
OFF_MAG_Z = 0x1A
OFF_BATTERY_VOLTAGE = 0x1F  # uint16 LE, mV -- HW: 0x1F reads ~3690 mV; the doc's 0x1C reads 0
OFF_BATTERY_CURRENT = 0x1E  # int16 LE, /100 = mA -- HW: reads 0 at idle; UNVERIFIED
OFF_TEMPERATURE = 0x2E      # int16 LE, 25 + raw/127 -- HW: negative garbage here; UNVERIFIED
OFF_ACCEL = 0x30            # 3x int16 LE -- HW-VERIFIED: |a| = 1.00 g in all 6 orientations
OFF_GYRO = 0x36             # 3x int16 LE -- HW-VERIFIED: <2 dps at rest, axis-correct on rotation
OFF_TRIGGER_L = 0x3C        # uint8 -- HW: reads 0 (right JC ZR digital in this mode); UNVERIFIED
OFF_TRIGGER_R = 0x3D        # uint8 -- UNVERIFIED

MIN_IMU_PACKET_LEN = 0x3E   # 62 -- floor for the "IMU enabled?" gate; real packets are 63

# Button-state window as used by the reference decoder ([FR-PY] solo_logic.py):
#   big-endian int over a 3-byte slice, start offset differs per side.
# HW-VERIFIED both sides, every button by label on 2026-10-24 (right A/B/X/Y/SL/SR
# corrected that day, see decoder/buttons.py).
BUTTON_STATE_SLICE_LEFT = slice(4, 7)
BUTTON_STATE_SLICE_RIGHT = slice(3, 6)

# Stick slice as used by the reference decoder ([FR-PY] solo_logic.py) --
# note this differs from the layout table (0x08 / 0x0B) by ~2 bytes.
# HW-VERIFIED both sides (2026-09-06 / 09-28 / 10-24): +x right, +y up; the other
# side's slot holds the placeholder ff f7 7f (= 2047, 2047). Rest points are NOT
# 2048: right ~(2109, 1987), left ~(1895, 2161) -- see calibration/stick.py.
# [ND] hid_reports.md agrees: left stick 0x0A, right stick 0x0D, "uncalibrated".
STICK_SLICE_LEFT = slice(10, 13)
STICK_SLICE_RIGHT = slice(13, 16)

# --- Scaling ---------------------------------------------------------------  [FR-PY]
ACCEL_RAW_PER_G = 4096.0            # raw / 4096 -> g
GYRO_RAW_PER_360DPS = 48000.0      # raw * 360 / 48000 -> deg/s
GYRO_DPS_PER_RAW = 360.0 / GYRO_RAW_PER_360DPS
GYRO_RADPS_PER_RAW = GYRO_DPS_PER_RAW * math.pi / 180.0

# Sticks are 12-bit (0..4095) but the physical gate only travels about
# +-1150..1250 counts from centre (HW 2026-09-06 right unit 900..3300), which is
# why the old "(raw - 2048) / 2048" never got past +-0.6. See
# calibration/stick.py for the per-controller normaliser built on these.
STICK_CENTER = 2048.0              # nominal centre; real rest point differs per unit
STICK_NOMINAL_EXTENT = 1100.0      # counts from centre treated as full deflection until a bigger push is seen
STICK_MAX_EXTENT = 1900.0          # sanity cap for the learned extent
STICK_CENTER_BAND = 300.0          # a rest centre is only accepted this close to 2048
STICK_DEADZONE = 0.08              # radial, in normalised units

BATTERY_MV_PER_V = 1000.0
BATTERY_RAW_PER_MA = 100.0
TEMP_BASE_C = 25.0
TEMP_RAW_DIVISOR = 127.0

# --- Behaviour quirks --------------------------------------------------  [FR-PY][MIS]
# Rapid reconnect attempts trigger a controller-level cooldown; the device
# refuses connections for several minutes. Handled by ReconnectPolicy.
RECONNECT_COOLDOWN_HINT_S = 180

# --- Sampling ------------------------------------------------------------------ [EIMU]
# [EIMU] claims 62 Hz native. HW 2026-09-06: measured 33.5 Hz notification rate on
# macOS CoreBluetooth (28 Hz before IMU enable) -- almost certainly BLE
# connection-interval limited on this stack, not a controller cap. One IMU sample
# per packet (12-byte block 0x30..0x3B, no sub-sampling). Used only by the
# synthetic/replay sources for pacing; the live path never resamples.
NOMINAL_SAMPLE_RATE_HZ = 62
