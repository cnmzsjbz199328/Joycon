// web/src/motion/motion-engine.js
// The one module games consume. In: InputFrames from any InputProvider.
// Out: "motion" events (MotionState, shared/protocol §7.2) + "gesture" events
// (GestureEvent, §8.3). Games NEVER touch raw IMU (GOAL.md §7.2, §14.6).
//
// Capabilities (GOAL.md §7.2): calibration, noise filtering, dead zone, drift
// handling, coordinate normalization, motion magnitude, gesture detection.

import { LowPass, HighPass, deadZone } from "./filters.js";
import { ComplementaryOrientation, MadgwickOrientation } from "./orientation.js";
import { GestureRecognizer } from "./gestures.js";
import { qRotate, qConjugate, qToEuler } from "./quaternion.js";
import { emptyMotionState } from "../../../shared/protocol/contracts.mjs";

const GESTURE_HOLD_S = 0.2; // how long a gesture stays attached to MotionState

export class MotionEngine extends EventTarget {
  constructor(opts = {}) {
    super();
    this.filter =
      opts.filter === "madgwick"
        ? new MadgwickOrientation(opts.madgwick)
        : new ComplementaryOrientation(opts.complementary);
    this.filterName = opts.filter === "madgwick" ? "madgwick" : "complementary";

    this.gyroLP = new LowPass(opts.gyroCutoffHz ?? 12, 3);
    this.accelLP = new LowPass(opts.accelCutoffHz ?? 6, 3);
    this.accelHP = new HighPass(opts.accelHpHz ?? 1.5, 3);
    this.recognizer = new GestureRecognizer(opts.gesture);

    // runtime calibration (in addition to any the adapter already did)
    this.calibration = { gyroBias: [0, 0, 0], gyroDeadZone: opts.gyroDeadZone ?? 0.03 };
    this._calSamples = null;

    this.motionSpeedLP = new LowPass(opts.speedCutoffHz ?? 10, 1);
    this.fullSpeed = opts.fullSpeed ?? (opts.gesture?.fullSpeed ?? 14);

    this._lastT = null;
    this._state = emptyMotionState(opts.controller ?? "left");
    this._lastGesture = null;
  }

  get state() {
    return this._state;
  }

  /** Begin an N-second still calibration; feed() collects samples until done. */
  startCalibration(seconds = 2) {
    this._calSamples = { until: null, seconds, gx: [], gy: [], gz: [] };
    this.dispatchEvent(new CustomEvent("calibration", { detail: { phase: "start", progress: 0 } }));
  }

  isCalibrating() {
    return this._calSamples != null;
  }

  reset() {
    this.filter.reset();
    this.gyroLP.reset();
    this.accelLP.reset();
    this.accelHP.reset();
    this.recognizer.reset();
    this._lastT = null;
  }

  /** @param {import('../../../shared/protocol/contracts.mjs')} frame  InputFrame */
  feed(frame) {
    const t = frame.timestamp;
    let dt = this._lastT == null ? 1 / 62 : t - this._lastT;
    if (!(dt > 0) || dt > 0.25) dt = 1 / 62; // guard against gaps / bad clocks
    this._lastT = t;

    const gyroRaw = [frame.gyroscope.x, frame.gyroscope.y, frame.gyroscope.z];
    const accelRaw = [frame.accelerometer.x, frame.accelerometer.y, frame.accelerometer.z];

    // --- calibration collection ---
    if (this._calSamples) {
      const c = this._calSamples;
      if (c.until == null) c.until = t + c.seconds;
      c.gx.push(gyroRaw[0]); c.gy.push(gyroRaw[1]); c.gz.push(gyroRaw[2]);
      const progress = Math.min(1, 1 - (c.until - t) / c.seconds);
      this.dispatchEvent(new CustomEvent("calibration", { detail: { phase: "collecting", progress } }));
      if (t >= c.until && c.gx.length > 20) {
        const mean = (a) => a.reduce((s, v) => s + v, 0) / a.length;
        const std = (a, m) => Math.sqrt(a.reduce((s, v) => s + (v - m) ** 2, 0) / a.length);
        const bx = mean(c.gx), by = mean(c.gy), bz = mean(c.gz);
        this.calibration.gyroBias = [bx, by, bz];
        this.calibration.gyroDeadZone = 3 * Math.max(std(c.gx, bx), std(c.gy, by), std(c.gz, bz)) + 0.005;
        this._calSamples = null;
        this.filter.reset();
        this.dispatchEvent(
          new CustomEvent("calibration", { detail: { phase: "done", progress: 1, result: { ...this.calibration } } }),
        );
      }
    }

    // --- de-bias + dead zone + low-pass (noise filtering, drift handling) ---
    const gyro = gyroRaw.map((v, i) =>
      deadZone(v - this.calibration.gyroBias[i], this.calibration.gyroDeadZone),
    );
    const gyroF = this.gyroLP.update(gyro, dt).slice();
    const accelF = this.accelLP.update(accelRaw, dt).slice();

    // --- orientation ---
    const q = this.filter.update(gyroF, accelF, dt).slice();

    // --- linear acceleration = measured - gravity (rotate world up into body) ---
    const gravityBody = qRotate(qConjugate(q), [0, 0, 1]);
    const linAccel = accelRaw.map((v, i) => v - gravityBody[i]);
    const linAccelHP = this.accelHP.update(linAccel, dt).slice();

    // --- motion magnitude (normalized 0..~1+) ---
    const angSpeed = Math.hypot(gyroF[0], gyroF[1], gyroF[2]);
    const linMag = Math.hypot(linAccelHP[0], linAccelHP[1], linAccelHP[2]);
    const rawSpeed = angSpeed / this.fullSpeed + linMag / 3.0;
    const motionSpeed = this.motionSpeedLP.update([rawSpeed], dt)[0];

    // --- gestures (on the transient-isolated signals) ---
    const ev = this.recognizer.update(t, gyroF, linAccelHP, frame.controller);
    if (ev) {
      this._lastGesture = ev;
      this.dispatchEvent(new CustomEvent("gesture", { detail: ev }));
    }

    const attachedGesture =
      this._lastGesture && t - this._lastGesture.timestamp <= GESTURE_HOLD_S
        ? this._lastGesture
        : null;

    this._state = {
      timestamp: t,
      controller: frame.controller,
      orientation: { quaternion: q, euler: qToEuler(q) },
      angularVelocity: { x: gyroF[0], y: gyroF[1], z: gyroF[2] },
      linearAcceleration: { x: linAccelHP[0], y: linAccelHP[1], z: linAccelHP[2] },
      motionSpeed,
      gesture: attachedGesture,
    };
    this.dispatchEvent(new CustomEvent("motion", { detail: this._state }));
    return this._state;
  }

  /** Convenience: subscribe an InputProvider directly. */
  attach(provider) {
    this._onFrame = (e) => this.feed(e.detail);
    provider.addEventListener("frame", this._onFrame);
    return () => provider.removeEventListener("frame", this._onFrame);
  }
}
