// shared/protocol/input-client.mjs
// Reference client for the adapter's public WebSocket interface. Turns the
// per-controller state frames into a stable input API:
//
//   const jc = connectJoyCon2();                       // ws://127.0.0.1:8765
//   jc.on("press",   ({ controller, button }) => ...); // "left"/"right", "a", "zl", ...
//   jc.on("release", ({ controller, button, reason }) => ...);
//   jc.on("stick",   ({ controller, x, y }) => ...);   // +x right, +y up, [-1, 1]
//   jc.on("device",  (d) => ...);                      // d.online, d.connection, ...
//   jc.device("right").buttons.a; jc.isPressed("left", "zl");
//
// Guarantees (the whole point -- no stuck keys):
//   - every press is followed by exactly one release;
//   - a controller that is not online has nothing pressed and sticks at 0,0.
//     It goes offline when the adapter reports it not "connected", when the
//     WebSocket closes, or when no frame arrived for `staleMs` (it comes back
//     on the next frame, re-pressing whatever is still held);
//   - frames for an offline controller are ignored.
//
// JoyCon2Input is pure state logic (no I/O) so it can be unit-tested and fed
// from any transport; connectJoyCon2() wires it to a WebSocket (browser or
// Node >= 22). No dependencies besides contracts.mjs.

import { PROTOCOL_VERSION, WS_DEFAULT_URL, CONTROLLER, buttonsFor, neutralButtons } from "./contracts.mjs";

const defaultNow = () => globalThis.performance.now();

function makeDevice(controller) {
  return {
    controller,
    connection: "unknown", // last adapter status for this controller
    online: false, // connection === "connected" && frames not stale
    stale: false,
    calibrated: false,
    imuReady: false,
    address: null,
    hint: null,
    buttons: neutralButtons(controller),
    stick: { x: 0, y: 0 },
    stickRaw: null,
    battery: null,
    timestamp: null, // adapter clock (s) of the last frame
    seq: null,
    frames: 0,
    ignoredFrames: 0,
    lastFrameAt: null, // local clock (ms)
  };
}

export class JoyCon2Input extends EventTarget {
  /** @param {{controllers?: string[], staleMs?: number, now?: () => number}} [opts] */
  constructor({ controllers = CONTROLLER, staleMs = 1000, now = defaultNow } = {}) {
    super();
    this.controllers = [...controllers];
    this.staleMs = staleMs;
    this.now = now;
    this.adapter = { transport: "closed", hello: null };
    this.devices = Object.fromEntries(this.controllers.map((c) => [c, makeDevice(c)]));
    this._badVersions = new Set();
  }

  /** Subscribe; returns an unsubscribe function. */
  on(type, fn) {
    const h = (e) => fn(e.detail);
    this.addEventListener(type, h);
    return () => this.removeEventListener(type, h);
  }

  device(controller) {
    return this.devices[controller] ?? null;
  }

  isPressed(controller, button) {
    return !!this.devices[controller]?.buttons[button];
  }

  _emit(type, detail) {
    this.dispatchEvent(new CustomEvent(type, { detail }));
  }

  _emitDevice(dev) {
    const { lastFrameAt, ...snapshot } = dev;
    this._emit("device", { ...snapshot, buttons: { ...dev.buttons } });
  }

  _releaseAll(dev, reason) {
    for (const name of Object.keys(dev.buttons)) {
      if (dev.buttons[name]) {
        dev.buttons[name] = false;
        this._emit("release", { controller: dev.controller, button: name, reason, timestamp: dev.timestamp, localTime: this.now() });
      }
    }
    if (dev.stick.x !== 0 || dev.stick.y !== 0) {
      dev.stick = { x: 0, y: 0 };
      this._emit("stick", { controller: dev.controller, x: 0, y: 0, raw: dev.stickRaw, reason });
    }
  }

  _setOffline(dev, reason) {
    const was = dev.online;
    dev.online = false;
    this._releaseAll(dev, reason);
    return was;
  }

  /** Feed one WebSocket message (string or already-parsed object). */
  handleMessage(message) {
    let msg = message;
    if (typeof message === "string") {
      try {
        msg = JSON.parse(message);
      } catch {
        return;
      }
    }
    if (!msg || typeof msg !== "object" || typeof msg.type !== "string") return;
    if (msg.v !== PROTOCOL_VERSION) {
      if (!this._badVersions.has(msg.v)) {
        this._badVersions.add(msg.v);
        this._emit("error", { message: `adapter speaks protocol v${msg.v}, this client v${PROTOCOL_VERSION}` });
      }
      return;
    }
    const data = msg.data ?? {};
    if (msg.type === "hello") {
      this.adapter.hello = data;
      this._emit("adapter", { ...this.adapter });
    } else if (msg.type === "status") {
      this._status(data);
    } else if (msg.type === "frame") {
      this._frame(data);
    }
  }

