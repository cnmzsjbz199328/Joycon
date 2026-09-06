import asyncio
import json

import pytest
import websockets

from adapter.src.decoder.encode import build_raw_packet
from adapter.src.decoder.packet import decode_packet
from adapter.src.normalize import to_input_frame
from adapter.src.websocket.server import BroadcastServer
from shared.protocol.frame import HelloData, StatusData


async def _free_port() -> int:
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.mark.asyncio
async def test_frames_not_downsampled_and_shape_is_valid():
    port = await _free_port()
    server = BroadcastServer(host="127.0.0.1", port=port)
    server.set_hello(HelloData(adapter="test", source="synthetic", rate_hz=62))
    await server.start()

    n = 200
    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as client:
            hello = json.loads(await asyncio.wait_for(client.recv(), timeout=2))
            assert hello["type"] == "hello" and hello["v"] == 1
            assert hello["data"]["source"] == "synthetic"

            await server.send_status(StatusData("connected", calibrated=True, controller="left"))
            status = json.loads(await asyncio.wait_for(client.recv(), timeout=2))
            assert status["type"] == "status" and status["data"]["calibrated"] is True

            # Fire N frames as fast as possible.
            for seq in range(n):
                raw = build_raw_packet(side="left", seq=seq, gyro_dps=(seq, 0, 0))
                pkt = decode_packet(raw, "left")
                await server.send_frame(to_input_frame(pkt, timestamp=seq * 0.016).to_message())

            received = []
            for _ in range(n):
                msg = json.loads(await asyncio.wait_for(client.recv(), timeout=2))
                assert msg["type"] == "frame" and msg["v"] == 1
                received.append(msg["data"])

        # No downsampling: every frame delivered, in order.
        assert len(received) == n
        assert [f["seq"] for f in received] == list(range(n))
        f0 = received[10]
        assert f0["controller"] == "left"
        assert set(("x", "y", "z")) <= set(f0["gyroscope"])
        # gyro is rad/s on the wire; input was 10 deg/s on x
        assert abs(f0["gyroscope"]["x"] - (10 * 3.14159265 / 180)) < 1e-3
        assert server.frames_sent == n
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_broadcast_to_multiple_clients():
    port = await _free_port()
    server = BroadcastServer(host="127.0.0.1", port=port)
    server.set_hello(HelloData(adapter="test", source="synthetic", rate_hz=62))
    await server.start()
    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as c1, \
                   websockets.connect(f"ws://127.0.0.1:{port}") as c2:
            await asyncio.wait_for(c1.recv(), timeout=2)  # hello
            await asyncio.wait_for(c2.recv(), timeout=2)
            await asyncio.sleep(0.05)
            assert server.client_count == 2

            raw = build_raw_packet(side="right", seq=7)
            pkt = decode_packet(raw, "right")
            await server.send_frame(to_input_frame(pkt, 1.0).to_message())

            m1 = json.loads(await asyncio.wait_for(c1.recv(), timeout=2))
            m2 = json.loads(await asyncio.wait_for(c2.recv(), timeout=2))
            assert m1["data"]["seq"] == 7 == m2["data"]["seq"]
    finally:
        await server.stop()
