"""End-to-end through the real Adapter + WebSocket, fed by a scripted source."""

import asyncio
import json
import random

import pytest
import websockets

from adapter.src.decoder.encode import build_raw_packet
from adapter.src.service import Adapter, build_parser
from adapter.src.sources import FrameSource, ReplaySource, StateChange
from shared.protocol.frame import PROTOCOL_VERSION


class ScriptedSource(FrameSource):
    name = "scripted"

    def __init__(self):
        self.q: asyncio.Queue = asyncio.Queue()

    async def frames(self):
        while True:
            item = await self.q.get()
            if item is None:
                return
            yield item


async def _free_port() -> int:
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Harness:
    def __init__(self, *extra):
        self.extra = extra
        self.src = ScriptedSource()
        self.t = 0.0
        self.rng = random.Random(7)

    async def __aenter__(self):
        self.port = await _free_port()
        args = build_parser().parse_args(["--port", str(self.port), *self.extra])
        self.adapter = Adapter(args, source=self.src)
        self.task = asyncio.create_task(self.adapter.run())
        for _ in range(100):
            try:
                self.ws = await websockets.connect(f"ws://127.0.0.1:{self.port}")
                break
            except OSError:
                await asyncio.sleep(0.02)
        assert json.loads(await self.ws.recv())["type"] == "hello"
        return self

    async def __aexit__(self, *exc):
        await self.ws.close()
        self.src.q.put_nowait(None)
        await asyncio.wait_for(self.task, timeout=5)

    def state(self, side, state, **info):
        self.src.q.put_nowait(StateChange(side, state, info=info))

    def frame(self, side, buttons=None, still=True, stick_raw=(2048, 2048)):
        self.t += 0.03
        g = 0.3 if still else 40.0
        raw = build_raw_packet(
            side=side, seq=int(self.t * 1000), buttons=buttons or {}, stick_raw=stick_raw,
            gyro_dps=(1.5 + self.rng.gauss(0, g), -0.7 + self.rng.gauss(0, g), self.rng.gauss(0, g)),
        )
        self.src.q.put_nowait((raw, side, self.t))

    async def recv(self, n):
        out = []
        for _ in range(n):
            m = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=3))
            assert m["v"] == PROTOCOL_VERSION
            out.append(m)
        return out


def pressed(msg):
    return sorted(k for k, v in msg["data"]["buttons"].items() if v)


@pytest.mark.asyncio
async def test_dual_controllers_are_isolated_and_buttons_do_not_wait_for_imu():
    async with Harness() as h:
        h.state("left", "connected", address="L-addr")
        h.state("right", "connected", address="R-addr")
        h.frame("left", {"zl": True, "up": True})
        h.frame("right", {"a": True, "home": True})
        h.frame("left", {})
        msgs = await h.recv(5)
        st = [m["data"] for m in msgs[:2]]
        assert [(s["controller"], s["connection"], s["address"]) for s in st] == [
            ("left", "connected", "L-addr"), ("right", "connected", "R-addr")]
        assert all(s["calibrated"] is False for s in st)
        f1, f2, f3 = msgs[2:]
        assert f1["data"]["controller"] == "left" and pressed(f1) == ["up", "zl"]
        assert f2["data"]["controller"] == "right" and pressed(f2) == ["a", "home"]
        assert "a" not in f1["data"]["buttons"] and "up" not in f2["data"]["buttons"]
        assert pressed(f3) == []
        assert all(m["data"]["imuReady"] is False for m in (f1, f2, f3))


@pytest.mark.asyncio
async def test_imu_calibration_is_per_controller_and_needs_stillness():
    async with Harness() as h:
        h.state("left", "connected")
        h.state("right", "connected")
        await h.recv(2)
        for _ in range(130):
            h.frame("left")
            h.frame("right", still=False)  # being handled: must not calibrate
        msgs = await h.recv(261)
        cal = [m["data"] for m in msgs if m["type"] == "status"]
        assert [(c["controller"], c["calibrated"]) for c in cal] == [("left", True)]
        frames = [m["data"] for m in msgs if m["type"] == "frame"]
        assert frames[-2]["controller"] == "left" and frames[-2]["imuReady"] is True
        assert frames[-1]["controller"] == "right" and frames[-1]["imuReady"] is False
        # left bias (1.5, -0.7, 0) deg/s is removed once calibrated
        assert abs(frames[-2]["gyroscope"]["x"]) < 0.05


