# Integrating Joy-Con 2 input into another project

Use this repository as a local input service: run its Python adapter on the
computer connected to the Joy-Cons, then consume the public WebSocket protocol
from your game or application. Buttons and sticks work without motion calibration.

中文说明：在连接手柄的电脑上运行 adapter，其他项目通过 WebSocket 读取输入；普通按键和摇杆不依赖体感标定。

## 1. Choose the integration boundary

- **Adapter:** owns BLE discovery, connection, decoding and calibration.
- **Your project:** owns action mapping, game logic and rendering.
- **Public contract:** [protocol v2](../shared/protocol/README.md).
- **JavaScript reference client:** [input-client.mjs](../shared/protocol/input-client.mjs),
  which imports [contracts.mjs](../shared/protocol/contracts.mjs).

There is no published npm or pip client package here. Keep a local checkout of
this repository, or vendor both JS modules together into your project while
preserving their relative import. Do not import a GitHub HTML file URL as a JS
module. Record the upstream commit/tag alongside any vendored files; keep the
adapter and client on compatible protocol versions (v1 and v2 are incompatible).

This interface supplies input to applications you control. It does not install
a virtual Xbox/DS4 controller for arbitrary existing games.

## 2. Start the adapter

The following commands run from the repository root. Use a Python 3 environment
compatible with [the dependencies](../adapter/requirements.txt).

```bash
git clone https://github.com/cnmzsjbz199328/Joycon.git
cd Joycon
# For repeatable deployments, check out your chosen reviewed tag or commit here.
python3 -m venv .venv
.venv/bin/pip install -r adapter/requirements.txt
.venv/bin/python -m adapter.src.service --source joycon2
```

Hold Sync on each Joy-Con until its player LEDs cycle. Allow Bluetooth access
for the process running Python if the OS requests it. By default, the adapter
looks for one left and one right controller. To use only one:

```bash
.venv/bin/python -m adapter.src.service --source joycon2 --side right
```

The default endpoint is `ws://127.0.0.1:8765`. The consumer must run on the same
computer for this address to work. `--host` and `--port` configure the listener;
configure the client URL accordingly. Remote deployment and HTTPS/WSS routing
are outside the verified local setup.

Buttons and sticks stream immediately; setting the controllers down for IMU
calibration is only required for motion consumers. You do not need to start
the web demo or Motion Engine to use the input service.

On Windows, use the corresponding `.venv\Scripts\python.exe` executable.
The hardware acceptance recorded here is for macOS/CoreBluetooth with two real
Joy-Con 2 units; other operating systems require their own hardware verification.

## 3. Verify the service before changing your application

In another terminal, from the repository root:

```bash
# Node.js 22 or newer; no npm install needed for this example
node examples/input-client.mjs
node examples/input-client.mjs right

# Python example, using the adapter's environment
.venv/bin/python examples/input_client.py
```

For an input dashboard:

```bash
cd web
npm install
npm run dev
```

Open <http://localhost:5173/input.html>. Confirm both device states, every button,
stick direction and release behavior before debugging your game mapping.

Without hardware, stop the hardware adapter and start one of these alternatives:

```bash
.venv/bin/python -m adapter.src.service --source synthetic --side both
.venv/bin/python -m adapter.src.service --source replay --file adapter/tests/fixtures/hw_2026-10-24_input.jsonl
```

Synthetic/replay sources verify integration behavior; they do not establish
hardware compatibility on a new machine.

## 4. JavaScript integration

Place `input-client.mjs` and `contracts.mjs` together under your project's
`vendor/joycon/` directory, then import from your application entry point:

