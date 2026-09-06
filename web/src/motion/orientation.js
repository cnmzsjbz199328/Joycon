// web/src/motion/orientation.js
// Complementary filter: integrate the gyro every frame for low-latency response,
// then nudge the estimate's "up" axis back toward the measured gravity direction
// by a small factor so tilt (pitch/roll) does not drift. Yaw still drifts (no
// magnetometer used) -- acceptable for a slashing game.
//
// A Madgwick option is included for comparison (docs/MOTION_ENGINE.md §10) but is
// off by default.

import {
  qIdentity,
  qIntegrate,
  qRotate,
  qBetween,
  qMul,
  qSlerpShort,
  qNormalize,
  qToEuler,
} from "./quaternion.js";

export class ComplementaryOrientation {
  /**
   * @param {object} opts
   * @param {number} opts.accelGain   0..1 correction per second toward gravity (default 0.02)
   * @param {number} opts.accelTrustBand  g-magnitude window where accel is trusted
   */
  constructor(opts = {}) {
    this.q = qIdentity();
    this.accelGain = opts.accelGain ?? 0.02;
    this.trust = opts.accelTrustBand ?? 0.15; // trust accel when 0.85g..1.15g
    this._ref = [0, 0, 1]; // world "up" in our convention
  }

  reset(q = qIdentity()) {
    this.q = q.slice();
  }

  /**
   * @param {[number,number,number]} gyro  rad/s, body frame
   * @param {[number,number,number]} accel g, body frame
   * @param {number} dt seconds
   */
  update(gyro, accel, dt) {
    // 1. gyro integration (the fast path)
    this.q = qIntegrate(this.q, gyro, dt);

    // 2. gravity correction (the slow path)
    const mag = Math.hypot(accel[0], accel[1], accel[2]);
    if (mag > 1e-3 && Math.abs(mag - 1) < this.trust) {
      const aBody = [accel[0] / mag, accel[1] / mag, accel[2] / mag];
      // where the estimate thinks "up" is, in body frame:
      const upBody = qRotate(qConj(this.q), this._ref);
      // rotation that would align estimate-up with measured gravity:
      const corr = qBetween(upBody, aBody);
      // apply only a fraction, frame-rate independent
      const t = 1 - Math.pow(1 - this.accelGain, dt * 60);
      const small = qSlerpShort(qIdentity(), corr, t);
      this.q = qNormalize(qMul(this.q, small));
    }
    return this.q;
  }

  get euler() {
    return qToEuler(this.q);
  }
}

function qConj(q) {
  return [q[0], -q[1], -q[2], -q[3]];
}

/** Madgwick IMU (no mag). Kept for the comparison in MOTION_ENGINE.md. */
export class MadgwickOrientation {
  constructor(opts = {}) {
    this.q = qIdentity();
    this.beta = opts.beta ?? 0.08;
  }

  reset(q = qIdentity()) {
    this.q = q.slice();
  }

  update(gyro, accel, dt) {
    let [q0, q1, q2, q3] = this.q;
    let [gx, gy, gz] = gyro;
    let [ax, ay, az] = accel;

    const norm = Math.hypot(ax, ay, az);
    if (norm > 1e-6) {
      ax /= norm; ay /= norm; az /= norm;

      const f1 = 2 * (q1 * q3 - q0 * q2) - ax;
      const f2 = 2 * (q0 * q1 + q2 * q3) - ay;
      const f3 = 2 * (0.5 - q1 * q1 - q2 * q2) - az;

      const J11 = -2 * q2, J12 = 2 * q3, J13 = -2 * q0, J14 = 2 * q1;
      const J21 = 2 * q1, J22 = 2 * q0, J23 = 2 * q3, J24 = 2 * q2;
      const J31 = 0, J32 = -4 * q1, J33 = -4 * q2, J34 = 0;

      let s0 = J11 * f1 + J21 * f2 + J31 * f3;
      let s1 = J12 * f1 + J22 * f2 + J32 * f3;
      let s2 = J13 * f1 + J23 * f2 + J33 * f3;
      let s3 = J14 * f1 + J24 * f2 + J34 * f3;
      const sn = Math.hypot(s0, s1, s2, s3) || 1;
      s0 /= sn; s1 /= sn; s2 /= sn; s3 /= sn;

      gx -= 0; // no bias term here
      const qDot0 = 0.5 * (-q1 * gx - q2 * gy - q3 * gz) - this.beta * s0;
      const qDot1 = 0.5 * (q0 * gx + q2 * gz - q3 * gy) - this.beta * s1;
      const qDot2 = 0.5 * (q0 * gy - q1 * gz + q3 * gx) - this.beta * s2;
      const qDot3 = 0.5 * (q0 * gz + q1 * gy - q2 * gx) - this.beta * s3;

      q0 += qDot0 * dt; q1 += qDot1 * dt; q2 += qDot2 * dt; q3 += qDot3 * dt;
    } else {
      q0 += 0.5 * (-q1 * gx - q2 * gy - q3 * gz) * dt;
      q1 += 0.5 * (q0 * gx + q2 * gz - q3 * gy) * dt;
      q2 += 0.5 * (q0 * gy - q1 * gz + q3 * gx) * dt;
      q3 += 0.5 * (q0 * gz + q1 * gy - q2 * gx) * dt;
    }
    this.q = qNormalize([q0, q1, q2, q3]);
    return this.q;
  }

  get euler() {
    return qToEuler(this.q);
  }
}
