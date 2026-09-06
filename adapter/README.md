# adapter/ — Joy-Con 2 BLE Adapter (Python)

Pipeline: `BLE scan -> connect -> enable IMU -> receive notifications -> decode
-> calibrate -> normalize -> WebSocket output`.

Language rationale: see [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §3.

> **STATUS: the BLE path is EXPERIMENTAL.** It is implemented from community
> reverse-engineering (see [../docs/JOYCON2_PROTOCOL.md](../docs/JOYCON2_PROTOCOL.md))
> but has not been verified on real hardware in this environment. Decoder,
> calibration, and the WebSocket bridge are covered by unit tests and a replay
> harness that do not need a controller.

## Setup

```bash
python -m venv ../.venv
../.venv/bin/pip install -r requirements.txt
```

## Run

```bash
# Phase 1 -- prototype: scan / connect / dump raw notifications + GATT tree
python -m adapter.src.bluetooth.prototype --scan
python -m adapter.src.bluetooth.prototype --connect <ADDR> --seconds 15

# Phase 2 -- decoded IMU reader in the terminal
python -m adapter.src.reader --source joycon2          # real hardware
python -m adapter.src.reader --source replay --file captures/left_idle.hex
python -m adapter.src.reader --source synthetic        # no hardware, sine motion

# Phase 3 -- full adapter with WebSocket output on ws://127.0.0.1:8765
python -m adapter.src.service --source joycon2
python -m adapter.src.service --source synthetic       # fallback for web dev
```

## Tests

```bash
../.venv/bin/python -m pytest -q
```

## Layout

| Path | Responsibility |
| --- | --- |
| `src/protocol/` | UUIDs, command frames, IMU-enable bytes, packet offsets, scales |
| `src/bluetooth/` | scan, connect, reconnect backoff, raw prototype |
| `src/decoder/` | packet -> structured (buttons/stick/accel/gyro/battery/temp) |
| `src/calibration/` | 2 s still calibration: gyro bias, gravity reference, dead zone |
| `src/websocket/` | normalized JSON broadcast (no downsampling) |
| `src/reader.py` | terminal IMU reader (Phase 2 deliverable) |
| `src/service.py` | decode + calibrate + WebSocket (Phase 3 deliverable) |
| `src/sources.py` | frame sources: `joycon2` / `replay` / `synthetic` |