  _status(s) {
    const dev = this.devices[s.controller];
    if (!dev) return; // "unknown" or a controller this client did not ask for
    dev.connection = s.connection;
    dev.calibrated = !!s.calibrated;
    dev.hint = s.hint ?? null;
    dev.address = s.address ?? dev.address;
    if (s.connection === "connected") {
      dev.online = true;
      dev.stale = false;
      dev.lastFrameAt = this.now(); // grace period before the stale check applies
    } else {
      this._setOffline(dev, "offline");
      dev.stale = false;
      dev.imuReady = false;
    }
    this._emitDevice(dev);
  }

  _frame(f) {
    const dev = this.devices[f.controller];
    if (!dev) return;
    if (dev.connection !== "connected") {
      dev.ignoredFrames++;
      return;
    }
    dev.lastFrameAt = this.now();
    const wasOffline = !dev.online;
    dev.online = true;
    dev.stale = false;
    dev.timestamp = f.timestamp;
    dev.seq = f.seq;
    dev.frames++;
    dev.imuReady = f.imuReady !== false;
    dev.battery = f.battery ?? null;
    dev.stickRaw = f.stickRaw ?? null;
    if (wasOffline) this._emitDevice(dev);

    const fb = f.buttons ?? {};
    for (const name of buttonsFor(dev.controller)) {
      const down = !!fb[name];
      if (down === dev.buttons[name]) continue;
      dev.buttons[name] = down;
      this._emit(down ? "press" : "release", {
        controller: dev.controller, button: name, timestamp: f.timestamp, localTime: dev.lastFrameAt,
        ...(down ? {} : { reason: "input" }),
      });
    }
    const x = f.stick?.x ?? 0;
    const y = f.stick?.y ?? 0;
    if (x !== dev.stick.x || y !== dev.stick.y) {
      dev.stick = { x, y };
      this._emit("stick", { controller: dev.controller, x, y, raw: dev.stickRaw });
    }
    this._emit("frame", { controller: dev.controller, frame: f });
  }

  handleTransportOpen() {
    this.adapter.transport = "open";
    this._emit("adapter", { ...this.adapter });
  }

  /** The WebSocket closed: nothing the adapter said still holds. */
  handleTransportClosed() {
    this.adapter.transport = "closed";
    for (const dev of Object.values(this.devices)) {
      this._setOffline(dev, "transport");
      dev.connection = "unknown";
      dev.stale = false;
      dev.imuReady = false;
      this._emitDevice(dev);
    }
    this._emit("adapter", { ...this.adapter });
  }

  /** Stale-frame watchdog; call periodically (connectJoyCon2 does, every 100 ms). */
  tick() {
    const t = this.now();
    for (const dev of Object.values(this.devices)) {
      if (dev.online && dev.lastFrameAt != null && t - dev.lastFrameAt > this.staleMs) {
        dev.stale = true;
        this._setOffline(dev, "stale");
        this._emitDevice(dev);
      }
    }
  }
}

/**
 * Connect a JoyCon2Input to the adapter and keep the socket open (reconnects
 * with a capped backoff). Returns the JoyCon2Input plus close() and send().
 * @param {{url?: string, controllers?: string[], staleMs?: number, reconnect?: boolean, WebSocketImpl?: any}} [opts]
 */
export function connectJoyCon2({
  url = WS_DEFAULT_URL,
  controllers,
  staleMs,
  reconnect = true,
  WebSocketImpl = globalThis.WebSocket,
} = {}) {
  if (!WebSocketImpl) throw new Error("no WebSocket implementation (Node >= 22 or a browser needed)");
  const input = new JoyCon2Input({ controllers, staleMs });
  let ws = null;
  let closed = false;
  let retry = 0;
  let retryTimer = null;

  const open = () => {
    input.adapter.transport = "connecting";
    input._emit("adapter", { ...input.adapter });
    ws = new WebSocketImpl(url);
    ws.onopen = () => {
      retry = 0;
      input.handleTransportOpen();
    };
    ws.onmessage = (ev) => input.handleMessage(typeof ev.data === "string" ? ev.data : String(ev.data));
    ws.onerror = () => {}; // onclose follows and handles it
    ws.onclose = () => {
      input.handleTransportClosed();
      if (!closed && reconnect) retryTimer = setTimeout(open, Math.min(8000, 500 * 2 ** retry++));
    };
  };
  const watchdog = setInterval(() => input.tick(), 100);
  open();

  input.close = () => {
    closed = true;
    clearInterval(watchdog);
    clearTimeout(retryTimer);
    ws?.close();
  };
  /** Send a client message, e.g. send("mark", {...}) for annotated captures. */
  input.send = (type, data) => {
    if (ws?.readyState !== 1) return false;
    ws.send(JSON.stringify({ v: PROTOCOL_VERSION, type, data }));
    return true;
  };
  return input;
}
