// web/src/motion/gestures.js
// Threshold + dominant-axis swing detector over a short sliding window. Uses the
// frame timestamp (not rAF) so detection is render-rate independent (GOAL.md §9).
//
// Axis convention (Joy-Con held pointing away from you):
//   gyro.z (yaw)   +  -> swing right  -> SLASH_RIGHT ;  -  -> SLASH_LEFT
//   gyro.x (pitch) +  -> swing up     -> SLASH_UP    ;  -  -> SLASH_DOWN
//   gyro.y (roll)     -> ROTATE
//   linearAccel forward spike w/ low rotation -> THRUST
//   many rotation reversals, no dominant axis   -> SHAKE

import { Window } from "./filters.js";

const GESTURE_NAMES = [
  "SLASH_LEFT",
  "SLASH_RIGHT",
  "SLASH_UP",
  "SLASH_DOWN",
  "THRUST",
  "SHAKE",
  "ROTATE",
];

export class GestureRecognizer {
  constructor(opts = {}) {
    // rad/s. Retuned against real hardware 2026-09-06 (right Joy-Con 2, macOS):
    // a gentle handling wobble is ~0.9 rad/s, a firm slash ~1.6-2.0, an all-out
    // spin peaks ~2.7. The original 6.0 / 14.0 were calibrated to the Mock IMU
    // (synthetic 900 dps / 15.7 rad/s bursts) and were unreachable on hardware,
    // so every real swing fell through to THRUST. Mock still clears these easily.
    // Lowered 1.5 -> 1.1 on 2026-09-28 (left Joy-Con 2, natural connected
    // up/down + left/right combos, not a single isolated max-effort strike):
    // real peak rotation for these was consistently 1.2-1.5 rad/s, i.e. below
    // the old threshold no matter how long THRUST's hold waited -- a natural,
    // fluid swing spreads effort over the combo instead of concentrating it
    // into one committed strike, so its peak is genuinely lower than the
    // original single-strike calibration. 1.1 clears the observed range with
    // a small margin above the ~0.9 gentle-wobble floor.
    // See docs/MOTION_ENGINE.md §3 and docs/HARDWARE_BRINGUP.md §5.
    this.enterSpeed = opts.enterSpeed ?? 1.1;
    this.exitSpeed = opts.exitSpeed ?? 0.6;
    this.fullSpeed = opts.fullSpeed ?? 2.6; // -> strength 1.0
    this.thrustAccel = opts.thrustAccel ?? 2.0; // g, gravity removed
    // Consecutive frames the low-rotation gate must hold before committing to
    // THRUST (see update()). Real swings on hardware show linear accel spiking
    // several frames *before* rotation ramps past enterSpeed -- checking the
    // window peak on the very first qualifying frame catches a slash mid
    // wind-up and misreads it as a thrust. Real hardware data (2026-09-28, left
    // Joy-Con 2, two separate test rounds): a hold of 3 frames (~90 ms @ 33 Hz)
    // still fired one frame too early on most swings (rotation crossed
    // enterSpeed on the very next frame); 4 frames (~120 ms) cleared 3 of 4
    // observed swings, only missing one still-ambiguous case. This is a
    // real-time classifier trading a bit of THRUST latency for far fewer
    // false positives -- expect it to not be perfect on every swing.
    this.thrustHoldFrames = opts.thrustHoldFrames ?? 4;
    this.refractory = opts.refractory ?? 0.28; // seconds between emitted gestures
    this.window = new Window(opts.windowSpan ?? 0.35);

    this._inSwing = false;
    this._peak = null; // { speed, vec:[x,y,z], t }
    this._lastEmit = -1e9;
    this._thrustHoldCount = 0;
    this._controller = opts.controller ?? "left";
  }

  reset() {
    this.window.clear();
    this._inSwing = false;
    this._peak = null;
    this._thrustHoldCount = 0;
  }

