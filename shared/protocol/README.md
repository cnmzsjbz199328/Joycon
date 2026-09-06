# shared/protocol/ — data contracts

The single source of truth for every message that crosses a layer boundary.
Both the Python adapter and the browser import from here.

| Contract | Producer → Consumer | File |
| --- | --- | --- |
| **InputFrame** (§8.1) | Adapter → Browser (over WebSocket) | `schema.json#/definitions/InputFrame`, `frame.py`, `contracts.mjs` |
| **MotionState** (§7.2 / §8.2) | Motion Engine → Game | `schema.json#/definitions/MotionState`, `contracts.mjs` |
| **GestureEvent** (§8.3) | Motion Engine → Game | `schema.json#/definitions/GestureEvent`, `contracts.mjs` |

Version: `PROTOCOL_VERSION = 1`. Sent in every WebSocket envelope; bump on any
breaking field change.

---

## 1. Transport envelope (WebSocket)

`ws://127.0.0.1:8765`. Server = adapter, clients = browser pages (Playground and
Game may both connect). One JSON object per text message:

```json
{ "v": 1, "type": "frame",  "data": { /* InputFrame */ } }
{ "v": 1, "type": "hello",  "data": { "adapter": "0.1.0", "source": "synthetic", "rateHz": 62 } }
{ "v": 1, "type": "status", "data": { "connection": "connected", "controller": "left", "calibrated": true } }
```

- `frame` messages are sent **at the device rate, with no downsampling and no
  coalescing** (GOAL.md §9). One BLE notification → one `frame` message.
- `hello` is sent once on connect; `status` whenever connection/calibration state
  changes.

## 2. InputFrame (Adapter → Browser)

```json
{
  "timestamp": 12345.678,        // adapter time.monotonic() seconds, float; receipt time of the BLE notification
  "seq": 26376,                  // controller packet id (wraps); for drop detection
  "controller": "left",          // "left" | "right"
  "buttons": { "up": false, "l": false, "...": false },
  "stick": { "x": 0.0, "y": 0.0 },          // [-1, 1]
  "accelerometer": { "x": 0.0, "y": 0.0, "z": 1.0 },   // g, calibrated (bias removed)
  "gyroscope": { "x": 0.0, "y": 0.0, "z": 0.0 },       // rad/s, calibrated (bias removed)
  "battery": { "voltage": 3.9, "current": 0.0 },        // volts, mA; may be null
  "temperature": 30.0                                    // deg C; may be null
}
```

Notes:
- `gyroscope` is **rad/s** here (decoder works in deg/s; the adapter converts on
  normalize so the Motion Engine can integrate directly). ADR-4.
- `accelerometer` / `gyroscope` already have the calibration bias subtracted.
- `orientation` is intentionally **not** in InputFrame — the adapter does not do
  fusion; the Motion Engine owns orientation.

## 3. MotionState (Motion Engine → Game)

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

## 4. GestureEvent (Motion Engine → Game)

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