```js
import { connectJoyCon2 } from "./vendor/joycon/input-client.mjs";

const input = connectJoyCon2({
  url: "ws://127.0.0.1:8765",
  controllers: ["left", "right"], // or just ["right"]
});

input.on("device", ({ controller, online, connection, hint }) => {
  console.log(controller, online, connection, hint);
});
input.on("press", ({ controller, button }) => {
  console.log("down", controller, button); // map to your application's actions
});
input.on("release", ({ controller, button, reason }) => {
  console.log("up", controller, button, reason);
});
input.on("error", ({ message }) => console.error(message));

// Call from your existing game update loop. Do not cache the stick object:
// the client replaces it as frames arrive.
function readControls() {
  const left = input.device("left");
  return {
    moveX: left.online ? left.stick.x : 0,
    moveY: left.online ? left.stick.y : 0,
    fire: input.isPressed("right", "zr"),
  };
}

// Call input.close() when your application disposes this connection.
```

The module works in a browser served by your application and in Node.js 22+.
The reference client handles socket retries, per-side state, edge events and a
default 1000 ms stale-frame watchdog. Subscribe to `stick` for changes, or poll
current state in your existing update loop. `on()` returns an unsubscribe function.

For other languages, implement the [client rules](../shared/protocol/README.md#6-client-rules-what-input-clientmjs-implements).
The [Python example](../examples/input_client.py) demonstrates raw WebSocket
consumption and clearing on offline/socket close, but currently has no stale-frame
watchdog: add one before relying on it for continuous held actions.

## 5. Input semantics that consumers must preserve

| Item | Meaning |
| --- | --- |
| Device selection | `controller` is `left` or `right`; current service supports one of each, not arbitrary multiple pairs |
| Device identity | `address` in status is diagnostic; on macOS it is a host-specific UUID, not a portable hardware identifier |
| Left buttons | `up down left right l zl sl sr minus capture stick` |
| Right buttons | `a b x y r zr sl sr plus home c stick` |
| Stick click | `stick` button on the corresponding controller |
| Sync | Pairing/connection control, not a gameplay input |
| Stick axes | `x` positive right, `y` positive up; both in [-1, 1] |
| Stick range | Radial dead zone; unit-circle clamp, so a full diagonal is approximately (0.71, 0.71) |
| Raw stick | `stickRaw` retains unnormalised 12-bit values for diagnostics |
| Button state | Full held-state snapshot in every frame; press/release are client-derived edges |
| Timing | `timestamp` is adapter monotonic seconds, not wall time; do not subtract it from another process's clock without synchronisation |
| Sequence | `seq` is the controller's wrapping millisecond counter, not a consecutive frame index |
| Motion readiness | `imuReady` concerns IMU only; it must not block buttons or sticks |

A socket opening does not mean either Joy-Con is online. Track each side's
status independently. Clear held buttons and centre sticks when it goes offline,
when the transport closes, or when frames become stale. Honor release events
regardless of their reason (`input`, `offline`, `stale`, `transport`). A held
button can produce a new press on the first frame after recovery.

The adapter retries a lost BLE connection. Hardware testing found that the user
may need to hold Sync again to make the controller advertise; follow status hints.
Rapid reconnection attempts may trigger a controller cooldown.

## 6. Acceptance boundary and source documents

Buttons, sticks, simultaneous left/right input and disconnect/reconnect behavior
were verified on the project's two units on macOS on 2026-10-24. Observed rate
was about 33 Hz per controller on that stack. Motion tuning is paused; latency
percentiles and other unverified fields must not be inferred from input acceptance.

- [Complete wire contract and lifecycle](../shared/protocol/README.md)
- [Runnable examples](../examples/README.md)
- [Hardware evidence and acceptance history](HARDWARE_BRINGUP.md)
- [BLE protocol and field verification](JOYCON2_PROTOCOL.md)
- [Software test records](TESTING.md)

## Handoff to another agent

Give the receiving project the repository URL, a reviewed tag/commit and this
file. Suggested instruction:

> Integrate Joy-Con 2 buttons and sticks from
> https://github.com/cnmzsjbz199328/Joycon at `<tag-or-commit>`.
> Read README.md and docs/INTEGRATION.md, then use the existing protocol v2
> service and reference client. Keep BLE decoding in the adapter. Implement
> application action mapping and verify offline/reconnect behavior. Only change
> the adapter if a concrete missing capability requires it.

中文提示：交接时附上仓库地址、已验收版本和本文档路径；先跑示例，再接业务映射。
