"""Phase 3 deliverable: the full adapter.

    source -> decode -> calibrate -> normalize -> WebSocket broadcast

Every decoded packet becomes exactly one `frame` message; the server never
coalesces or drops on the happy path, so the browser sees the device rate
(GOAL.md §9).

    python -m adapter.src.service --source synthetic
    python -m adapter.src.service --source replay --file adapter/tests/fixtures/left_idle.hex
    python -m adapter.src.service --source joycon2 --side left      # EXPERIMENTAL
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time

from shared.protocol.frame import HelloData, StatusData

from .calibration.calibrator import Calibrator
from .decoder.packet import PacketTooShort, decode_packet
from .normalize import to_input_frame
from .sources import make_source
from .websocket.server import BroadcastServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("adapter.service")

ADAPTER_VERSION = "0.1.0"


class Adapter:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.server = BroadcastServer(host=args.host, port=args.port)
        self.source = make_source(
            args.source, side=args.side or "left", file=args.file, loop=True
        )
        self.calibrator = Calibrator() if not args.no_calibrate else None
        self.calibration = None
        self._decoded = 0
        self._short = 0

    async def _run_calibration(self, frames) -> None:
        log.info("calibration: hold the controller flat and still (~2 s)")
        await self.server.send_status(StatusData("connected", calibrated=False, controller=self.args.side or "unknown"))
        async for raw, side, _t in frames:
            try:
                pkt = decode_packet(raw, side)
            except PacketTooShort:
                continue
            self.calibrator.feed(pkt)
            if self.calibrator.progress >= 1.0:
                break
        self.calibration = self.calibrator.finish()
        log.info(
            "calibration complete: %d samples, gyro_bias=(%.2f,%.2f,%.2f) dps, deadzone=%.2f dps",
            self.calibration.samples,
            self.calibration.gyro_bias.x,
            self.calibration.gyro_bias.y,
            self.calibration.gyro_bias.z,
            self.calibration.gyro_deadzone_dps,
        )
        await self.server.send_status(
            StatusData("connected", calibrated=True, controller=self.args.side or "unknown")
        )

    async def _stats_loop(self) -> None:
        last = time.monotonic()
        last_decoded = 0
        last_sent = 0
        while True:
            await asyncio.sleep(2.0)
            now = time.monotonic()
            dt = now - last
            in_hz = (self._decoded - last_decoded) / dt
            out_hz = (self.server.frames_sent - last_sent) / dt
            log.info(
                "in=%.1f Hz  out=%.1f Hz  clients=%d  short=%d  (out/in=%.2f)",
                in_hz, out_hz, self.server.client_count, self._short,
                (out_hz / in_hz) if in_hz else 0.0,
            )
            last, last_decoded, last_sent = now, self._decoded, self.server.frames_sent

    async def run(self) -> None:
        self.server.set_hello(
            HelloData(adapter=ADAPTER_VERSION, source=self.source.name, rate_hz=62)
        )
        await self.server.start()
        frames = self.source.frames()

        if self.calibrator is not None:
            try:
                await self._run_calibration(frames)
            except Exception as exc:  # noqa: BLE001
                log.warning("calibration failed, continuing uncalibrated: %s", exc)

        stats = asyncio.create_task(self._stats_loop())
        try:
            async for raw, side, t_recv in frames:
                try:
                    pkt = decode_packet(raw, side)
                except PacketTooShort:
                    self._short += 1
                    continue
                if self.calibration is not None:
                    self.calibration.apply(pkt)
                self._decoded += 1
                await self.server.send_frame(to_input_frame(pkt, t_recv).to_message())
        finally:
            stats.cancel()
            await self.source.aclose()
            await self.server.send_status(StatusData("stopped", calibrated=self.calibration is not None))
            await self.server.stop()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Joy-Con 2 adapter: decode + WebSocket bridge")
    p.add_argument("--source", default="synthetic", choices=["synthetic", "replay", "joycon2"])
    p.add_argument("--file", help="capture file for --source replay")
    p.add_argument("--side", choices=["left", "right"])
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-calibrate", action="store_true")
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
