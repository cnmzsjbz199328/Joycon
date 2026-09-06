"""Frame sources -- where raw packets come from.

Every source yields (raw_bytes, side, t_recv_monotonic). Swapping the source is
how the adapter runs with no hardware (GOAL.md §13 fallback) without changing the
decode / calibrate / websocket code below it.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import AsyncIterator
from pathlib import Path

from .decoder.encode import build_raw_packet
from .protocol.constants import NOMINAL_SAMPLE_RATE_HZ

Frame = tuple[bytes, str, float]


class FrameSource:
    name = "base"

    def frames(self) -> AsyncIterator[Frame]:  # pragma: no cover - interface
        raise NotImplementedError

    async def aclose(self) -> None:  # pragma: no cover - default
        return None


class SyntheticSource(FrameSource):
    """No hardware. Smooth sine wobble with a scripted slash every few seconds."""

    name = "synthetic"

    def __init__(self, side: str = "left", rate_hz: int = NOMINAL_SAMPLE_RATE_HZ):
        self.side = side
        self.rate_hz = rate_hz
        self._stop = False

    async def frames(self) -> AsyncIterator[Frame]:
        dt = 1.0 / self.rate_hz
        t0 = time.monotonic()
        seq = 0
        while not self._stop:
            t = time.monotonic() - t0
            # gentle idle wobble
            gx = 15.0 * math.sin(t * 1.7)
            gy = 10.0 * math.sin(t * 1.1 + 1.0)
            gz = 8.0 * math.sin(t * 0.9 + 2.0)
            # scripted "slash right" burst: 150 ms every 3 s
            phase = t % 3.0
            if phase < 0.15:
                gz += 600.0 * math.sin(phase / 0.15 * math.pi)
            ax = 0.05 * math.sin(t * 2.0)
            ay = 0.05 * math.cos(t * 1.3)
            az = 1.0
            raw = build_raw_packet(
                side=self.side, seq=seq,
                accel_g=(ax, ay, az), gyro_dps=(gx, gy, gz),
            )
            yield raw, self.side, time.monotonic()
            seq += 1
            await asyncio.sleep(dt)

    async def aclose(self) -> None:
        self._stop = True


class ReplaySource(FrameSource):
    """Replay a capture file: one hex packet per line (spaces optional).

    Produce these with `prototype.py --connect ... | tee`, or hand-craft for tests.
    """

    name = "replay"

    def __init__(self, path: str | Path, side: str = "left", rate_hz: int = NOMINAL_SAMPLE_RATE_HZ, loop: bool = True):
        self.path = Path(path)
        self.side = side
        self.rate_hz = rate_hz
        self.loop = loop
        self._stop = False

    def _packets(self) -> list[bytes]:
        out: list[bytes] = []
        for line in self.path.read_text().splitlines():
            line = line.strip().replace(" ", "")
            if not line or line.startswith("#"):
                continue
            try:
                out.append(bytes.fromhex(line))
            except ValueError:
                continue
        if not out:
            raise ValueError(f"no hex packets in {self.path}")
        return out

    async def frames(self) -> AsyncIterator[Frame]:
        packets = self._packets()
        dt = 1.0 / self.rate_hz
        while not self._stop:
            for raw in packets:
                if self._stop:
                    break
                yield raw, self.side, time.monotonic()
                await asyncio.sleep(dt)
            if not self.loop:
                break

    async def aclose(self) -> None:
        self._stop = True


class JoyCon2Source(FrameSource):
    """Real hardware via BLE. EXPERIMENTAL -- unverified in this environment."""

    name = "joycon2"

    def __init__(self, address: str | None = None, side: str | None = None, scan_timeout: float = 12.0):
        self.address = address
        self.side = side
        self.scan_timeout = scan_timeout
        self._queue: asyncio.Queue[Frame] = asyncio.Queue(maxsize=256)
        self._conn = None
        self._task: asyncio.Task | None = None

    async def _ensure_target(self) -> tuple[str, str]:
        from .bluetooth.scanner import scan_for_controllers

        if self.address:
            return self.address, (self.side or "unknown")
        found = await scan_for_controllers(timeout=self.scan_timeout, want=1)
        if not found:
            raise RuntimeError("no Joy-Con 2 found -- press Sync, or use --source synthetic")
        c = found[0]
        return c.address, (self.side or c.side)

    async def frames(self) -> AsyncIterator[Frame]:
        from .bluetooth.connection import JoyConConnection

        address, side = await self._ensure_target()
        side = side if side in ("left", "right") else "left"

        def on_notify(data: bytes) -> None:
            try:
                self._queue.put_nowait((data, side, time.monotonic()))
            except asyncio.QueueFull:
                pass  # never block the BLE callback; a dropped frame is fine

        self._conn = JoyConConnection(address, side=side, on_notification=on_notify)
        self._task = asyncio.create_task(self._conn.run())
        try:
            while True:
                yield await self._queue.get()
        finally:
            await self.aclose()

    async def aclose(self) -> None:
        if self._conn is not None:
            self._conn.stop()
        if self._task is not None:
            self._task.cancel()


def make_source(kind: str, **kw) -> FrameSource:
    kind = kind.lower()
    if kind == "synthetic":
        return SyntheticSource(side=kw.get("side", "left"))
    if kind == "replay":
        return ReplaySource(kw["file"], side=kw.get("side", "left"), loop=kw.get("loop", True))
    if kind == "joycon2":
        return JoyCon2Source(address=kw.get("address"), side=kw.get("side"))
    raise ValueError(f"unknown source: {kind}")
