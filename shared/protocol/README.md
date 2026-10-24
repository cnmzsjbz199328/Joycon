# shared/protocol/ — data contracts

The single source of truth for every message that crosses a layer boundary.
Both the Python adapter and the browser import from here.

| Contract | Producer → Consumer | File |
| --- | --- | --- |
| **InputFrame** (§8.1) | Adapter → clients (over WebSocket) | `schema.json#/definitions/InputFrame`, `frame.py`, `contracts.mjs` |
| **Status** | Adapter → clients, one per controller | `schema.json#/definitions/Status`, `frame.py`, `contracts.mjs` |
| **MotionState** (§7.2 / §8.2) | Motion Engine → Game | `schema.json#/definitions/MotionState`, `contracts.mjs` |
| **GestureEvent** (§8.3) | Motion Engine → Game | `schema.json#/definitions/GestureEvent`, `contracts.mjs` |
| Reference client | buttons/sticks for any JS project | `input-client.mjs` |

Version: `PROTOCOL_VERSION = 2`, sent as `v` in every WebSocket envelope; bumped
on any breaking change. `adapter/tests/test_contracts.py` fails if Python, JS and
the schema disagree on the version, the button names or the connection states.

**Using Joy-Con 2 buttons/sticks from another project** needs only §1, §2, §5,
§6 — no BLE, no IMU. Runnable examples: [`examples/`](../../examples/README.md).

---

## 0. Changes in v2 (2026-10-24)

v1 assumed one controller per adapter and conflated "WebSocket open" with
"controller connected". v2 is incompatible, hence the bump:

- One adapter streams a **left and a right** Joy-Con 2 on the same socket; every
  frame and every status names its `controller`.
- `status` is **per controller**, and `connection: "connected"` now means *that
  controller is online and its frames are flowing* (v1 sent "connected" before
  the BLE link was even up). The last status of each controller is replayed to
  a client when it connects.
- Frames start with the first packet. `imuReady` tells motion consumers when the
  IMU calibration has been applied; buttons and sticks never wait for it.
- `buttons` always carries the **full set** for that side (adds `home`,
  `capture`, `c`).
- `stick` is normalised per controller (centre + full travel, dead zone); the
  untouched 12-bit values are in the new `stickRaw`.
- New client → adapter message `mark` (diagnostic annotations for captures).

## 1. Transport envelope (WebSocket)

`ws://127.0.0.1:8765`. Server = adapter, clients = any number of pages /
programs. One JSON object per text message:

```json
{ "v": 2, "type": "hello",  "data": { "adapter": "0.2.0", "source": "joycon2", "rateHz": 62 } }
{ "v": 2, "type": "status", "data": { "controller": "right", "connection": "connected", "calibrated": false, "hint": null, "address": "59F5…" } }
{ "v": 2, "type": "frame",  "data": { /* InputFrame */ } }
```

- `hello` once on connect, then the last `status` of every controller.
- `frame` messages are sent **at the device rate, with no downsampling and no
  coalescing** (GOAL.md §9). One BLE notification → one `frame` message. On
  macOS that is ~33 Hz per controller (BLE connection-interval limit).
- Ordering: a controller's `status` and `frame` messages are delivered in the
  order they happened. No frame of a controller follows its own
  `"disconnected"` status.
- Clients → adapter: only `{"v": 2, "type": "mark", "data": {...}}` is accepted.
  It is written into the `--record` capture (if any) and otherwise ignored.

## 2. Status (one per controller)

| field | meaning |
| --- | --- |
| `controller` | `"left"` / `"right"` |
| `connection` | `connected` = online, frames flowing. `connecting` = looking for it (press Sync). `disconnected` = link just dropped. `reconnecting` / `cooldown` = adapter retrying (cooldown = the controller refused rapid reconnects; wait 2–3 min). `stopped` = adapter shutting down. |
| `calibrated` | the adapter's IMU still-calibration for this controller has completed (motion only) |
| `hint` | human-readable next step, or null |
| `address` | BLE address of the unit (on macOS a per-host UUID), diagnostic |

Lifecycle: `connecting` → `connected` → (link lost) `disconnected` →
`connecting`/`reconnecting` → `connected` … The adapter keeps retrying by
address on its own. Verified on hardware (2026-10-24): a dropped Joy-Con 2
(e.g. after a short Sync press while connected) does **not** advertise to us
again by itself — **hold its Sync button until the player LEDs run**, and the
adapter reconnects within ~1 s (the status `hint` says so). On reconnect the
adapter re-enables input + IMU; the controller keeps its IMU calibration and
stick calibration, so `calibrated` stays true and input is usable immediately.
A link loss reaches clients as `disconnected` ~0.7 s after the last frame.

## 3. InputFrame (adapter → clients)

