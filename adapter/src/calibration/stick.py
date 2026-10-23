"""Per-controller analog stick normalisation (wire contract: stick in [-1, 1]).

Why this exists: the Joy-Con 2 reports raw, uncalibrated 12-bit sticks ([ND]
hid_reports.md). The physical gate only travels about +-1150..1250 counts and
the rest point is not 2048 (HW 2026-09-06 right unit 900..3300; 2026-09-28 left
unit rest about (-123, +143) counts off 2048). Dividing by 2048 therefore capped
the output near +-0.6 and left a visible offset at rest.

Method (needs no factory data, no user action):
  centre  - mean of the first still window near 2048 after connect; until then
            the nominal 2048 is used
  extents - one per direction (x-, x+, y-, y+); start at STICK_NOMINAL_EXTENT and
            only ever grow to the largest deflection seen, so a full push
            reaches 1.0 on every unit and diagonals are not under-reported
  output  - clamp to the unit circle, then a radial dead zone, rescaled so the
            value grows from 0 at the dead-zone edge
Axis convention: +x right, +y up (raw counts grow the same way).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..protocol import constants as C


@dataclass
class StickNormalizer:
    deadzone: float = C.STICK_DEADZONE
    initial_extent: float = C.STICK_NOMINAL_EXTENT
    max_extent: float = C.STICK_MAX_EXTENT
    center_band: float = C.STICK_CENTER_BAND
    settle_frames: int = 8
    settle_tolerance: int = 10  # counts, max-min within the window on each axis

    center: tuple[float, float] | None = field(default=None, init=False)
    extents: list[float] = field(default_factory=list, init=False)  # x-, x+, y-, y+
    _window: list[tuple[int, int]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.extents = [self.initial_extent] * 4

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
        c = "nominal" if self.center is None else f"({self.center[0]:.0f},{self.center[1]:.0f})"
        e = ",".join(f"{v:.0f}" for v in self.extents)
        return f"centre={c} extents(x-,x+,y-,y+)={e} deadzone={self.deadzone:.2f}"
