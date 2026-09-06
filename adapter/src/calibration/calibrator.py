"""Still-position calibration (GOAL.md §15 step 5: "hold flat for 2 seconds").

No factory calibration block is known for Joy-Con 2 ([FR-PY] uses linear scales
only), so we derive:
  - gyro_bias:   mean gyro while still  -> subtracted from every later sample
  - gravity_ref: mean accel while still -> initial "down" direction for orientation
  - accel_bias:  residual so |accel - bias| == 1 g at rest
  - noise:       per-axis std dev -> dead-zone threshold for the Motion Engine
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..decoder.packet import DecodedPacket, Vec3


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float], mean: float) -> float:
    if len(xs) < 2:
        return 0.0
    return math.sqrt(sum((x - mean) ** 2 for x in xs) / (len(xs) - 1))


@dataclass
class CalibrationResult:
    gyro_bias: Vec3
    accel_bias: Vec3
    gravity_ref: Vec3
    gyro_noise: Vec3          # 1-sigma, deg/s
    gyro_deadzone_dps: float  # 3-sigma of the worst axis
    samples: int

    def apply(self, pkt: DecodedPacket) -> DecodedPacket:
        g, a = pkt.gyro_dps, pkt.accel_g
        pkt.gyro_dps = Vec3(
            g.x - self.gyro_bias.x, g.y - self.gyro_bias.y, g.z - self.gyro_bias.z
        )
        pkt.accel_g = Vec3(
            a.x - self.accel_bias.x, a.y - self.accel_bias.y, a.z - self.accel_bias.z
        )
        return pkt


@dataclass
class Calibrator:
    min_samples: int = 60          # ~1 s at 62 Hz
    target_samples: int = 124      # ~2 s
    _gx: list[float] = field(default_factory=list)
    _gy: list[float] = field(default_factory=list)
    _gz: list[float] = field(default_factory=list)
    _ax: list[float] = field(default_factory=list)
    _ay: list[float] = field(default_factory=list)
    _az: list[float] = field(default_factory=list)

    def feed(self, pkt: DecodedPacket) -> None:
        self._gx.append(pkt.gyro_dps.x)
        self._gy.append(pkt.gyro_dps.y)
        self._gz.append(pkt.gyro_dps.z)
        self._ax.append(pkt.accel_g.x)
        self._ay.append(pkt.accel_g.y)
        self._az.append(pkt.accel_g.z)

    @property
    def progress(self) -> float:
        return min(1.0, len(self._gx) / self.target_samples)

    @property
    def ready(self) -> bool:
        return len(self._gx) >= self.min_samples

    def reset(self) -> None:
        for lst in (self._gx, self._gy, self._gz, self._ax, self._ay, self._az):
            lst.clear()

    def finish(self) -> CalibrationResult:
        if not self.ready:
            raise RuntimeError(f"need >= {self.min_samples} samples, have {len(self._gx)}")

        gbx, gby, gbz = _mean(self._gx), _mean(self._gy), _mean(self._gz)
        abx, aby, abz = _mean(self._ax), _mean(self._ay), _mean(self._az)

        # Scale the mean accel vector so its magnitude is exactly 1 g; the
        # residual (measured - unit_gravity) is the accel bias.
        mag = math.sqrt(abx * abx + aby * aby + abz * abz) or 1.0
        gravity = Vec3(abx / mag, aby / mag, abz / mag)
        accel_bias = Vec3(abx - gravity.x, aby - gravity.y, abz - gravity.z)

        nx = _std(self._gx, gbx)
        ny = _std(self._gy, gby)
        nz = _std(self._gz, gbz)
        deadzone = 3.0 * max(nx, ny, nz)

        return CalibrationResult(
            gyro_bias=Vec3(gbx, gby, gbz),
            accel_bias=accel_bias,
            gravity_ref=gravity,
            gyro_noise=Vec3(nx, ny, nz),
            gyro_deadzone_dps=deadzone,
            samples=len(self._gx),
        )
