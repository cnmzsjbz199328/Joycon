// web/src/motion/quaternion.js
// Minimal quaternion helpers. Order [w, x, y, z]. Framework-free on purpose
// (docs/ARCHITECTURE.md §4: the Motion Engine must not depend on three.js).

export function qIdentity() {
  return [1, 0, 0, 0];
}

export function qNormalize(q) {
  const n = Math.hypot(q[0], q[1], q[2], q[3]) || 1;
  return [q[0] / n, q[1] / n, q[2] / n, q[3] / n];
}

export function qMul(a, b) {
  const [aw, ax, ay, az] = a;
  const [bw, bx, by, bz] = b;
  return [
    aw * bw - ax * bx - ay * by - az * bz,
    aw * bx + ax * bw + ay * bz - az * by,
    aw * by - ax * bz + ay * bw + az * bx,
    aw * bz + ax * by - ay * bx + az * bw,
  ];
}

/** Integrate a body-frame angular velocity (rad/s) over dt into q. */
export function qIntegrate(q, omega, dt) {
  const [wx, wy, wz] = omega;
  // dq = q * 0.5 * (0, wx, wy, wz) * dt   -> first order, then renormalize
  const dq = qMul(q, [0, wx * 0.5 * dt, wy * 0.5 * dt, wz * 0.5 * dt]);
  return qNormalize([q[0] + dq[0], q[1] + dq[1], q[2] + dq[2], q[3] + dq[3]]);
}

/** Rotate vector v by quaternion q. */
export function qRotate(q, v) {
  const [w, x, y, z] = q;
  const [vx, vy, vz] = v;
  // t = 2 * cross(q.xyz, v)
  const tx = 2 * (y * vz - z * vy);
  const ty = 2 * (z * vx - x * vz);
  const tz = 2 * (x * vy - y * vx);
  return [
    vx + w * tx + (y * tz - z * ty),
    vy + w * ty + (z * tx - x * tz),
    vz + w * tz + (x * ty - y * tx),
  ];
}

export function qConjugate(q) {
  return [q[0], -q[1], -q[2], -q[3]];
}

/** Shortest-arc quaternion rotating unit vector a onto unit vector b. */
export function qBetween(a, b) {
  const d = a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  if (d > 0.999999) return qIdentity();
  if (d < -0.999999) {
    // 180 deg: pick any orthogonal axis
    let ax = [1, 0, 0];
    if (Math.abs(a[0]) > 0.9) ax = [0, 1, 0];
    const c = [
      a[1] * ax[2] - a[2] * ax[1],
      a[2] * ax[0] - a[0] * ax[2],
      a[0] * ax[1] - a[1] * ax[0],
    ];
    return qNormalize([0, c[0], c[1], c[2]]);
  }
  const c = [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
  return qNormalize([1 + d, c[0], c[1], c[2]]);
}

export function qSlerpShort(q, target, t) {
  let dot = q[0] * target[0] + q[1] * target[1] + q[2] * target[2] + q[3] * target[3];
  let tgt = target;
  if (dot < 0) {
    tgt = [-target[0], -target[1], -target[2], -target[3]];
    dot = -dot;
  }
  if (dot > 0.9995) {
    return qNormalize([
      q[0] + t * (tgt[0] - q[0]),
      q[1] + t * (tgt[1] - q[1]),
      q[2] + t * (tgt[2] - q[2]),
      q[3] + t * (tgt[3] - q[3]),
    ]);
  }
  const theta0 = Math.acos(dot);
  const theta = theta0 * t;
  const s0 = Math.cos(theta) - (dot * Math.sin(theta)) / Math.sin(theta0);
  const s1 = Math.sin(theta) / Math.sin(theta0);
  return qNormalize([
    s0 * q[0] + s1 * tgt[0],
    s0 * q[1] + s1 * tgt[1],
    s0 * q[2] + s1 * tgt[2],
    s0 * q[3] + s1 * tgt[3],
  ]);
}

export function qToEuler(q) {
  const [w, x, y, z] = q;
  // roll (x), pitch (y), yaw (z) -- aerospace-ish ZYX
  const sinr = 2 * (w * x + y * z);
  const cosr = 1 - 2 * (x * x + y * y);
  const roll = Math.atan2(sinr, cosr);

  const sinp = 2 * (w * y - z * x);
  const pitch = Math.abs(sinp) >= 1 ? Math.sign(sinp) * (Math.PI / 2) : Math.asin(sinp);

  const siny = 2 * (w * z + x * y);
  const cosy = 1 - 2 * (y * y + z * z);
  const yaw = Math.atan2(siny, cosy);
  return { roll, pitch, yaw };
}
