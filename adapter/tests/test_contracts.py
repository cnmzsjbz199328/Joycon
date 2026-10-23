"""Python, JS and JSON Schema must agree on the wire contract."""

import json
import re
from pathlib import Path

from adapter.src.decoder.buttons import BUTTONS_LEFT, BUTTONS_RIGHT
from adapter.src.decoder.encode import build_raw_packet
from adapter.src.decoder.packet import decode_packet
from adapter.src.normalize import to_input_frame
from shared.protocol.frame import PROTOCOL_VERSION

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "shared/protocol/schema.json").read_text())
MJS = (ROOT / "shared/protocol/contracts.mjs").read_text()


def _mjs_list(name: str) -> list[str]:
    body = re.search(rf"export const {name} = (?:/\*.*?\*/ )?\(?\[(.*?)\]\)?;", MJS, re.S).group(1)
    return re.findall(r'"([^"]+)"', body)


def test_protocol_version_agrees():
    assert SCHEMA["definitions"]["Envelope"]["properties"]["v"]["const"] == PROTOCOL_VERSION
    assert int(re.search(r"export const PROTOCOL_VERSION = (\d+);", MJS).group(1)) == PROTOCOL_VERSION


def test_button_lists_agree_everywhere():
    d = SCHEMA["definitions"]
    assert list(BUTTONS_LEFT) == _mjs_list("BUTTONS_LEFT") == d["ButtonsLeft"]["required"]
    assert list(BUTTONS_RIGHT) == _mjs_list("BUTTONS_RIGHT") == d["ButtonsRight"]["required"]
    assert set(d["ButtonsLeft"]["properties"]) == set(BUTTONS_LEFT)
    assert set(d["ButtonsRight"]["properties"]) == set(BUTTONS_RIGHT)


def test_connection_states_agree():
    assert _mjs_list("CONNECTION_STATES") == SCHEMA["definitions"]["Status"]["properties"]["connection"]["enum"]


def test_frame_matches_schema_fields():
    props = SCHEMA["definitions"]["InputFrame"]["properties"]
    for side, names in (("left", BUTTONS_LEFT), ("right", BUTTONS_RIGHT)):
        msg = to_input_frame(decode_packet(build_raw_packet(side=side), side), 1.0, imu_ready=False).to_message()
        assert set(msg) <= set(props), set(msg) - set(props)
        assert set(SCHEMA["definitions"]["InputFrame"]["required"]) <= set(msg)
        assert list(msg["buttons"]) == list(names)
        assert set(msg["stickRaw"]) == {"x", "y"} and all(isinstance(v, int) for v in msg["stickRaw"].values())
        assert msg["imuReady"] is False
        json.dumps(msg)  # serialisable


def test_status_matches_schema_fields():
    from shared.protocol.frame import StatusData

    props = SCHEMA["definitions"]["Status"]["properties"]
    assert set(StatusData("connected", True, "left", None, "X").as_dict()) == set(props)
