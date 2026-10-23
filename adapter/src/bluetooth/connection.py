"""A single Joy-Con 2 BLE connection: connect, enable input + IMU, stream
notifications, and reconnect with backoff.

State changes are reported through `on_state_change(state, hint, info)` using
the shared/protocol connection states ("connecting", "connected",
"disconnected", "reconnecting", "cooldown", "stopped"). "connected" is only
reported once notifications are subscribed, i.e. input is about to flow.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakDeviceNotFoundError

from ..protocol import commands
from ..protocol.constants import (
    COMMAND_RESPONSE_UUID,
    ENABLE_IMU_GAP_S,
    FLASH_FACTORY_STICK_CAL,
    FLASH_USER_STICK_CAL,
    INPUT_REPORT_UUID,
    SIDE_CHAR_LEFT,
    SIDE_CHAR_RIGHT,
    WRITE_COMMAND_UUID,
)
from .reconnect import ReconnectPolicy

log = logging.getLogger("adapter.connection")

NotificationHandler = Callable[[bytes], Awaitable[None] | None]
StateHandler = Callable[[str, "str | None", "dict[str, Any]"], None]

# Not advertising -> keep looking, but this is not a refused connection, so it
# must not walk the cooldown backoff (that would sleep through a Sync press).
NOT_FOUND_RETRY_S = 1.0


def side_from_services(client: BleakClient) -> str:
    uuids = {ch.uuid.lower() for s in client.services for ch in s.characteristics}
    if SIDE_CHAR_LEFT in uuids and SIDE_CHAR_RIGHT not in uuids:
        return "left"
    if SIDE_CHAR_RIGHT in uuids and SIDE_CHAR_LEFT not in uuids:
        return "right"
    return "unknown"


class JoyConConnection:
    def __init__(
        self,
        address: str,
        *,
        device: BLEDevice | None = None,
        side: str = "unknown",
        player_number: int = 1,
        on_notification: NotificationHandler,
        on_state_change: StateHandler | None = None,
        policy: ReconnectPolicy | None = None,
        read_stick_calibration: bool = True,
    ) -> None:
        self.address = address
        self.side = side
        self.player_number = player_number
        self._device = device  # first connect reuses the scan result (no re-scan)
        self._on_notification = on_notification
        self._on_state_change = on_state_change or (lambda _s, _h, _i: None)
        self._policy = policy or ReconnectPolicy()
        self._read_stick_cal = read_stick_calibration
        self._client: BleakClient | None = None
        self._stop = asyncio.Event()
        self._connected = asyncio.Event()
        self.flash: dict[str, str] = {}  # diagnostic: hex of the stick-calibration reads

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def _state(self, state: str, hint: str | None = None, **info: Any) -> None:
        self._on_state_change(state, hint, {"address": self.address, **info})

    async def _handle(self, _sender: object, data: bytearray) -> None:
        res = self._on_notification(bytes(data))
        if asyncio.iscoroutine(res):
            await res

    async def _read_flash(self, client: BleakClient, address: int, length: int) -> bytes | None:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[bytes] = loop.create_future()

        def on_resp(_s: object, data: bytearray) -> None:
            payload = commands.parse_flash_read(bytes(data), address)
            if payload is not None and not fut.done():
                fut.set_result(payload)

        await client.start_notify(COMMAND_RESPONSE_UUID, on_resp)
        try:
            await client.write_gatt_char(WRITE_COMMAND_UUID, commands.read_flash(address, length))
            return await asyncio.wait_for(fut, timeout=1.5)
        except asyncio.TimeoutError:
            return None
        finally:
            try:
                await client.stop_notify(COMMAND_RESPONSE_UUID)
            except Exception:  # noqa: BLE001
                pass

    async def _read_stick_calibration(self, client: BleakClient) -> None:
        """Diagnostic only: record the factory/user stick calibration blocks the
        console reads at connect. Nothing depends on the result yet."""
        for key, addr, n in (("factory", FLASH_FACTORY_STICK_CAL, 9), ("user", FLASH_USER_STICK_CAL, 11)):
            try:
                data = await self._read_flash(client, addr, n)
            except Exception as exc:  # noqa: BLE001
                log.info("stick calibration read %s failed: %s", key, exc)
                continue
            if data is not None:
                self.flash[key] = data.hex(" ")
                log.info("%s stick calibration @0x%X (%s): %s", key, addr, self.side, self.flash[key])

    async def _initialise(self, client: BleakClient) -> None:
        """Re-run on every (re)connect: side check, LEDs, input+IMU enable, subscribe."""
        gatt_side = side_from_services(client)
        if self.side == "unknown":
            self.side = gatt_side
        elif gatt_side not in ("unknown", self.side):
            log.warning("%s: advertised side %s but GATT says %s -- using GATT", self.address, self.side, gatt_side)
            self.side = gatt_side

        try:
            await client.write_gatt_char(WRITE_COMMAND_UUID, commands.set_player_leds(self.player_number))
        except Exception as exc:  # noqa: BLE001 - LED is best effort
            log.warning("set LEDs failed: %s", exc)

        # Feature mask 0x2F = buttons | sticks | IMU | mouse | rumble ([ND] commands.md 0x0C).
        cmd1, cmd2 = commands.enable_imu_sequence()
        await client.write_gatt_char(WRITE_COMMAND_UUID, cmd1)
        await asyncio.sleep(ENABLE_IMU_GAP_S)
        await client.write_gatt_char(WRITE_COMMAND_UUID, cmd2)

        await client.start_notify(INPUT_REPORT_UUID, self._handle)

        if self._read_stick_cal and not self.flash:
            await self._read_stick_calibration(client)

    async def run(self) -> None:
        """Connect and keep the link alive until stop() is called."""
        while not self._stop.is_set():
            not_found = False
            try:
                self._state("connecting")
                client = BleakClient(self._device or self.address, disconnected_callback=self._on_disconnect)
                self._device = None
                await client.connect()
                self._client = client
                await self._initialise(client)
                self._policy.reset()
                self._connected.set()
                self._state("connected", gatt_side=self.side, flash=dict(self.flash))
                log.info("connected %s (%s)", self.address, self.side)

                # Idle until disconnect or stop.
                while client.is_connected and not self._stop.is_set():
                    await asyncio.sleep(0.5)

            except BleakDeviceNotFoundError:
                not_found = True
            except Exception as exc:  # noqa: BLE001
                log.warning("connection error on %s: %s", self.address, exc)
            finally:
                self._connected.clear()
                await self._safe_disconnect()

            if self._stop.is_set():
                break

            if not_found:
                delay = NOT_FOUND_RETRY_S
                hint = f"{self.side} Joy-Con 2 not advertising -- press its Sync button to reconnect"
                self._state("reconnecting", hint)
            else:
                delay = self._policy.next_delay()
                hint = self._policy.status_hint()
                self._state("cooldown" if self._policy.in_cooldown else "reconnecting", hint)
                if hint:
                    log.warning(hint)
                log.info("retrying %s in %.1fs", self.address, delay)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass

        self._state("stopped")

    def _on_disconnect(self, _client: BleakClient) -> None:
        log.info("disconnected %s", self.address)
        self._connected.clear()
        self._state("disconnected")

    async def _safe_disconnect(self) -> None:
        if self._client is not None:
            try:
                if self._client.is_connected:
                    await self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    async def wait_connected(self, timeout: float | None = None) -> bool:
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def stop(self) -> None:
        self._stop.set()
