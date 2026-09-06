"""Phase 1 deliverable: PC BLE connection prototype.

Connects to a real Joy-Con 2 and prints raw notifications (hex) so the offsets in
docs/JOYCON2_PROTOCOL.md can be verified against hardware. Also dumps the full
GATT service tree (needed to fill in the unverified Service UUID).

Usage:
    python -m adapter.src.bluetooth.prototype --scan
    python -m adapter.src.bluetooth.prototype --connect <ADDRESS> [--no-imu] [--seconds N]
    python -m adapter.src.bluetooth.prototype              # scan, then connect to first

STATUS: EXPERIMENTAL. Requires a physical Joy-Con 2 + a working BLE adapter.
Without hardware this prints "no controllers found" and exits 1 -- that is the
expected outcome in an environment with no Bluetooth radio.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time

from bleak import BleakClient

from ..protocol import commands
from ..protocol.constants import (
    ENABLE_IMU_GAP_S,
    INPUT_REPORT_UUID,
    MIN_IMU_PACKET_LEN,
    WRITE_COMMAND_UUID,
)
from .scanner import BluetoothUnavailable, scan_for_controllers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("prototype")


async def do_scan(timeout: float) -> list:
    log.info("scanning %.0fs -- press Sync on the Joy-Con 2 now", timeout)
    try:
        controllers = await scan_for_controllers(timeout=timeout, want=99)
    except BluetoothUnavailable as exc:
        log.error("Bluetooth unavailable: %s", exc)
        log.error("This environment has no usable BLE radio -- expected without hardware.")
        return []
    if not controllers:
        log.warning("no Joy-Con 2 controllers found")
        return []
    for c in controllers:
        log.info("found: %s  addr=%s  side=%s", c.name, c.address, c.side)
    return controllers


async def dump_services(client: BleakClient) -> None:
    log.info("--- GATT services ---")
    for service in client.services:
        log.info("service %s (%s)", service.uuid, service.description)
        for ch in service.characteristics:
            log.info("  char %s  props=%s", ch.uuid, ",".join(ch.properties))


async def do_connect(address: str, enable_imu: bool, seconds: float) -> None:
    count = 0
    first_len = None
    t0 = time.monotonic()

    def on_notify(_sender: object, data: bytearray) -> None:
        nonlocal count, first_len
        count += 1
        if first_len is None:
            first_len = len(data)
            log.info("first notification: %d bytes", first_len)
        if count <= 5 or count % 60 == 0:
            log.info("[%05d] %3dB  %s", count, len(data), data.hex(" "))

    async with BleakClient(address) as client:
        log.info("connected=%s to %s", client.is_connected, address)
        await dump_services(client)
        await client.start_notify(INPUT_REPORT_UUID, on_notify)
        log.info("subscribed to %s (raw, IMU not yet enabled)", INPUT_REPORT_UUID)
        await asyncio.sleep(2.0)

        if enable_imu:
            cmd1, cmd2 = commands.enable_imu_sequence()
            await client.write_gatt_char(WRITE_COMMAND_UUID, cmd1)
            await asyncio.sleep(ENABLE_IMU_GAP_S)
            await client.write_gatt_char(WRITE_COMMAND_UUID, cmd2)
            log.info("IMU enable commands sent")

        await asyncio.sleep(seconds)
        await client.stop_notify(INPUT_REPORT_UUID)

    dt = time.monotonic() - t0
    rate = count / dt if dt else 0.0
    log.info("--- summary ---")
    log.info("notifications=%d  elapsed=%.1fs  rate=%.1f Hz", count, dt, rate)
    if first_len is not None:
        log.info(
            "packet length %d (expected >= %d once IMU enabled)",
            first_len,
            MIN_IMU_PACKET_LEN,
        )


async def main_async(args: argparse.Namespace) -> int:
    if args.connect:
        await do_connect(args.connect, enable_imu=not args.no_imu, seconds=args.seconds)
        return 0

    controllers = await do_scan(args.scan_timeout)
    if args.scan:
        return 0 if controllers else 1
    if not controllers:
        return 1
    await do_connect(controllers[0].address, enable_imu=not args.no_imu, seconds=args.seconds)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Joy-Con 2 BLE connection prototype")
    p.add_argument("--scan", action="store_true", help="scan only, list controllers")
    p.add_argument("--connect", metavar="ADDR", help="connect to this BLE address")
    p.add_argument("--no-imu", action="store_true", help="do not send IMU enable commands")
    p.add_argument("--seconds", type=float, default=10.0, help="stream duration")
    p.add_argument("--scan-timeout", type=float, default=10.0)
    args = p.parse_args(argv)
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