  /**
   * @param {number} t seconds (frame timestamp)
   * @param {[number,number,number]} gyro rad/s, calibrated
   * @param {[number,number,number]} linAccel g, gravity removed
   * @param {string} controller
   * @returns {null | object} a GestureEvent when one completes this frame
   */
  update(t, gyro, linAccel, controller = this._controller) {
    this._controller = controller;
    const speed = Math.hypot(gyro[0], gyro[1], gyro[2]);
    const accelMag = Math.hypot(linAccel[0], linAccel[1], linAccel[2]);
    this.window.push({ t, gyro: gyro.slice(), linAccel: linAccel.slice(), speed, accelMag });

    // THRUST: strong linear accel with LOW rotation across the whole recent
    // window -- not just this frame. A slash also spikes linear accel on the
    // wind-up, while its rotation is still ramping past enterSpeed; checking the
    // instantaneous speed alone let THRUST fire first and the refractory then
    // swallowed the slash. Requiring the window peak to stay sub-threshold hands
    // any rotation burst to the swing path instead (real-hardware fix 2026-09-06).
    const windowPeakSpeed = Math.max(
      speed,
      ...this.window.items.map((it) => it.speed),
    );
    const thrustCandidate =
      accelMag > this.thrustAccel &&
      windowPeakSpeed < this.enterSpeed &&
      !this._inSwing &&
      t - this._lastEmit > this.refractory;
    this._thrustHoldCount = thrustCandidate ? this._thrustHoldCount + 1 : 0;
    if (thrustCandidate && this._thrustHoldCount >= this.thrustHoldFrames) {
      // direction = dominant linear-accel axis
      const dir = unit(linAccel);
      this._lastEmit = t;
      this._thrustHoldCount = 0;
      return this._event("THRUST", accelMag, dir, t);
    }

    if (!this._inSwing) {
      if (speed > this.enterSpeed && t - this._lastEmit > this.refractory) {
        this._inSwing = true;
        this._peak = { speed, vec: gyro.slice(), t };
      }
      return null;
    }

    // A real swing-back (up<->down, left<->right, ...) is one continuous human
    // motion that never dips through exitSpeed in between -- so before folding
    // this frame into the peak, check whether the peak's dominant axis just
    // reversed sign with comparable force. Without this, the second half only
    // ever wins if it's the larger peak, and the first half's gesture is lost
    // entirely (never emitted, magnitude-only peak tracking has no way to
    // notice a direction flip on its own).
    const peakAxis = dominantAxis(this._peak.vec);
    if (
      Math.sign(gyro[peakAxis]) !== Math.sign(this._peak.vec[peakAxis]) &&
      Math.abs(gyro[peakAxis]) > this.enterSpeed
    ) {
      const ev = this._classify(this._peak, t);
      this._peak = { speed, vec: gyro.slice(), t };
      if (ev) this._lastEmit = t;
      return ev;
    }

    // in a swing: track the peak
    if (speed > this._peak.speed) this._peak = { speed, vec: gyro.slice(), t };

    if (speed < this.exitSpeed) {
      const ev = this._classify(this._peak, t);
      this._inSwing = false;
      this._peak = null;
      if (ev) this._lastEmit = t;
      return ev;
    }
    return null;
  }

  _classify(peak, t) {
    const [gx, gy, gz] = peak.vec;
    const ax = Math.abs(gx);
    const ay = Math.abs(gy);
    const az = Math.abs(gz);

    // SHAKE: look for >=3 sign changes of the largest-variance axis in the window
    if (this._looksLikeShake()) {
      return this._event("SHAKE", peak.speed, unit(peak.vec), t);
    }

    let name;
    if (az >= ax && az >= ay) {
      name = gz >= 0 ? "SLASH_RIGHT" : "SLASH_LEFT";
    } else if (ax >= ay && ax >= az) {
      name = gx >= 0 ? "SLASH_UP" : "SLASH_DOWN";
    } else {
      name = "ROTATE";
    }
    return this._event(name, peak.speed, unit(peak.vec), t);
  }

  _looksLikeShake() {
    const items = this.window.items;
    if (items.length < 6) return false;
    // dominant axis across the window
    let sx = 0, sy = 0, sz = 0;
    for (const it of items) {
      sx += it.gyro[0] * it.gyro[0];
      sy += it.gyro[1] * it.gyro[1];
      sz += it.gyro[2] * it.gyro[2];
    }
    const axis = sx >= sy && sx >= sz ? 0 : sy >= sz ? 1 : 2;
    let changes = 0;
    let prevSign = 0;
    let maxAbs = 0;
    for (const it of items) {
      const v = it.gyro[axis];
      maxAbs = Math.max(maxAbs, Math.abs(v));
      const s = Math.sign(v);
      if (s !== 0 && prevSign !== 0 && s !== prevSign) changes++;
      if (s !== 0) prevSign = s;
    }
    return changes >= 3 && maxAbs > this.enterSpeed * 0.6;
  }

  _event(gesture, speed, direction, t) {
    return {
      gesture,
      strength: Math.max(0, Math.min(1, speed / this.fullSpeed)),
      speed,
      direction,
      timestamp: t,
      controller: this._controller,
    };
  }
}

export { GESTURE_NAMES };

function unit(v) {
  const n = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / n, v[1] / n, v[2] / n];
}

function dominantAxis([x, y, z]) {
  const ax = Math.abs(x), ay = Math.abs(y), az = Math.abs(z);
  if (az >= ax && az >= ay) return 2;
  if (ax >= ay && ax >= az) return 0;
  return 1;
}
