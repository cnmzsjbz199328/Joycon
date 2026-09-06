"""A single Joy-Con 2 BLE connection: connect, enable IMU, stream notifications,
and reconnect with backoff.

STATUS: EXPERIMENTAL -- BLE path not verified on hardware in this environment.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from bleak import BleakClient

from ..protocol import commands
from ..protocol.constants import (
    ENABLE_IMU_GAP_S,
    INPUT_REPORT_UUID,
    WRITE_COMMAND_UUID,
)
from .reconnect import ReconnectPolicy

log = logging.getLogger("adapter.connection")

NotificationHandler = Callable[[bytes], Awaitable[None] | None]


class JoyConConnection:
    def __init__(
        self,
        address: str,
        *,
        side: str = "unknown",
        player_number: int = 1,
        on_notification: NotificationHandler,
        on_state_change: Callable[[str], None] | None = None,
        policy: ReconnectPolicy | None = None,
    ) -> None:
        self.address = address
        self.side = side
        self.player_number = player_number
        self._on_notification = on_notification
        self._on_state_change = on_state_change or (lambda _s: None)
        self._policy = policy or ReconnectPolicy()
        self._client: BleakClient | None = None
        self._stop = asyncio.Event()
        self._connected = asyncio.Event()

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def _handle(self, _sender: object, data: bytearray) -> None:
        res = self._on_notification(bytes(data))
        if asyncio.iscoroutine(res):
            await res

    async def _initialise(self, client: BleakClient) -> None:
        """Re-run on every (re)connect: LEDs + IMU enable + subscribe."""
        try:
            await client.write_gatt_char(WRITE_COMMAND_UUID, commands.set_player_leds(self.player_number))
        except Exception as exc:  # noqa: BLE001 - LED is best effort
            log.warning("set LEDs failed: %s", exc)

        cmd1, cmd2 = commands.enable_imu_sequence()
        await client.write_gatt_char(WRITE_COMMAND_UUID, cmd1)
        await asyncio.sleep(ENABLE_IMU_GAP_S)
        await client.write_gatt_char(WRITE_COMMAND_UUID, cmd2)

        await client.start_notify(INPUT_REPORT_UUID, self._handle)

    async def run(self) -> None:
        """Connect and keep the link alive until stop() is called."""
        while not self._stop.is_set():
            try:
                self._on_state_change("connecting")
                client = BleakClient(self.address, disconnected_callback=self._on_disconnect)
                await client.connect()
                self._client = client
                await self._initialise(client)
                self._policy.reset()
                self._connected.set()
                self._on_state_change("connected")
                log.info("connected %s (%s)", self.address, self.side)

                # Idle until disconnect or stop.
                while client.is_connected and not self._stop.is_set():
                    await asyncio.sleep(1.0)

            except Exception as exc:  # noqa: BLE001
                log.warning("connection error on %s: %s", self.address, exc)
            finally:
                self._connected.clear()
                await self._safe_disconnect()

            if self._stop.is_set():
                break

            delay = self._policy.next_delay()
            hint = self._policy.status_hint()
            self._on_state_change("cooldown" if self._policy.in_cooldown else "reconnecting")
            if hint:
                log.warning(hint)
            log.info("retrying %s in %.1fs", self.address, delay)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass

        self._on_state_change("stopped")

    def _on_disconnect(self, _client: BleakClient) -> None:
        log.info("disconnected %s", self.address)
        self._connected.clear()
        self._on_state_change("disconnected")

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
