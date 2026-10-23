"""WebSocket broadcast server for the browser bridge.

Contract: shared/protocol (envelope + InputFrame). One BLE notification maps to
exactly one `frame` message -- no batching, no downsampling (GOAL.md §9).

Status is per controller: the last status of every controller is replayed to a
client when it connects, so a late joiner knows which Joy-Con is online.
Inbound messages are ignored except diagnostic `mark`s, handed to `on_message`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from collections.abc import Callable

import websockets
from websockets.asyncio.server import ServerConnection, serve

from shared.protocol.frame import (
    WS_DEFAULT_HOST,
    WS_DEFAULT_PORT,
    PROTOCOL_VERSION,
    HelloData,
    StatusData,
    envelope,
)

log = logging.getLogger("adapter.ws")


class BroadcastServer:
    def __init__(self, host: str = WS_DEFAULT_HOST, port: int = WS_DEFAULT_PORT,
                 on_message: Callable[[dict[str, Any]], None] | None = None):
        self.host = host
        self.port = port
        self.on_message = on_message
        self._clients: set[ServerConnection] = set()
        self._server: Any = None
        self._hello: dict[str, Any] | None = None
        self._last_status: dict[str, dict[str, Any]] = {}  # controller -> envelope
        self._sent = 0

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def frames_sent(self) -> int:
        return self._sent

    def set_hello(self, hello: HelloData) -> None:
        self._hello = envelope("hello", hello.as_dict())

    async def start(self) -> None:
        self._server = await serve(self._handle, self.host, self.port, ping_interval=10)
        log.info("websocket listening on ws://%s:%d", self.host, self.port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, ws: ServerConnection) -> None:
        self._clients.add(ws)
        log.info("client connected (%d total)", len(self._clients))
        try:
            if self._hello is not None:
                await ws.send(json.dumps(self._hello))
            for status in list(self._last_status.values()):
                await ws.send(json.dumps(status))
            async for text in ws:
                self._inbound(text)
        except websockets.ConnectionClosed:
            pass
        finally:
            self._clients.discard(ws)
            log.info("client disconnected (%d total)", len(self._clients))

    def _inbound(self, text: str | bytes) -> None:
        try:
            msg = json.loads(text)
        except ValueError:
            return
        if (isinstance(msg, dict) and msg.get("v") == PROTOCOL_VERSION and msg.get("type") == "mark"
                and isinstance(msg.get("data"), dict) and self.on_message is not None):
            self.on_message(msg)

    async def _broadcast(self, payload: str) -> None:
        if not self._clients:
            return
        dead: list[ServerConnection] = []
        for ws in self._clients:
            try:
                await ws.send(payload)
            except websockets.ConnectionClosed:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    async def send_frame(self, frame_msg: dict[str, Any]) -> None:
        self._sent += 1
        await self._broadcast(json.dumps(envelope("frame", frame_msg)))

    async def send_status(self, status: StatusData) -> None:
        msg = envelope("status", status.as_dict())
        self._last_status[status.controller] = msg
        await self._broadcast(json.dumps(msg))
