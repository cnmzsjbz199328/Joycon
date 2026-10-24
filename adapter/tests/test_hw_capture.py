"""Regression on REAL hardware data: tests/fixtures/hw_2026-10-24_input.jsonl.

Trimmed from the 2026-10-24 hardware round (macOS, the project's left + right
Joy-Con 2 connected to one adapter at the same time; docs/HARDWARE_BRINGUP.md
§5 "第 5 轮"). Packets are untouched controller bytes; only packets where
nothing moved were dropped. If a decoding change breaks any of these, it
contradicts what the real controllers sent.
"""

import asyncio
import json
import math
from pathlib import Path

import pytest
import websockets

from adapter.src.calibration.stick import StickNormalizer, parse_factory_stick_cal
from adapter.src.decoder.packet import decode_packet
from adapter.src.service import Adapter, build_parser
from adapter.src.sources import ReplaySource, StateChange

FIXTURE = Path(__file__).parent / "fixtures" / "hw_2026-10-24_input.jsonl"
RECORDS = [json.loads(x) for x in FIXTURE.read_text().splitlines() if x.strip()]
T0 = RECORDS[0]["t"]
WINDOWS = RECORDS[0]["windows"]  # [start_s, end_s, what happened]


def _packets(window: int):
    a, b, _ = WINDOWS[window]
    return [r for r in RECORDS if r["kind"] == "packet" and a <= r["t"] - T0 <= b]


def _press_edges(window: int):
    prev, out = {}, []
    for r in _packets(window):
        pressed = {k for k, v in decode_packet(bytes.fromhex(r["hex"]), r["side"]).buttons.items() if v}
        out += [(r["side"], b) for b in sorted(pressed - prev.get(r["side"], set()))]
        prev[r["side"]] = pressed
    return out


def test_every_button_decodes_as_the_label_the_operator_pressed():
    # The operator pressed each button once while watching the input page and
    # confirmed every name lit matched the printed label (ABXY/SL/SR included,
    # after the 2026-10-24 mask fix). The one extra R is a finger slip onto R
    # while pressing SR, visible as R+SR in the same frames.
    assert _press_edges(0) == [
        ("left", b) for b in ("up", "down", "left", "right", "l", "zl", "sl", "sr", "minus", "capture", "stick")
    ] + [
        ("right", b) for b in ("a", "b", "x", "y", "r", "zr", "sl", "sr", "r", "c", "home", "plus", "stick")
    ]


def _factory():
    cals = {}
    for r in RECORDS:
        if r["kind"] == "state" and r["state"] == "connected":
            cals[r["side"]] = parse_factory_stick_cal(r["info"]["flash"]["factory"])
    return cals


def test_factory_calibration_was_read_from_both_units():
    cals = _factory()
    assert cals["left"].center == (1907, 2151) and cals["right"].center == (2124, 1992)


@pytest.mark.parametrize("side", ["left", "right"])
def test_real_stick_reaches_the_edge_everywhere_and_rests_at_zero(side):
    n = StickNormalizer()
    n.apply_factory(_factory()[side])
    pts = [n.normalize(*decode_packet(bytes.fromhex(r["hex"]), side).stick_raw)
           for r in _packets(1) if r["side"] == side]
    assert max(y for _, y in pts) >= 0.95 and min(y for _, y in pts) <= -0.95
    assert max(x for x, _ in pts) >= 0.95 and min(x for x, _ in pts) <= -0.95
    sectors = [0.0] * 8
    for x, y in pts:
        if math.hypot(x, y) > 0.3:
            i = round(math.atan2(y, x) / (math.pi / 4)) % 8
            sectors[i] = max(sectors[i], math.hypot(x, y))
    assert min(sectors) >= 0.95, sectors  # diagonals included
    assert all(math.hypot(x, y) <= 1.0 + 1e-9 for x, y in pts)
    assert (0.0, 0.0) in pts  # released stick reads exactly zero


@pytest.mark.asyncio
async def test_real_session_through_adapter_and_websocket():
    """Window 3 replayed through the real Adapter: both sticks at once, A+B+R
    held, A held through a Sync disconnect, reconnect, A again."""
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    src = ReplaySource(FIXTURE, loop=False, speed=0)
    adapter = Adapter(build_parser().parse_args(["--port", str(port)]), source=src)

    # gate the source until the client is attached, so no message is missed
    gate = asyncio.Event()
    orig = src.frames

    async def gated():
        await gate.wait()
        async for item in orig():
            yield item

    src.frames = gated
    task = asyncio.create_task(adapter.run())
    for _ in range(100):
        try:
            ws = await websockets.connect(f"ws://127.0.0.1:{port}")
            break
        except OSError:
            await asyncio.sleep(0.02)
    await ws.recv()  # hello
    gate.set()
    msgs = []
    try:
        while True:
            m = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
            msgs.append(m)
            if m["type"] == "status" and m["data"]["connection"] == "stopped" and m["data"]["controller"] == "right":
                break
    finally:
        await ws.close()
        await asyncio.wait_for(task, timeout=5)

    status = [(i, m["data"]) for i, m in enumerate(msgs) if m["type"] == "status"]
    frames = [(i, m["data"]) for i, m in enumerate(msgs) if m["type"] == "frame"]
    # both connected, identified by side
    assert {(d["controller"], d["connection"]) for _, d in status} >= {("left", "connected"), ("right", "connected")}

    # both sticks fully deflected at the same time (consecutive frames, one per side)
    both = 0
    last = {}
    for _, f in frames:
        last[f["controller"]] = math.hypot(f["stick"]["x"], f["stick"]["y"])
        if len(last) == 2 and min(last.values()) >= 0.95:
            both += 1
    assert both >= 10

    right = [(i, f) for i, f in frames if f["controller"] == "right"]
    pressed = lambda f: {k for k, v in f["buttons"].items() if v}  # noqa: E731
    assert any(pressed(f) == {"a", "b", "r"} for _, f in right)
    assert all(not pressed(f) & {"x", "y", "zr"} for _, f in right if {"a", "b", "r"} <= pressed(f))

    # the real disconnect: the last right frame before it has A held, the
    # status follows, and nothing for the right side arrives until it is back
    i_disc = next(i for i, d in status if d["controller"] == "right" and d["connection"] == "disconnected")
    i_back = next(i for i, d in status if i > i_disc and d["controller"] == "right" and d["connection"] == "connected")
    before = [f for i, f in right if i < i_disc]
    assert pressed(before[-1]) == {"a"}
    assert not [f for i, f in right if i_disc < i < i_back]
    after = [f for i, f in right if i > i_back]
    assert any("a" in pressed(f) for f in after)
