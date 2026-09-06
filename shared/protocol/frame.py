"""Python side of the data contracts (mirrors schema.json / contracts.mjs).

Kept dependency-free so the adapter can import it directly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

PROTOCOL_VERSION = 1
WS_DEFAULT_HOST = "127.0.0.1"
WS_DEFAULT_PORT = 8765

GESTURES = (
    "SLASH_LEFT",
    "SLASH_RIGHT",
    "SLASH_UP",
    "SLASH_DOWN",
    "THRUST",
    "SHAKE",
    "ROTATE",
)

_DEG2RAD = math.pi / 180.0


@dataclass
class InputFrame:
    timestamp: float
    seq: int
    controller: str  # "left" | "right"
    buttons: dict[str, bool]
    stick: tuple[float, float]
    accel_g: tuple[float, float, float]
    gyro_dps: tuple[float, float, float]
    battery_v: float | None = None
    battery_ma: float | None = None
    temperature_c: float | None = None

    def to_message(self) -> dict[str, Any]:
        gx, gy, gz = self.gyro_dps
        ax, ay, az = self.accel_g
        return {
            "timestamp": self.timestamp,
            "seq": self.seq,
            "controller": self.controller,
            "buttons": self.buttons,
            "stick": {"x": self.stick[0], "y": self.stick[1]},
            "accelerometer": {"x": ax, "y": ay, "z": az},
            # contract: gyroscope is rad/s on the wire (ADR-4)
            "gyroscope": {"x": gx * _DEG2RAD, "y": gy * _DEG2RAD, "z": gz * _DEG2RAD},
            "battery": (
                None
                if self.battery_v is None and self.battery_ma is None
                else {"voltage": self.battery_v, "current": self.battery_ma}
            ),
            "temperature": self.temperature_c,
        }


def envelope(msg_type: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"v": PROTOCOL_VERSION, "type": msg_type, "data": data}


@dataclass
class HelloData:
    adapter: str
    source: str
    rate_hz: float

    def as_dict(self) -> dict[str, Any]:
        return {"adapter": self.adapter, "source": self.source, "rateHz": self.rate_hz}


@dataclass
class StatusData:
    connection: str
    calibrated: bool
    controller: str = "unknown"
    hint: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "connection": self.connection,
            "controller": self.controller,
            "calibrated": self.calibrated,
            "hint": self.hint,
        }
