"""Session recorder for `service.py --record FILE.jsonl`.

One JSON object per line, all `t` values on the adapter's time.monotonic()
clock, so packets, controller state changes and the action marks a test page
sends ({"type": "mark"} messages, see shared/protocol/README.md) line up:

  {"kind": "meta",   "t": ..., "wall": "...", "adapter": "...", "source": "...", "argv": [...]}
  {"kind": "state",  "t": ..., "side": "left", "state": "connected", "hint": null, "info": {...}}
  {"kind": "packet", "t": ..., "side": "left", "hex": "..."}
  {"kind": "mark",   "t": ..., "data": {...}}

`--source replay --file FILE.jsonl` plays it back through the full pipeline.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class CaptureWriter:
    def __init__(self, path: str | Path, *, adapter: str, source: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("a", buffering=1)  # line-buffered: survives Ctrl-C
        self._write({
            "kind": "meta", "t": time.monotonic(),
            "wall": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "adapter": adapter, "source": source, "argv": sys.argv[1:],
        })
        self.packets = 0

    def _write(self, rec: dict[str, Any]) -> None:
        self._f.write(json.dumps(rec, separators=(",", ":")) + "\n")

    def packet(self, t: float, side: str, raw: bytes) -> None:
        self.packets += 1
        self._write({"kind": "packet", "t": t, "side": side, "hex": raw.hex()})

    def state(self, side: str, state: str, hint: str | None, info: dict[str, Any]) -> None:
        self._write({"kind": "state", "t": time.monotonic(), "side": side, "state": state,
                     "hint": hint, "info": info})

    def mark(self, data: dict[str, Any]) -> None:
        self._write({"kind": "mark", "t": time.monotonic(), "data": data})

    def close(self) -> None:
        self._f.close()
