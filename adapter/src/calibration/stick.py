"""Per-controller analog stick normalisation (wire contract: stick in [-1, 1]).

Why this exists: the Joy-Con 2 reports raw, uncalibrated 12-bit sticks ([ND]
hid_reports.md). The physical gate only travels about +-1150..1250 counts and
the rest point is not 2048 (HW 2026-09-06 right unit 900..3300; 2026-09-28 left
unit rest about (-123, +143) counts off 2048). Dividing by 2048 therefore capped
the output near +-0.6 and left a visible offset at rest.

Method:
  centre  - the controller's factory calibration (flash 0x130A8, read at
            connect, see apply_factory). Without it: mean of the first still
            window near 2048 after connect, the nominal 2048 until then.
  extents - one per direction (x-, x+, y-, y+); start at the factory travel (or
            STICK_NOMINAL_EXTENT) and only ever grow to the largest deflection
            seen, so a full push reaches 1.0 on every unit
  output  - clamp to the unit circle, then a radial dead zone, rescaled so the
            value grows from 0 at the dead-zone edge
Axis convention: +x right, +y up (raw counts grow the same way).

Factory block layout (9 bytes = three packed 12-bit x,y pairs, same packing as
the live stick): centre, travel in +x/+y, travel in -x/-y. [ND] lists the
address only; the meaning of the three pairs was established on HW 2026-10-24
(two units): factory centre within ~15 counts of the measured rest point, and
each travel value within ~5 % of the deflection reached in that direction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..decoder.packet import decode_stick_raw
from ..protocol import constants as C


@dataclass(frozen=True)
class FactoryStickCal:
    center: tuple[int, int]
    plus: tuple[int, int]   # travel towards +x, +y
    minus: tuple[int, int]  # travel towards -x, -y


def parse_factory_stick_cal(data: bytes | str | None) -> FactoryStickCal | None:
    """9 bytes (or their hex) from flash 0x130A8 -> calibration, or None if blank/implausible."""
    if isinstance(data, str):
        data = bytes.fromhex(data.replace(" ", ""))
    if not data or len(data) < 9:
        return None
    c, plus, minus = (decode_stick_raw(data[i:i + 3]) for i in (0, 3, 6))
    ok_centre = all(abs(v - C.STICK_CENTER) <= C.STICK_CENTER_BAND * 2 for v in c)
    ok_travel = all(500 <= v <= C.STICK_MAX_EXTENT for v in (*plus, *minus))
    return FactoryStickCal(c, plus, minus) if ok_centre and ok_travel else None


@dataclass
class StickNormalizer:
    deadzone: float = C.STICK_DEADZONE
    initial_extent: float = C.STICK_NOMINAL_EXTENT
    max_extent: float = C.STICK_MAX_EXTENT
    center_band: float = C.STICK_CENTER_BAND
    settle_frames: int = 8
    settle_tolerance: int = 10  # counts, max-min within the window on each axis

    center: tuple[float, float] | None = field(default=None, init=False)
    source: str = field(default="nominal", init=False)  # "factory" | "rest" | "nominal"
    extents: list[float] = field(default_factory=list, init=False)  # x-, x+, y-, y+
    _window: list[tuple[int, int]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.extents = [self.initial_extent] * 4

    def apply_factory(self, cal: FactoryStickCal) -> None:
        """Use the factory centre and travel; learned growth still applies on top."""
        self.center = (float(cal.center[0]), float(cal.center[1]))
        factory = [cal.minus[0], cal.plus[0], cal.minus[1], cal.plus[1]]
        # On a reconnect keep whatever travel was learned beyond the factory values.
        keep = self.extents if self.source == "factory" else factory
        self.extents = [float(max(f, k)) for f, k in zip(factory, keep)]
        self.source = "factory"
        self._window.clear()

    def _track_center(self, rx: int, ry: int) -> None:
        if (abs(rx - C.STICK_CENTER) > self.center_band
                or abs(ry - C.STICK_CENTER) > self.center_band):
            self._window.clear()
            return
        self._window.append((rx, ry))
        if len(self._window) > self.settle_frames:
            self._window.pop(0)
        if len(self._window) < self.settle_frames:
            return
        xs = [p[0] for p in self._window]
        ys = [p[1] for p in self._window]
        if (max(xs) - min(xs) <= self.settle_tolerance
                and max(ys) - min(ys) <= self.settle_tolerance):
            self.center = (sum(xs) / len(xs), sum(ys) / len(ys))
            self.source = "rest"
            self._window.clear()

    def _axis(self, d: float, base: int) -> float:
        i = base + (1 if d > 0 else 0)
        mag = abs(d)
        # Only learn extents against a real centre, or a +-150 count centre
        # error would inflate one side permanently.
        if self.center is not None and mag > self.extents[i]:
            self.extents[i] = min(mag, self.max_extent)
        return math.copysign(min(mag / self.extents[i], 1.0), d)

    def normalize(self, rx: int, ry: int) -> tuple[float, float]:
        if self.center is None:
            self._track_center(rx, ry)
        cx, cy = self.center or (C.STICK_CENTER, C.STICK_CENTER)
        x = self._axis(rx - cx, 0)
        y = self._axis(ry - cy, 2)
        r = math.hypot(x, y)
        if r > 1.0:
            x, y, r = x / r, y / r, 1.0
        if r <= self.deadzone:
            return 0.0, 0.0
        k = (r - self.deadzone) / (1.0 - self.deadzone) / r
        return x * k, y * k

    def describe(self) -> str:
        c = "nominal" if self.center is None else f"({self.center[0]:.0f},{self.center[1]:.0f}) from {self.source}"
        e = ",".join(f"{v:.0f}" for v in self.extents)
        return f"centre={c} extents(x-,x+,y-,y+)={e} deadzone={self.deadzone:.2f}"
