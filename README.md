# Joy-Con 2 Motion Web Game Platform

Use a Nintendo Switch 2 **Joy-Con 2** as a motion controller on PC — entirely off-console.

**Integrating buttons and sticks into another project? Start with the
[Integration guide](docs/INTEGRATION.md).** It covers adapter setup, client files,
working examples, protocol v2, disconnect handling and the verified platform scope.
The input service works independently of the motion demos.

中文接入说明：其他项目请先阅读 [Integration guide](docs/INTEGRATION.md)，通过现有 WebSocket 服务接入。

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

> **Status (2026-10-24)** — real **left + right Joy-Con 2** on a Mac mini (macOS / CoreBluetooth),
> both connected to one adapter at the same time:
> - **Buttons + sticks — verified, stable interface.** All 11 left and 12 right buttons (incl. Home,
>   Capture, C; Sync is pairing-only), both sticks calibrated from the controller's own factory data
>   (exactly 0 at rest, full deflection r ≥ 0.99 in all 8 directions incl. diagonals), combos and long holds,
>   left/right isolation, nothing stuck on disconnect, auto-reconnect after a long Sync press.
>   Usable from any project via the WebSocket contract — see **[Using the buttons and sticks](#using-the-buttons-and-sticks-from-another-project)**.
> - **Motion — link verified, tuning paused.** Accel/gyro decode verified on both units; gesture
>   thresholds tuned on hardware for left/right slashes; UP/DOWN tuning and the `game.html` hardware
>   run are not done. Latency percentiles and high-rate gyro full-scale are unmeasured.
> - ~33 Hz per controller on macOS (BLE connection-interval limit, not the controller).
>
> Log of every hardware round: [docs/HARDWARE_BRINGUP.md](docs/HARDWARE_BRINGUP.md) §5 ·
> per-item checklist: [docs/JOYCON2_PROTOCOL.md](docs/JOYCON2_PROTOCOL.md) §J.
> Everything above the adapter also runs on fallback providers (Mock IMU / Keyboard / Gamepad /
> Joy-Con 1), see [docs/TESTING.md](docs/TESTING.md).

---

## Quick start

### 1. Adapter

```bash
python -m venv .venv
.venv/bin/pip install -r adapter/requirements.txt

# real hardware: finds a left AND a right Joy-Con 2 — hold Sync on each until the LEDs run
.venv/bin/python -m adapter.src.service --source joycon2            # --side left|right for one
.venv/bin/python -m adapter.src.service --source joycon2 --record adapter/captures/session.jsonl

# no hardware — synthetic controllers (motion + a button walk + circling sticks):
.venv/bin/python -m adapter.src.service --source synthetic --side both
# replay a recording through the full pipeline:
.venv/bin/python -m adapter.src.service --source replay --file adapter/tests/fixtures/hw_2026-10-24_input.jsonl
```

The adapter serves `ws://127.0.0.1:8765`. Buttons and sticks are live as soon as a controller
connects; the IMU still-calibration (set the controller down ~2 s) only matters for motion.

### 2. Web

```bash
cd web
npm install
npm run dev        # http://localhost:5173
```

Open the launcher. **Input Test** (`input.html`) shows every button and both sticks of both
controllers with a press/release log. For motion:

1. Pick a provider (`Joy-Con 2 (adapter)` for hardware; `Mock IMU` needs nothing).
2. Press **Connect** → status shows **Connected**, controller shows **LEFT/RIGHT**.
3. **Calibration**: hold the Joy-Con flat and still for 2 s → **Calibration Complete**.
4. **Motion Playground** — live gyro/accel scope, motion speed, gesture readout, 3D Sword.
5. **Motion Fruit Slash** — swing to slice fruit, avoid bombs. No game over.

### Start-up UX (GOAL §15)

Run Adapter → open page → `Connect Joy-Con 2` → `Connected` → "hold flat 2 s" →
`Calibration Complete` → Playground → play.

---

## Using the buttons and sticks from another project

Follow the **[Integration guide](docs/INTEGRATION.md)** for setup and cross-project
file paths. Vendor `input-client.mjs` together with its sibling `contracts.mjs`,
or use them from a local checkout; no published client package is required.
The following import assumes this repository's directory layout.

Connect to `ws://127.0.0.1:8765` and read per-controller state frames — no BLE, no IMU:

```js
import { connectJoyCon2 } from "./shared/protocol/input-client.mjs";   // browser or Node >= 22
const jc = connectJoyCon2();                                           // or { controllers: ["right"] }
jc.on("press",   ({ controller, button }) => console.log(controller, button, "down"));
jc.on("release", ({ controller, button, reason }) => console.log(controller, button, "up", reason));
jc.device("left").stick;   // { x, y } in [-1, 1], +x right, +y up, 0,0 at rest
```

Button names — left: `up down left right l zl sl sr minus capture stick`; right:
`a b x y r zr sl sr plus home c stick`. A controller that drops, a stale stream or a closed socket
releases everything it held. Contract (protocol v2): [shared/protocol/README.md](shared/protocol/README.md);
runnable Node and Python examples: [examples/](examples/README.md).

---

## Layout

```
adapter/        Python BLE adapter
  src/
    bluetooth/    scan, connect, reconnect backoff, raw prototype
    protocol/     UUIDs, command frames, IMU-enable bytes, packet offsets, scales
    decoder/      raw notification -> structured (buttons/stick/accel/gyro)
    calibration/  IMU still calibration; stick normalisation from factory calibration
    websocket/    normalized JSON broadcast (no downsampling)
    sources.py    frame sources: joycon2 / replay / synthetic
    reader.py     terminal IMU reader          (Phase 2)
    service.py    full pipeline + WebSocket     (Phase 3)
  tests/          pytest

shared/protocol/  data contracts, ONE source of truth (protocol v2)
  schema.json     JSON Schema for InputFrame / Status / MotionState / GestureEvent
  frame.py        Python side
  contracts.mjs   browser side
  input-client.mjs  reference client: buttons/sticks, press/release, no stuck keys

examples/         minimal Node + Python consumers of the input interface

web/
  src/
    input/        InputProvider interface + JoyCon2 / JoyCon1 / Gamepad / Keyboard / MockIMU
    motion/       Motion Engine: filters, quaternion, orientation, gestures
    playground/   IMU scope + 3D Sword
    game/         Motion Fruit Slash
    input-test/   input.html: all buttons + sticks, event log, guided acceptance run
    ui/           connection panel, calibration overlay, styles
  test/           node:test unit tests + Playwright e2e smoke

docs/
  RESEARCH.md            Phase 0 — ecosystem, per-project REUSE/REFERENCE/DO NOT USE
  CALIBRATION_RESEARCH.md  Calibration deep dive — official flow vs. in-game "face the
                           screen" yaw anchor vs. SPI factory calibration (open question)
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

# web end-to-end (headless Chromium: Mock IMU pages + input page against a synthetic
# adapter and against the real hardware recording)
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

Done since: Joy-Con 2 BLE verified on hardware (both units), full button + stick
input interface (protocol v2).

Next: motion UP/DOWN tuning and the `game.html` hardware run (paused), latency
percentiles — runbook in [docs/HARDWARE_BRINGUP.md](docs/HARDWARE_BRINGUP.md) — then
stack more games on the unchanged Motion API — Tennis, Table Tennis, Boxing,
Racing, Bowling, Fishing, Rhythm.
