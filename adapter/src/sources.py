"""Frame sources -- where raw packets come from.

Every source yields, in order, either a raw frame `(raw_bytes, side, t_recv)` or
a `StateChange` for one controller. Both travel through one queue so a
controller's "disconnected" can never be overtaken by one of its own earlier
frames. Swapping the source is how the adapter runs with no hardware (GOAL.md
§13 fallback) without changing the decode / calibrate / websocket code below it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .decoder.buttons import BUTTONS_LEFT, BUTTONS_RIGHT
from .decoder.encode import build_raw_packet
from .protocol.constants import NOMINAL_SAMPLE_RATE_HZ

log = logging.getLogger("adapter.sources")

Frame = tuple[bytes, str, float]
SIDES = ("left", "right")


@dataclass(frozen=True)
class StateChange:
    side: str
    state: str  # shared/protocol CONNECTION_STATES
    hint: str | None = None
    info: dict[str, Any] = field(default_factory=dict)


SourceItem = Frame | StateChange


class FrameSource:
    name = "base"

    def frames(self) -> AsyncIterator[SourceItem]:  # pragma: no cover - interface
        raise NotImplementedError

    async def aclose(self) -> None:  # pragma: no cover - default
        return None


class SyntheticSource(FrameSource):
    """No hardware. Lies still for the first STILL_S (so the adapter's IMU
    calibration completes, like a controller set down on a desk), then a smooth
    sine wobble with a scripted slash every few seconds. Throughout: a scripted
    button walk (one button at a time, 0.3 s each) and a stick circling at full
    deflection, so input consumers have something to show."""

    STILL_S = 4.5

    name = "synthetic"

    def __init__(self, sides: tuple[str, ...] = ("left",), rate_hz: int = NOMINAL_SAMPLE_RATE_HZ):
        self.sides = sides
        self.rate_hz = rate_hz
        self._stop = False

    @staticmethod
    def _buttons(side: str, t: float) -> dict[str, bool]:
        names = BUTTONS_LEFT if side == "left" else BUTTONS_RIGHT
        k, phase = divmod(t, 1.0)
        return {names[int(k) % len(names)]: True} if phase < 0.3 else {}

    async def frames(self) -> AsyncIterator[SourceItem]:
        for side in self.sides:
            yield StateChange(side, "connected", info={"address": f"synthetic-{side}"})
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
            if t < self.STILL_S:
                gx = gy = gz = 0.0
                ax = ay = 0.0
            for i, side in enumerate(self.sides):
                a = t * 1.2 + i * math.pi
                raw = build_raw_packet(
                    side=side, seq=seq,
                    accel_g=(ax, ay, az), gyro_dps=(gx, gy, gz),
                    stick_raw=(round(2048 + 1200 * math.cos(a)), round(2048 + 1200 * math.sin(a))),
                    buttons=self._buttons(side, t),
                )
                yield raw, side, time.monotonic()
            seq += 1
            await asyncio.sleep(dt)

    async def aclose(self) -> None:
        self._stop = True


class ReplaySource(FrameSource):
    """Replay a capture file.

    Two formats:
      *.jsonl -- adapter `--record` output: packets (with side and original
                 timing), controller state changes and action marks. Replays
                 the session as it happened, including connects/disconnects.
      other   -- one hex packet per line (spaces optional), replayed as `side`
                 at `rate_hz`.
    """

    name = "replay"

    def __init__(self, path: str | Path, side: str = "left", rate_hz: int = NOMINAL_SAMPLE_RATE_HZ,
                 loop: bool = True, max_gap_s: float = 1.0, speed: float = 1.0):
        self.path = Path(path)
        self.side = side
        self.rate_hz = rate_hz
        self.loop = loop
        self.max_gap_s = max_gap_s
        self.speed = speed  # .jsonl playback speed; 0 = as fast as possible
        self._stop = False

    def _hex_packets(self) -> list[bytes]:
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

    def records(self) -> list[tuple[float, SourceItem]]:
        """(original t, item) for a .jsonl capture, in file order."""
        out: list[tuple[float, SourceItem]] = []
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("kind") == "packet":
                out.append((r["t"], (bytes.fromhex(r["hex"]), r["side"], r["t"])))
            elif r.get("kind") == "state":
                out.append((r["t"], StateChange(r["side"], r["state"], r.get("hint"), r.get("info") or {})))
        if not out:
            raise ValueError(f"no packets in {self.path}")
        return out

    async def _replay_jsonl(self) -> AsyncIterator[SourceItem]:
        recs = self.records()
        prev = recs[0][0]
        for t, item in recs:
            if self._stop:
                return
            await asyncio.sleep(min(max(0.0, t - prev), self.max_gap_s) / self.speed if self.speed > 0 else 0)
            prev = t
            if isinstance(item, StateChange):
                yield item
            else:
                yield item[0], item[1], time.monotonic()

    async def frames(self) -> AsyncIterator[SourceItem]:
        if self.path.suffix == ".jsonl":
            while not self._stop:
                async for item in self._replay_jsonl():
                    yield item
                if not self.loop:
                    break
            return
        packets = self._hex_packets()
        yield StateChange(self.side, "connected", info={"address": f"replay:{self.path.name}"})
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
    """Real hardware via BLE: up to one LEFT and one RIGHT Joy-Con 2 at once.

    Scans until every wanted side has a connection; each connection then keeps
    itself alive (reconnect + backoff) by address. A controller whose side is
    not in the advertisement is connected anyway and identified from its GATT
    table before input starts.
    """

    name = "joycon2"

    def __init__(self, sides: tuple[str, ...] = SIDES, address: str | None = None,
                 scan_timeout: float = 8.0, max_queue: int = 512):
        self.sides = tuple(sides)
        self.address = address
        self.scan_timeout = scan_timeout
        self.max_queue = max_queue
        # Unbounded so a StateChange is never dropped; frames are shed by hand
        # past max_queue instead.
        self._queue: asyncio.Queue[SourceItem] = asyncio.Queue()
        self._conns: dict[str, Any] = {}  # side -> the JoyConConnection that owns it
        self._all: list[Any] = []
        self._tasks: list[asyncio.Task] = []
        self._discovery: asyncio.Task | None = None
        self.dropped = 0
        self.settle_s = 2.0  # after starting connections: let unknown-side units resolve
        self.idle_s = 0.5    # between empty scans

    def _put_state(self, side: str, state: str, hint: str | None = None, info: dict | None = None) -> None:
        self._queue.put_nowait(StateChange(side, state, hint, info or {}))

    def _start(self, address: str, side: str, device: Any = None) -> None:
        from .bluetooth.connection import JoyConConnection

        holder: dict[str, Any] = {}

        def owns(conn: Any) -> bool:
            return not holder.get("ignored") and self._conns.get(conn.side) is conn

        def on_notify(data: bytes) -> None:
            conn = holder["conn"]
            if not owns(conn):
                return  # side not resolved yet, not wanted, or a duplicate
            if self._queue.qsize() >= self.max_queue:
                self.dropped += 1
                return  # never block the BLE callback; a dropped frame is fine
            self._queue.put_nowait((data, conn.side, time.monotonic()))

        def on_state(state: str, hint: str | None, info: dict) -> None:
            conn = holder["conn"]
            if state == "connected" and not holder.get("ignored"):
                owner = self._conns.get(conn.side)
                if conn.side not in self.sides or owner not in (None, conn):
                    log.warning("%s (%s) not used: side unwanted or already connected", address, conn.side)
                    holder["ignored"] = True
                    conn.stop()
                else:
                    for k, v in list(self._conns.items()):
                        if v is conn and k != conn.side:  # GATT corrected the advertised side
                            del self._conns[k]
                    self._conns[conn.side] = conn
            if owns(conn):
                self._put_state(conn.side, state, hint, info)

        conn = JoyConConnection(address, device=device, side=side, on_notification=on_notify, on_state_change=on_state)
        holder["conn"] = conn
        self._all.append(conn)
        if side in self.sides:
            self._conns[side] = conn
        self._tasks.append(asyncio.create_task(conn.run()))

    def _missing(self) -> list[str]:
        return [s for s in self.sides if s not in self._conns]

    async def _discover(self) -> None:
        from .bluetooth.scanner import BluetoothUnavailable, scan_for_controllers

        for s in self.sides:
            self._put_state(s, "connecting", f"looking for the {s} Joy-Con 2 -- hold its Sync button until the LEDs run")
        if self.address:
            self._start(self.address, self.sides[0] if len(self.sides) == 1 else "unknown")
            return
        seen: set[str] = set()  # every address already started or skipped; never re-reported
        while self._missing():
            try:
                found = await scan_for_controllers(
                    timeout=self.scan_timeout, want=len(self._missing()), exclude_addresses=seen,
                )
            except BluetoothUnavailable as exc:
                for s in self._missing():
                    self._put_state(s, "connecting", f"Bluetooth unavailable ({exc}) -- retrying")
                await asyncio.sleep(5.0)
                continue
            for c in found:
                seen.add(c.address)
                if c.side != "unknown" and c.side not in self._missing():
                    log.info("ignoring %s (%s): side not wanted or already connected", c.address, c.side)
                    continue
                log.info("found %s addr=%s side=%s (from %s) mdata=%s",
                         c.name, c.address, c.side, c.side_source, c.manufacturer_data.hex(" "))
                self._start(c.address, c.side, c.device)
            # unknown-side units resolve their side asynchronously; give them a moment
            await asyncio.sleep(self.settle_s if found else self.idle_s)

    async def frames(self) -> AsyncIterator[SourceItem]:
        self._discovery = asyncio.create_task(self._discover())
        try:
            while True:
                yield await self._queue.get()
        finally:
            await self.aclose()

    async def aclose(self) -> None:
        if self._discovery is not None:
            self._discovery.cancel()
        for conn in self._all:
            conn.stop()
        for t in self._tasks:
            if not t.done():
                try:
                    await asyncio.wait_for(asyncio.shield(t), timeout=3.0)
                except (asyncio.TimeoutError, asyncio.CancelledError, Exception):  # noqa: BLE001
                    t.cancel()


def resolve_sides(side: str | None, kind: str) -> tuple[str, ...]:
    """CLI --side -> tuple of sides. joycon2 defaults to both, the others to left."""
    if side == "both" or (side is None and kind == "joycon2"):
        return SIDES
    return (side or "left",)


def make_source(kind: str, **kw) -> FrameSource:
    kind = kind.lower()
    sides = resolve_sides(kw.get("side"), kind)
    if kind == "synthetic":
        return SyntheticSource(sides=sides)
    if kind == "replay":
        return ReplaySource(kw["file"], side=sides[0], loop=kw.get("loop", True), speed=kw.get("speed") or 1.0)
    if kind == "joycon2":
        return JoyCon2Source(sides=sides, address=kw.get("address"))
    raise ValueError(f"unknown source: {kind}")
