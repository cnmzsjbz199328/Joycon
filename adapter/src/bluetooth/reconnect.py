"""Reconnect backoff for the Joy-Con 2 controller-level cooldown.

Community reports ([FR-PY] README, [MIS]): repeated connect attempts in a short
window make the controller refuse connections for several minutes. We use
exponential backoff with jitter and, after a run of failures, hold at the ceiling
and surface a "wait 2-3 minutes" hint to the user.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..protocol.constants import RECONNECT_COOLDOWN_HINT_S


@dataclass
class ReconnectPolicy:
    base_delay_s: float = 1.0
    ceiling_s: float = 60.0
    jitter_frac: float = 0.2
    cooldown_after_failures: int = 4

    _consecutive_failures: int = field(default=0, init=False)

    def reset(self) -> None:
        """Call after a successful connect."""
        self._consecutive_failures = 0

    @property
    def in_cooldown(self) -> bool:
        return self._consecutive_failures >= self.cooldown_after_failures

    def next_delay(self) -> float:
        """Record one failure and return how long to wait before retrying."""
        n = self._consecutive_failures  # failures seen before this one
        self._consecutive_failures += 1
        if n >= self.cooldown_after_failures:
            delay = self.ceiling_s
        else:
            delay = min(self.ceiling_s, self.base_delay_s * (2 ** n))
        jitter = delay * self.jitter_frac
        return max(0.1, delay + random.uniform(-jitter, jitter))

    def status_hint(self) -> str | None:
        if self.in_cooldown:
            return (
                f"Controller appears to be in its reconnect cooldown. "
                f"Put it down and wait ~{RECONNECT_COOLDOWN_HINT_S // 60}-3 minutes, "
                f"then press Sync again."
            )
        return None
