"""Minimal integration example (Python): Joy-Con 2 buttons and sticks from the
adapter, without touching BLE packets or the IMU.

    python -m adapter.src.service --source joycon2        # or --source synthetic --side both
    python examples/input_client.py                        # both controllers
    python examples/input_client.py right                  # pick one

Only needs `websockets`. Implements the client rules from
shared/protocol/README.md (section 6): edge-detect press/release from the state
frames, and treat a controller as released/centred whenever it is not online
or the socket drops -- that is what prevents stuck keys.
"""

from __future__ import annotations

import asyncio
import json
import sys

import websockets

URL = "ws://127.0.0.1:8765"
PROTOCOL_VERSION = 2


class Controller:
    def __init__(self, side: str):
        self.side = side
        self.online = False
        self.buttons: dict[str, bool] = {}
        self.stick = (0.0, 0.0)

    def release_all(self, reason: str) -> None:
        for name, down in self.buttons.items():
            if down:
                print(f"[{self.side}] {name} up ({reason})")
        self.buttons = dict.fromkeys(self.buttons, False)
        self.stick = (0.0, 0.0)


async def main(wanted: list[str]) -> None:
    pads = {s: Controller(s) for s in wanted}
    while True:
        try:
            async with websockets.connect(URL) as ws:
                print("[adapter] open")
                async for text in ws:
                    msg = json.loads(text)
                    if msg.get("v") != PROTOCOL_VERSION:
                        print(f"protocol v{msg.get('v')} != v{PROTOCOL_VERSION}")
                        continue
                    d = msg["data"]
                    pad = pads.get(d.get("controller"))
                    if pad is None:
                        continue
                    if msg["type"] == "status":
                        pad.online = d["connection"] == "connected"
                        if not pad.online:
                            pad.release_all("offline")
                        print(f"[{pad.side}] {'ONLINE' if pad.online else 'offline'} ({d['connection']})")
                    elif msg["type"] == "frame" and pad.online:
                        for name, down in d["buttons"].items():
                            if down != pad.buttons.get(name, False):
                                print(f"[{pad.side}] {name} {'down' if down else 'up'}")
                        pad.buttons = d["buttons"]
                        pad.stick = (d["stick"]["x"], d["stick"]["y"])
                        if pad.buttons.get("a") and pad.buttons.get("b"):
                            print("A+B combo!")
        except OSError:
            pass
        except websockets.ConnectionClosed:
            pass
        print("[adapter] closed -- retrying in 1 s")
        for pad in pads.values():
            pad.online = False
            pad.release_all("transport")
        await asyncio.sleep(1.0)


if __name__ == "__main__":
    try:
        asyncio.run(main(sys.argv[1:] or ["left", "right"]))
    except KeyboardInterrupt:
        pass
