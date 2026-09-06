from adapter.src.protocol import commands
from adapter.src.protocol import constants as C


def test_command_frame_shape():
    frame = commands.build_command(C.COMMAND_LEDS, C.SUBCOMMAND_SET_PLAYER_LEDS, b"\x01")
    assert frame[0] == C.COMMAND_LEDS
    assert frame[1:3] == b"\x91\x01"
    assert frame[3] == C.SUBCOMMAND_SET_PLAYER_LEDS
    assert frame[5] == 8  # payload padded to 8
    assert len(frame) == 8 + 8


def test_player_leds_patterns():
    assert commands.set_player_leds(1)[8] == 0x01
    assert commands.set_player_leds(4)[8] == 0x0F
    assert commands.set_player_leds(99)[8] == 0x06  # clamped to P8


def test_enable_imu_sequence_matches_reference():
    c1, c2 = commands.enable_imu_sequence()
    assert c1 == bytes.fromhex("0c910102000400002f000000")
    assert c2 == bytes.fromhex("0c910104000400002f000000")
    assert len(c1) == 12 and c1 != c2
