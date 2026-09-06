// web/src/input/gamepad-provider.js
// Standard Gamepad API. NOTE (docs/ARCHITECTURE.md §2, approach C): the Gamepad
// API has no orientation concept -- it gives buttons + sticks only. This provider
// therefore does NOT provide a real IMU; it derives a coarse angular velocity
// from the right stick so gesture mapping can still be exercised.

import { InputProvider, nowSeconds } from "./provider.js";

const DEG2RAD = Math.PI / 180;
const STICK_TO_DPS = 900;

export class GamepadProvider extends InputProvider {
  constructor(opts = {}) {
    super("gamepad", opts);
    this.rateHz = opts.rateHz ?? 62;
    this.index = opts.index ?? null;
    this._timer = null;
    this._seq = 0;
  }

  get label() {
    return "Gamepad API (no IMU — sticks only)";
  }
  get providesIMU() {
    return false;
  }

  async connect() {
    if (!("getGamepads" in navigator)) throw new Error("Gamepad API unavailable");
    this.connected = true;
    this.calibrated = true;
    this._emitStatus("connecting");
    await this._waitForPad(4000);
    this._emitStatus("connected");
    this._timer = setInterval(() => this._tick(), 1000 / this.rateHz);
  }

  disconnect() {
    if (this._timer) clearInterval(this._timer);
    this._timer = null;
    super.disconnect();
  }

  _pad() {
    const pads = navigator.getGamepads?.() ?? [];
    if (this.index != null) return pads[this.index] ?? null;
    for (const p of pads) if (p && p.connected) return p;
    return null;
  }

  _waitForPad(timeoutMs) {
    return new Promise((resolve, reject) => {
      const t0 = performance.now();
      const poll = () => {
        if (this._pad()) return resolve();
        if (performance.now() - t0 > timeoutMs) return reject(new Error("no gamepad connected"));
        setTimeout(poll, 100);
      };
      poll();
    });
  }

  _tick() {
    const pad = this._pad();
    if (!pad) return;
    const [, , rx = 0, ry = 0] = pad.axes;
    const buttons = {};
    pad.buttons.forEach((b, i) => (buttons[`b${i}`] = b.pressed));

    this._emitFrame({
      timestamp: nowSeconds(),
      seq: this._seq++,
      controller: this.controller,
      buttons,
      stick: { x: pad.axes[0] ?? 0, y: pad.axes[1] ?? 0 },
      accelerometer: { x: 0, y: 0, z: 1 },
      gyroscope: {
        x: -ry * STICK_TO_DPS * DEG2RAD,
        y: 0,
        z: rx * STICK_TO_DPS * DEG2RAD,
      },
      battery: null,
      temperature: null,
    });
  }
}
