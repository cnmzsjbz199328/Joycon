"""BLE scan + side detection for Joy-Con 2.

Identifies Switch 2 controllers by manufacturer id 1363 and the 01 00 03 7E
manufacturer-data prefix ([FR-PY] main.py).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..protocol.constants import MANUFACTURER_ID, MANUFACTURER_PREFIX


class BluetoothUnavailable(RuntimeError):
    """No usable BLE adapter / permission (common in CI and headless envs)."""


@dataclass
class FoundController:
    device: BLEDevice
    name: str
    address: str
    side: str  # "left" | "right" | "unknown"


def _detect_side(name: str | None) -> str:
    n = (name or "").lower()
    if "(l)" in n or "left" in n:
        return "left"
    if "(r)" in n or "right" in n:
        return "right"
    return "unknown"


def _is_joycon2(adv: AdvertisementData) -> bool:
    data = adv.manufacturer_data.get(MANUFACTURER_ID)
    return bool(data and data.startswith(MANUFACTURER_PREFIX))


async def scan_for_controllers(
    timeout: float = 10.0,
    want: int = 1,
    exclude_addresses: set[str] | None = None,
) -> list[FoundController]:
    """Scan until `want` distinct controllers are seen or `timeout` elapses.

    Raises BluetoothUnavailable if the BLE stack cannot be started (no radio /
    no permission) -- callers fall back to a non-Joy-Con-2 provider.
    """
    exclude = {a.lower() for a in (exclude_addresses or set())}
    found: dict[str, FoundController] = {}
    done = asyncio.Event()

    def callback(device: BLEDevice, adv: AdvertisementData) -> None:
        if device.address.lower() in exclude or device.address in found:
            return
        if not _is_joycon2(adv):
            return
        name = device.name or adv.local_name or "Joy-Con 2"
        found[device.address] = FoundController(
            device=device, name=name, address=device.address, side=_detect_side(name)
        )
        if len(found) >= want:
            done.set()

    scanner = BleakScanner(callback)
    try:
        # On macOS, start() blocks indefinitely without Bluetooth permission or a
        # powered adapter -- guard it with the same timeout.
        await asyncio.wait_for(scanner.start(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise BluetoothUnavailable("BLE scan start timed out") from exc
    except Exception as exc:  # noqa: BLE001 - bleak raises backend-specific errors
        raise BluetoothUnavailable(str(exc)) from exc

    try:
        await asyncio.wait_for(done.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        try:
            await asyncio.wait_for(scanner.stop(), timeout=5.0)
        except Exception:  # noqa: BLE001
            pass
    return list(found.values())
