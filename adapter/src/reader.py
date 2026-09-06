"""Phase 2 deliverable: terminal IMU raw-data reader.

Prints decoded ax/ay/az, gx/gy/gz, buttons and stick in real time. Runs a 2 s
still calibration first (skippable) so the printed values are bias-corrected.

    python -m adapter.src.reader --source synthetic
    python -m adapter.src.reader --source replay --file tests/fixtures/left_idle.hex
    python -m adapter.src.reader --source joycon2 --side left      # EXPERIMENTAL
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from .calibration.calibrator import Calibrator, CalibrationResult
from .decoder.packet import DecodedPacket, PacketTooShort, decode_packet
from .sources import make_source


async def _calibrate(source_frames, calibrator: Calibrator) -> CalibrationResult:
    print("Calibration: hold the Joy-Con flat and still...", flush=True)
    async for raw, side, _t in source_frames:
        try:
            pkt = decode_packet(raw, side)
        except PacketTooShort:
            continue
        calibrator.feed(pkt)
        if calibrator.progress >= 1.0:
            break
        print(f"\r  {calibrator.progress * 100:5.1f}%", end="", flush=True)
    res = calibrator.finish()
    print(
        f"\rCalibration complete: {res.samples} samples  "
        f"gyro_bias=({res.gyro_bias.x:+.2f},{res.gyro_bias.y:+.2f},{res.gyro_bias.z:+.2f}) dps  "
        f"deadzone={res.gyro_deadzone_dps:.2f} dps"
    )
    return res


def _fmt(pkt: DecodedPacket) -> str:
    a, g = pkt.accel_g, pkt.gyro_dps
    pressed = ",".join(k for k, v in pkt.buttons.items() if v) or "-"
    return (
        f"seq={pkt.seq:>7} {pkt.side:<5} "
        f"A[g] {a.x:+6.2f} {a.y:+6.2f} {a.z:+6.2f}   "
        f"G[dps] {g.x:+8.1f} {g.y:+8.1f} {g.z:+8.1f}   "
        f"stick({pkt.stick[0]:+.2f},{pkt.stick[1]:+.2f})  btn[{pressed}]"
    )


async def run(args: argparse.Namespace) -> int:
    source = make_source(
        args.source, side=args.side or "left", file=args.file, loop=True
    )
    frames = source.frames()

    calib: CalibrationResult | None = None
    if not args.no_calibrate:
        try:
            calib = await _calibrate(frames, Calibrator())
        except Exception as exc:  # noqa: BLE001
            print(f"calibration skipped: {exc}", file=sys.stderr)

    count = 0
    t0 = time.monotonic()
    last_report = t0
    try:
        async for raw, side, _t in frames:
            try:
                pkt = decode_packet(raw, side)
            except PacketTooShort as exc:
                print(f"[short packet] {exc}", file=sys.stderr)
                continue
            if calib:
                calib.apply(pkt)
            count += 1
            now = time.monotonic()
            if count <= 3 or now - last_report >= 0.25:
                rate = count / (now - t0) if now > t0 else 0.0
                print(f"{_fmt(pkt)}   [{rate:5.1f} Hz]", flush=True)
                last_report = now
            if args.max_packets and count >= args.max_packets:
                break
    except KeyboardInterrupt:
        pass
    finally:
        await source.aclose()

    print(f"\nread {count} packets in {time.monotonic() - t0:.1f}s")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Joy-Con 2 terminal IMU reader")
    p.add_argument("--source", default="synthetic", choices=["synthetic", "replay", "joycon2"])
    p.add_argument("--file", help="capture file for --source replay")
    p.add_argument("--side", choices=["left", "right"])
    p.add_argument("--no-calibrate", action="store_true")
    p.add_argument("--max-packets", type=int, default=0, help="stop after N (0 = run forever)")
    args = p.parse_args(argv)
    if args.source == "replay" and not args.file:
        p.error("--source replay requires --file")
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
