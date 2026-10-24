"""Phase 2 deliverable: terminal IMU raw-data reader.

Prints decoded ax/ay/az, gx/gy/gz, buttons and stick (normalised + raw 12-bit
counts) in real time, plus controller state changes. Runs a 2 s still IMU
calibration per controller first (skippable) so the printed IMU values are
bias-corrected; buttons and sticks print from the first packet regardless.

    python -m adapter.src.reader --source synthetic
    python -m adapter.src.reader --source replay --file tests/fixtures/left_idle.hex
    python -m adapter.src.reader --source joycon2                  # left + right
    python -m adapter.src.reader --source joycon2 --side left
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from .calibration.calibrator import CalibrationResult, Calibrator
from .calibration.stick import StickNormalizer, parse_factory_stick_cal
from .decoder.packet import DecodedPacket, PacketTooShort, decode_packet
from .sources import StateChange, make_source


def _fmt(pkt: DecodedPacket, imu_ok: bool) -> str:
    a, g = pkt.accel_g, pkt.gyro_dps
    pressed = ",".join(k for k, v in pkt.buttons.items() if v) or "-"
    imu = "" if imu_ok else " (IMU uncalibrated)"
    return (
        f"seq={pkt.seq:>9} {pkt.side:<5} "
        f"A[g] {a.x:+6.2f} {a.y:+6.2f} {a.z:+6.2f}   "
        f"G[dps] {g.x:+8.1f} {g.y:+8.1f} {g.z:+8.1f}{imu}   "
        f"stick({pkt.stick[0]:+.2f},{pkt.stick[1]:+.2f}) raw({pkt.stick_raw[0]:4d},{pkt.stick_raw[1]:4d})  "
        f"btn[{pressed}]"
    )


async def run(args: argparse.Namespace) -> int:
    source = make_source(args.source, side=args.side, file=args.file, loop=True)
    calibrators: dict[str, Calibrator] = {}
    calibs: dict[str, CalibrationResult] = {}
    sticks: dict[str, StickNormalizer] = {}

    count = 0
    t0 = time.monotonic()
    last_report: dict[str, float] = {}
    last_buttons: dict[str, dict[str, bool]] = {}
    try:
        async for item in source.frames():
            if isinstance(item, StateChange):
                print(f"[{item.side}] {item.state}" + (f" -- {item.hint}" if item.hint else ""), flush=True)
                cal = parse_factory_stick_cal((item.info.get("flash") or {}).get("factory"))
                if item.state == "connected" and cal is not None:
                    sticks.setdefault(item.side, StickNormalizer()).apply_factory(cal)
                continue
            raw, side, _t = item
            try:
                pkt = decode_packet(raw, side)
            except PacketTooShort as exc:
                print(f"[short packet] {exc}", file=sys.stderr)
                continue
            pkt.stick = sticks.setdefault(side, StickNormalizer()).normalize(*pkt.stick_raw)
            if side in calibs:
                calibs[side].apply(pkt)
            elif not args.no_calibrate:
                cal = calibrators.setdefault(side, Calibrator())
                cal.feed(pkt)
                if cal.progress >= 1.0:
                    res = calibs[side] = cal.finish()
                    print(
                        f"[{side}] IMU calibration complete: {res.samples} samples  "
                        f"gyro_bias=({res.gyro_bias.x:+.2f},{res.gyro_bias.y:+.2f},{res.gyro_bias.z:+.2f}) dps  "
                        f"deadzone={res.gyro_deadzone_dps:.2f} dps", flush=True,
                    )
            count += 1
            now = time.monotonic()
            changed = pkt.buttons != last_buttons.get(side)
            last_buttons[side] = pkt.buttons
            if changed or now - last_report.get(side, 0.0) >= 0.25:
                rate = count / (now - t0) if now > t0 else 0.0
                print(f"{_fmt(pkt, args.no_calibrate or side in calibs)}   [{rate:5.1f} Hz]", flush=True)
                last_report[side] = now
            if args.max_packets and count >= args.max_packets:
                break
    except KeyboardInterrupt:
        pass
    finally:
        await source.aclose()

    print(f"\nread {count} packets in {time.monotonic() - t0:.1f}s")
    for side, s in sticks.items():
        print(f"{side} stick: {s.describe()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Joy-Con 2 terminal IMU reader")
    p.add_argument("--source", default="synthetic", choices=["synthetic", "replay", "joycon2"])
    p.add_argument("--file", help="capture file for --source replay")
    p.add_argument("--side", choices=["left", "right", "both"])
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
