// web/src/input/mock-imu-provider.js
// No hardware. Emits synthetic InputFrames at ~62 Hz: gentle idle wobble plus a
// scripted gesture cycle (slash R -> L -> up -> down -> thrust). Mirrors the
// adapter SyntheticSource so the whole stack can be developed and demoed with
// nothing plugged in (GOAL.md §13 fallback).

import { InputProvider, nowSeconds } from "./provider.js";
import { BUTTONS_LEFT, BUTTONS_RIGHT } from "../../../shared/protocol/contracts.mjs";

const DEG2RAD = Math.PI / 180;

const SCRIPT = [
  { at: 2.0, kind: "SLASH_RIGHT", axis: "z", peak: 900 },
  { at: 4.0, kind: "SLASH_LEFT", axis: "z", peak: -900 },
  { at: 6.0, kind: "SLASH_UP", axis: "x", peak: 900 },
  { at: 8.0, kind: "SLASH_DOWN", axis: "x", peak: -900 },
  { at: 10.0, kind: "THRUST", axis: "accelY", peak: 3.2 },
];
const CYCLE = 12.0;
const BURST = 0.14; // seconds

export class MockIMUProvider extends InputProvider {
  constructor(opts = {}) {
    super("mock-imu", opts);
    this.rateHz = opts.rateHz ?? 62;
    this._timer = null;
    this._t0 = 0;
    this._seq = 0;
    this._scripted = opts.scripted ?? true;
  }

  get label() {
    return "Mock IMU (no hardware)";
  }

  async connect() {
    this.connected = true;
    this.calibrated = true; // synthetic data has no bias
    this._t0 = nowSeconds();
    this._seq = 0;
    this._emitStatus("connected");
    const dt = 1000 / this.rateHz;
    this._timer = setInterval(() => this._tick(), dt);
  }

  disconnect() {
    if (this._timer) clearInterval(this._timer);
    this._timer = null;
    super.disconnect();
  }

  /** Advance one manual step (used by tests instead of the timer). */
  step(tSeconds) {
    this._emitAt(tSeconds);
  }

  _tick() {
    this._emitAt(nowSeconds() - this._t0);
  }

  _emitAt(t) {
    const gyro = {
      x: 12 * Math.sin(t * 1.7),
      y: 9 * Math.sin(t * 1.1 + 1),
      z: 7 * Math.sin(t * 0.9 + 2),
    };
    const accel = { x: 0.04 * Math.sin(t * 2), y: 0.04 * Math.cos(t * 1.3), z: 1.0 };

    if (this._scripted) {
      const phase = t % CYCLE;
      for (const s of SCRIPT) {
        const rel = phase - s.at;
        if (rel >= 0 && rel < BURST) {
          const env = Math.sin((rel / BURST) * Math.PI);
          if (s.axis === "accelY") accel.y += s.peak * env;
          else gyro[s.axis] += s.peak * env;
        }
      }
    }

    const names = this.controller === "left" ? BUTTONS_LEFT : BUTTONS_RIGHT;
    const buttons = {};
    for (const n of names) buttons[n] = false;

    this._emitFrame({
      timestamp: this._t0 + t,
      seq: this._seq++,
      controller: this.controller,
      buttons,
      stick: { x: 0, y: 0 },
      accelerometer: accel,
      // contract: rad/s on the wire
      gyroscope: { x: gyro.x * DEG2RAD, y: gyro.y * DEG2RAD, z: gyro.z * DEG2RAD },
      battery: { voltage: 3.9, current: 0 },
      temperature: 30,
    });
  }
}