@pytest.mark.asyncio
async def test_no_calibrate_flag_marks_imu_ready_immediately():
    async with Harness("--no-calibrate") as h:
        h.state("left", "connected")
        h.frame("left")
        _, f = await h.recv(2)
        assert f["data"]["imuReady"] is True


@pytest.mark.asyncio
async def test_disconnect_arrives_after_the_last_frame_and_late_client_sees_both_sides():
    async with Harness() as h:
        h.state("left", "connected")
        h.state("right", "connected")
        h.frame("right", {"zr": True})
        h.state("right", "disconnected")
        h.frame("left", {"l": True})
        msgs = await h.recv(5)
        kinds = [(m["type"], m["data"]["controller"]) for m in msgs]
        assert kinds == [("status", "left"), ("status", "right"), ("frame", "right"),
                         ("status", "right"), ("frame", "left")]
        assert msgs[3]["data"]["connection"] == "disconnected"

        async with websockets.connect(f"ws://127.0.0.1:{h.port}") as late:
            got = [json.loads(await asyncio.wait_for(late.recv(), timeout=2)) for _ in range(3)]
        assert got[0]["type"] == "hello"
        assert {(g["data"]["controller"], g["data"]["connection"]) for g in got[1:]} == {
            ("left", "connected"), ("right", "disconnected")}


@pytest.mark.asyncio
async def test_reconnect_keeps_calibration_and_reports_online_again():
    async with Harness() as h:
        h.state("left", "connected")
        await h.recv(1)
        for _ in range(124):
            h.frame("left")
        await h.recv(125)  # frames + calibrated status
        h.state("left", "disconnected")
        h.state("left", "connecting")
        h.state("left", "connected")
        h.frame("left", {"minus": True})
        msgs = await h.recv(4)
        assert [m["data"]["connection"] for m in msgs[:3]] == ["disconnected", "connecting", "connected"]
        assert msgs[2]["data"]["calibrated"] is True and msgs[2]["data"]["hint"] is None
        assert msgs[3]["data"]["imuReady"] is True and pressed(msgs[3]) == ["minus"]


@pytest.mark.asyncio
async def test_stick_is_normalised_per_controller_with_raw_kept():
    async with Harness() as h:
        h.state("left", "connected")
        h.state("right", "connected")
        await h.recv(2)
        for _ in range(10):
            h.frame("left", stick_raw=(1925, 2191))  # left unit's offset rest point
            h.frame("right", stick_raw=(2047, 2047))
        h.frame("left", stick_raw=(1925, 2191 + 1300))  # full up
        h.frame("right", stick_raw=(2047 + 1250, 2047))  # full right
        msgs = await h.recv(22)
        rest_l = msgs[-4]["data"]
        assert rest_l["controller"] == "left" and rest_l["stick"] == {"x": 0.0, "y": 0.0}
        assert rest_l["stickRaw"] == {"x": 1925, "y": 2191}
        up, right = msgs[-2]["data"], msgs[-1]["data"]
        assert up["stick"] == {"x": 0.0, "y": 1.0}
        assert right["stick"] == {"x": 1.0, "y": 0.0}


@pytest.mark.asyncio
async def test_record_then_replay_reproduces_the_session(tmp_path):
    path = tmp_path / "cap.jsonl"
    async with Harness("--record", str(path)) as h:
        h.state("right", "connected", address="R")
        h.frame("right", {"c": True})
        await h.recv(2)
        await h.ws.send(json.dumps({"v": PROTOCOL_VERSION, "type": "mark", "data": {"step": "press C"}}))
        await asyncio.sleep(0.1)
        h.frame("right", {})
        h.state("right", "disconnected")
        await h.recv(2)

    lines = [json.loads(x) for x in path.read_text().splitlines()]
    assert [r["kind"] for r in lines] == ["meta", "state", "packet", "mark", "packet", "state"]
    assert lines[3]["data"] == {"step": "press C"}

    items = [item for _, item in ReplaySource(path).records()]
    assert isinstance(items[0], StateChange) and items[0].state == "connected"
    assert items[1][1] == "right" and items[2][1] == "right"
    assert isinstance(items[3], StateChange) and items[3].state == "disconnected"
