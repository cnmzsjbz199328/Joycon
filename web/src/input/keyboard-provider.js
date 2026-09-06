// web/src/input/keyboard-provider.js
// Fallback with zero hardware and no adapter. Arrow keys / WASD synthesise angular
// velocity; Space = thrust. Useful for developing game logic and gesture mapping.
//   Arrow Left/Right  -> gyro z -/+   (SLASH_LEFT / SLASH_RIGHT)
//   Arrow Up/Down      -> gyro x +/-   (SLASH_UP / SLASH_DOWN)
//   Space              -> accel y spike (THRUST)

import { InputProvider, nowSeconds } from "./provider.js";
import { BUTTONS_LEFT, BUTTONS_RIGHT } from "../../../shared/protocol/contracts.mjs";

const DEG2RAD = Math.PI / 180;
const IMPULSE_DEG = 850; // peak deg/s while a key is held
const RISE = 12; // how fast the synthetic rate approaches the target

export class KeyboardProvider extends InputProvider {
  constructor(opts = {}) {
    super("keyboard", opts);
    this.rateHz = opts.rateHz ?? 62;
    this._keys = new Set();
    this._timer = null;
    this._seq = 0;
    this._t0 = 0;
    this._g = { x: 0, y: 0, z: 0 };
    this._thrust = 0;
    this._onDown = (e) => this._set(e, true);
    this._onUp = (e) => this._set(e, false);
  }

  get label() {
    return "Keyboard (arrows / space)";
  }
  get providesIMU() {
    return false; // synthetic, not a real IMU
  }

  async connect() {
    this.connected = true;
    this.calibrated = true;
    this._t0 = nowSeconds();
    window.addEventListener("keydown", this._onDown);
    window.addEventListener("keyup", this._onUp);
    this._emitStatus("connected");
    this._timer = setInterval(() => this._tick(), 1000 / this.rateHz);
  }

  disconnect() {
    if (this._timer) clearInterval(this._timer);
    this._timer = null;
    window.removeEventListener("keydown", this._onDown);
    window.removeEventListener("keyup", this._onUp);
    super.disconnect();
  }

  _set(e, down) {
    const k = e.key.toLowerCase();
    const map = {
      arrowleft: "L", a: "L", arrowright: "R", d: "R",
      arrowup: "U", w: "U", arrowdown: "D", s: "D", " ": "T",
    };
    if (!(k in map)) return;
    e.preventDefault();
    if (down) this._keys.add(map[k]);
    else this._keys.delete(map[k]);
  }

  _tick() {
    const target = { x: 0, y: 0, z: 0 };
    if (this._keys.has("R")) target.z += IMPULSE_DEG;
    if (this._keys.has("L")) target.z -= IMPULSE_DEG;
    if (this._keys.has("U")) target.x += IMPULSE_DEG;
    if (this._keys.has("D")) target.x -= IMPULSE_DEG;
    const a = Math.min(1, RISE / this.rateHz);
    this._g.x += (target.x - this._g.x) * a;
    this._g.y += (target.y - this._g.y) * a;
    this._g.z += (target.z - this._g.z) * a;

    const targetThrust = this._keys.has("T") ? 3.0 : 0;
    this._thrust += (targetThrust - this._thrust) * a;

    const names = this.controller === "left" ? BUTTONS_LEFT : BUTTONS_RIGHT;
    const buttons = {};
    for (const n of names) buttons[n] = false;

    const t = nowSeconds();
    this._emitFrame({
      timestamp: t,
      seq: this._seq++,
      controller: this.controller,
      buttons,
      stick: { x: 0, y: 0 },
      accelerometer: { x: 0, y: this._thrust, z: 1 },
      gyroscope: {
        x: this._g.x * DEG2RAD,
        y: this._g.y * DEG2RAD,
        z: this._g.z * DEG2RAD,
      },
      battery: null,
      temperature: null,
    });
  }
}