```json
{
  "timestamp": 12345.678,        // adapter time.monotonic() seconds at BLE receipt
  "seq": 26376,                  // controller's own ms counter (wraps); for drop detection
  "controller": "left",          // "left" | "right"
  "buttons": { "up": false, "down": false, "...": false },   // full set for that side, see §5
  "stick": { "x": 0.0, "y": 0.0 },           // normalised, see §4
  "stickRaw": { "x": 1925, "y": 2191 },      // 12-bit counts as reported, 0..4095 (diagnostic)
  "accelerometer": { "x": 0.0, "y": 0.0, "z": 1.0 },   // g, calibrated (bias removed once imuReady)
  "gyroscope": { "x": 0.0, "y": 0.0, "z": 0.0 },       // rad/s, calibrated (bias removed once imuReady)
  "battery": { "voltage": 3.9, "current": 0.0 },        // volts, mA; may be null
  "temperature": 30.0,                                  // deg C; may be null (unverified field)
  "imuReady": true                                      // false while the IMU calibration is pending
}
```

- `gyroscope` is **rad/s** (ADR-4). `orientation` is intentionally not here —
  the Motion Engine owns fusion.
- `imuReady: false` → ignore `accelerometer`/`gyroscope` for motion (the
  Motion Engine does). The calibration needs ~2 s of the controller lying
  still; it restarts if the controller moves. `--no-calibrate` makes every
  frame `imuReady: true`. Absent (other providers) = true.

## 4. Sticks

`stick.x` / `stick.y` in [-1, 1]: **+x = right, +y = up**, magnitude clamped to
the unit circle (diagonals reach ~(0.71, 0.71), not (1, 1)), and **exactly
0, 0 at rest** (radial dead zone, default 0.08, output rescaled from its edge).

The Joy-Con 2 reports raw, uncalibrated 12-bit values. At connect the adapter
reads each controller's **factory stick calibration** (centre + travel in each
direction) and normalises with it; travel only grows if a push goes further.
If the read ever fails it falls back to learning the rest centre (first still
moment near 2048) and a nominal 1100-count travel. On the project's two units:
exactly 0 at rest, r ≥ 0.99 in all 8 directions. `stickRaw` keeps the untouched
counts for diagnostics or custom calibration.
(Why: v1 divided by 2048 although the real travel is only ~±1150–1300 counts,
so sticks topped out near ±0.6 — see `adapter/src/calibration/stick.py`.)

## 5. Buttons

`true` while held. Every frame carries the full set of its side; edge
detection (press/release) is the client's job (§6).

| side | names |
| --- | --- |
| left | `up` `down` `left` `right` (D-pad), `l` `zl`, `sl` `sr` (rail), `minus`, `capture`, `stick` (stick click) |
| right | `a` `b` `x` `y`, `r` `zr`, `sl` `sr` (rail), `plus`, `home`, `c` (C / GameChat), `stick` (stick click) |

The Sync button is not an input (verified: never appears in any frame) — a
short press while connected disconnects the controller, holding it starts
pairing.
Bit positions and their verification status: `docs/JOYCON2_PROTOCOL.md` §E.

## 6. Client rules (what `input-client.mjs` implements)

1. Track state per `controller`. Left and right are independent.
2. A controller is **online** only while its last status is `connected`.
   Ignore frames for a controller that is not online.
3. Press/release = edges between consecutive frames of the same controller.
4. When a controller goes offline (status not `connected`), when the WebSocket
   closes, or when no frame arrived for ~1 s (stale): **release everything it
   had pressed and centre its stick**. When it comes back, the next frame
   re-presses whatever is still held.
5. Reject envelopes whose `v` differs from the version you were written for.

```js
import { connectJoyCon2 } from "shared/protocol/input-client.mjs";
const jc = connectJoyCon2({ controllers: ["right"] });     // or both (default)
jc.on("press",   ({ controller, button }) => …);
jc.on("release", ({ controller, button, reason }) => …);  // reason: input | offline | stale | transport
jc.on("device",  (d) => d.online …);
jc.device("right").stick;  jc.isPressed("right", "zr");
```

## 7. MotionState (Motion Engine → Game)

```json
{
  "timestamp": 12345.678,
  "controller": "left",
  "orientation": { "quaternion": [w, x, y, z], "euler": { "pitch": 0, "yaw": 0, "roll": 0 } },
  "angularVelocity": { "x": 0.0, "y": 0.0, "z": 0.0 },     // rad/s, filtered
  "linearAcceleration": { "x": 0.0, "y": 0.0, "z": 0.0 },  // g, gravity removed
  "motionSpeed": 0.0,      // scalar 0..~1+, normalized overall motion magnitude
  "gesture": null           // most recent GestureEvent within the last ~200 ms, else null
}
```

## 8. GestureEvent (Motion Engine → Game)

```json
{
  "gesture": "SLASH_RIGHT",   // SLASH_LEFT | SLASH_RIGHT | SLASH_UP | SLASH_DOWN | THRUST | SHAKE | ROTATE
  "strength": 0.82,            // 0..1, normalized peak magnitude
  "speed": 4.1,                // rad/s (or g for THRUST), raw peak
  "direction": [x, y, z],      // unit vector in controller frame, dominant motion axis
  "timestamp": 12345.678,
  "controller": "left"
}
```

`direction` is `[]`-shaped in the GOAL example; we always send a 3-number unit
vector (empty only if indeterminate).
