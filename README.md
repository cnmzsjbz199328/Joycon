# Joy-Con 2 Motion Web Game Platform

Use a Nintendo Switch 2 **Joy-Con 2** as a motion controller on PC — entirely off-console.

This is **not** a single game. It is a reusable base: the Joy-Con 2 link is
researched once, and gameplay stacks on top.

```
Joy-Con 2 ──BLE──> Adapter (Python) ──WebSocket──> Browser
                   scan / connect / enable IMU        InputProvider
                   decode / calibrate / normalize     Motion Engine  (filter · orientation · gestures)
                                                       Games          (Playground → 3D Sword → Fruit Slash → …)
```

The first full motion demo is **Motion Fruit Slash**. Adding Tennis, Boxing,
Bowling, … later means writing a new consumer of the same `MotionState` /
`GestureEvent` contract — nothing below the game changes.

> **Joy-Con 2 BLE is EXPERIMENTAL.** The adapter is built from community reverse
> engineering (attributed line-by-line in [docs/JOYCON2_PROTOCOL.md](docs/JOYCON2_PROTOCOL.md))
> but has **not** been verified on real hardware in this repo. Everything above the
> adapter is fully working and verified through fallback providers
> (Mock IMU / Keyboard / Gamepad / Joy-Con 1). See [docs/TESTING.md](docs/TESTING.md) §3.

---

## Quick start

### 1. Adapter

```bash
python -m venv .venv
.venv/bin/pip install -r adapter/requirements.txt

# real hardware (EXPERIMENTAL):
.venv/bin/python -m adapter.src.service --source joycon2

# no hardware — synthetic motion, everything downstream works the same:
.venv/bin/python -m adapter.src.service --source synthetic
```

The adapter serves `ws://127.0.0.1:8765`.

### 2. Web

```bash
cd web
npm install
npm run dev        # http://localhost:5173
```

Open the launcher, then:

1. Pick a provider (`Joy-Con 2 (adapter)` for hardware; `Mock IMU` needs nothing).
2. Press **Connect** → status shows **Connected**, controller shows **LEFT/RIGHT**.
3. **Calibration**: hold the Joy-Con flat and still for 2 s → **Calibration Complete**.
4. **Motion Playground** — live gyro/accel scope, motion speed, gesture readout, 3D Sword.
5. **Motion Fruit Slash** — swing to slice fruit, avoid bombs. No game over.

### Start-up UX (GOAL §15)

Run Adapter → open page → `Connect Joy-Con 2` → `Connected` → "hold flat 2 s" →
`Calibration Complete` → Playground → play.

---

## Layout

```
adapter/        Python BLE adapter
  src/
    bluetooth/    scan, connect, reconnect backoff, raw prototype
    protocol/     UUIDs, command frames, IMU-enable bytes, packet offsets, scales
    decoder/      raw notification -> structured (buttons/stick/accel/gyro)
    calibration/  2 s still calibration -> gyro bias, gravity ref, dead zone
    websocket/    normalized JSON broadcast (no downsampling)
    sources.py    frame sources: joycon2 / replay / synthetic
    reader.py     terminal IMU reader          (Phase 2)
    service.py    full pipeline + WebSocket     (Phase 3)
  tests/          pytest

shared/protocol/  data contracts, ONE source of truth
  schema.json     JSON Schema for InputFrame / MotionState / GestureEvent
  frame.py        Python side
  contracts.mjs   browser side

web/
  src/
    input/        InputProvider interface + JoyCon2 / JoyCon1 / Gamepad / Keyboard / MockIMU
    motion/       Motion Engine: filters, quaternion, orientation, gestures
    playground/   IMU scope + 3D Sword
    game/         Motion Fruit Slash
    ui/           connection panel, calibration overlay, styles
  test/           node:test unit tests + Playwright e2e smoke

docs/
  RESEARCH.md            Phase 0 — ecosystem, per-project REUSE/REFERENCE/DO NOT USE
  JOYCON2_PROTOCOL.md    Phase 1 — BLE type, UUIDs, packet layout, sources, J1-J12 checklist
  ARCHITECTURE.md        Phase 1 — 3-approach comparison, ADR log
  MOTION_ENGINE.md       Phase 6 — capabilities, filter selection
  TESTING.md             Phases 0-8 test record + Definition-of-Done status
```

---

## Tests

```bash
# adapter
cd adapter && ../.venv/bin/python -m pytest -q

# web unit
cd web && npm test

# web end-to-end (headless Chromium, Mock IMU)
cd web && ../.venv/bin/pip install playwright && ../.venv/bin/python -m playwright install chromium
~/.claude/skills/webapp-testing/scripts/with_server.py \
  --server "node_modules/.bin/vite --port 5173 --strictPort" --port 5173 \
  -- ../.venv/bin/python test/e2e_smoke.py
```

See [docs/TESTING.md](docs/TESTING.md) for the phase-by-phase record and the
real-hardware acceptance checklist.

---

## Roadmap

Done (Phase 1 of the project): research → protocol → BLE reader → IMU decoder →
WebSocket bridge → Motion Playground → 3D Sword → Gesture Engine → Fruit Slash →
docs.

Next: verify the Joy-Con 2 BLE path on hardware — step-by-step runbook in
[docs/HARDWARE_BRINGUP.md](docs/HARDWARE_BRINGUP.md) — then stack more games on
the unchanged Motion API — Tennis, Table Tennis, Boxing, Racing, Bowling,
Fishing, Rhythm.
