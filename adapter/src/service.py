"""Phase 3 deliverable: the full adapter.

    source -> decode -> calibrate -> normalize -> WebSocket broadcast

Every decoded packet becomes exactly one `frame` message; the server never
coalesces or drops on the happy path, so the browser sees the device rate
(GOAL.md §9).

Buttons and sticks are broadcast from the first packet. The IMU still-
calibration runs alongside, per controller: frames carry `imuReady: false`
until it has completed (it waits for ~2 s of stillness), then the bias is
applied and the controller's status flips to `calibrated: true`. A
controller keeps its calibration and stick centre across reconnects.

    python -m adapter.src.service --source synthetic [--side both]
    python -m adapter.src.service --source replay --file adapter/tests/fixtures/left_idle.hex
    python -m adapter.src.service --source joycon2                 # left + right
    python -m adapter.src.service --source joycon2 --side right    # only the right one
    python -m adapter.src.service --source joycon2 --record adapter/captures/session.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from shared.protocol.frame import HelloData, StatusData

from .calibration.calibrator import CalibrationResult, Calibrator
from .calibration.stick import StickNormalizer, parse_factory_stick_cal
from .capture import CaptureWriter
from .decoder.packet import PacketTooShort, decode_packet
from .normalize import to_input_frame
from .sources import StateChange, make_source
from .websocket.server import BroadcastServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("adapter.service")

ADAPTER_VERSION = "0.2.0"

# A calibration window whose gyro noise exceeds this (1-sigma, deg/s, worst
# axis) was not still -- the controller was being handled -- so it is thrown
# away and collection restarts. Real units at rest read ~0.1-0.3 dps.
STILL_MAX_NOISE_DPS = 2.0


@dataclass
class Device:
    side: str
    stick: StickNormalizer = field(default_factory=StickNormalizer)
    calibrator: Calibrator | None = None
    calibration: CalibrationResult | None = None
    connection: str = "connecting"
    address: str | None = None
    hint: str | None = None
    decoded: int = 0
    stick_logged: str = ""

    @property
    def imu_ready(self) -> bool:
        return self.calibration is not None or self.calibrator is None

    def status(self) -> StatusData:
        return StatusData(self.connection, calibrated=self.calibration is not None,
                          controller=self.side, hint=self.hint, address=self.address)


class Adapter:
    def __init__(self, args: argparse.Namespace, source=None):
        self.args = args
        self.recorder: CaptureWriter | None = None
        self.server = BroadcastServer(host=args.host, port=args.port, on_message=self._on_client_message)
        self.source = source or make_source(args.source, side=args.side, file=args.file, loop=True,
                                            speed=args.speed)
        self.devices: dict[str, Device] = {}
        self._decoded = 0
        self._short = 0

    def _device(self, side: str) -> Device:
        dev = self.devices.get(side)
        if dev is None:
            dev = Device(side, calibrator=None if self.args.no_calibrate else Calibrator())
            self.devices[side] = dev
        return dev

    def _on_client_message(self, msg: dict[str, Any]) -> None:
        if self.recorder is not None:
            self.recorder.mark(msg["data"])

    async def _on_state(self, ev: StateChange) -> None:
        dev = self._device(ev.side)
        dev.connection = ev.state
        dev.hint = ev.hint
        dev.address = ev.info.get("address", dev.address)
        if self.recorder is not None:
            self.recorder.state(ev.side, ev.state, ev.hint, ev.info)
        cal = parse_factory_stick_cal((ev.info.get("flash") or {}).get("factory"))
        if ev.state == "connected" and cal is not None:
            dev.stick.apply_factory(cal)
        if ev.state == "connected" and dev.calibration is None and dev.calibrator is not None:
            dev.calibrator.reset()
            dev.hint = "buttons and sticks live; IMU calibrating -- set the Joy-Con down still for ~2 s"
        log.info("%s: %s%s", ev.side, ev.state, f" ({dev.hint})" if dev.hint else "")
        await self.server.send_status(dev.status())

    async def _calibrate_step(self, dev: Device, pkt) -> None:
        cal = dev.calibrator
        cal.feed(pkt)
        if cal.progress < 1.0:
            return
        res = cal.finish()
        noise = max(res.gyro_noise.x, res.gyro_noise.y, res.gyro_noise.z)
        cal.reset()
        if noise > STILL_MAX_NOISE_DPS:
            return  # moved during the window -- collect again
        dev.calibration = res
        dev.hint = None
        log.info(
            "%s: IMU calibration complete: %d samples, gyro_bias=(%.2f,%.2f,%.2f) dps, deadzone=%.2f dps",
            dev.side, res.samples, res.gyro_bias.x, res.gyro_bias.y, res.gyro_bias.z, res.gyro_deadzone_dps,
        )
        await self.server.send_status(dev.status())

    async def _on_frame(self, raw: bytes, side: str, t_recv: float) -> None:
        if self.recorder is not None:
            self.recorder.packet(t_recv, side, raw)
        try:
            pkt = decode_packet(raw, side)
        except PacketTooShort:
            self._short += 1
            return
        dev = self._device(side)
        pkt.stick = dev.stick.normalize(*pkt.stick_raw)
        if dev.calibration is not None:
            dev.calibration.apply(pkt)
        elif dev.calibrator is not None:
            await self._calibrate_step(dev, pkt)
        dev.decoded += 1
        self._decoded += 1
        await self.server.send_frame(to_input_frame(pkt, t_recv, imu_ready=dev.imu_ready).to_message())

    async def _stats_loop(self) -> None:
        last = time.monotonic()
        last_decoded = 0
        last_sent = 0
        per_side: dict[str, int] = {}
        while True:
            await asyncio.sleep(2.0)
            now = time.monotonic()
            dt = now - last
            in_hz = (self._decoded - last_decoded) / dt
            out_hz = (self.server.frames_sent - last_sent) / dt
            sides = "  ".join(
                f"{d.side}={(d.decoded - per_side.get(d.side, 0)) / dt:.1f}Hz/{d.connection}"
                for d in self.devices.values()
            )
            log.info(
                "in=%.1f Hz  out=%.1f Hz  clients=%d  short=%d  (out/in=%.2f)  %s",
                in_hz, out_hz, self.server.client_count, self._short,
                (out_hz / in_hz) if in_hz else 0.0, sides,
            )
            for d in self.devices.values():
                per_side[d.side] = d.decoded
                desc = d.stick.describe()
                if desc != d.stick_logged:
                    log.info("%s stick: %s", d.side, desc)
                    d.stick_logged = desc
            last, last_decoded, last_sent = now, self._decoded, self.server.frames_sent

    async def run(self) -> None:
        if self.args.record:
            self.recorder = CaptureWriter(self.args.record, adapter=ADAPTER_VERSION, source=self.source.name)
            log.info("recording to %s", self.args.record)
        self.server.set_hello(
            HelloData(adapter=ADAPTER_VERSION, source=self.source.name, rate_hz=62)
        )
        await self.server.start()

        stats = asyncio.create_task(self._stats_loop())
        try:
            async for item in self.source.frames():
                if isinstance(item, StateChange):
                    await self._on_state(item)
                else:
                    await self._on_frame(*item)
        finally:
            stats.cancel()
            await self.source.aclose()
            for dev in self.devices.values():
                dev.connection, dev.hint = "stopped", None
                await self.server.send_status(dev.status())
            await self.server.stop()
            if self.recorder is not None:
                self.recorder.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Joy-Con 2 adapter: decode + WebSocket bridge")
    p.add_argument("--source", default="synthetic", choices=["synthetic", "replay", "joycon2"])
    p.add_argument("--file", help="capture file for --source replay (.jsonl recording or hex lines)")
    p.add_argument("--speed", type=float, default=1.0, help="replay speed for .jsonl recordings (e.g. 10)")
    p.add_argument("--side", choices=["left", "right", "both"],
                   help="joycon2: which controllers to connect (default both); "
                        "synthetic/replay: which side to emulate (default left)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-calibrate", action="store_true", help="skip the adapter's IMU still-calibration")
    p.add_argument("--record", metavar="FILE.jsonl", help="append every raw packet, state change and mark")
    return p


def main(argv: list[str] | None = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    if args.source == "replay" and not args.file:
        p.error("--source replay requires --file")
    try:
        asyncio.run(Adapter(args).run())
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
