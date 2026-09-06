// web/src/motion/filters.js
// Low-latency building blocks. See docs/MOTION_ENGINE.md for the algorithm
// comparison and why complementary (not Madgwick/VQF) is the default.

/** One-pole exponential moving average, cutoff-frequency parameterised. */
export class LowPass {
  constructor(cutoffHz = 8, dim = 3) {
    this.cutoffHz = cutoffHz;
    this.value = new Array(dim).fill(0);
    this._init = false;
  }

  /** @param {number[]} x  @param {number} dt seconds */
  update(x, dt) {
    if (!this._init) {
      this.value = x.slice();
      this._init = true;
      return this.value;
    }
    const rc = 1 / (2 * Math.PI * this.cutoffHz);
    const a = dt / (rc + dt); // 0..1
    for (let i = 0; i < x.length; i++) {
      this.value[i] += a * (x[i] - this.value[i]);
    }
    return this.value;
  }

  reset() {
    this._init = false;
    this.value = this.value.map(() => 0);
  }
}

/** High-pass = signal - low-pass. Used to isolate transient (slash) accel. */
export class HighPass {
  constructor(cutoffHz = 1.5, dim = 3) {
    this.lp = new LowPass(cutoffHz, dim);
    this.value = new Array(dim).fill(0);
  }

  update(x, dt) {
    const lp = this.lp.update(x, dt);
    this.value = x.map((v, i) => v - lp[i]);
    return this.value;
  }

  reset() {
    this.lp.reset();
    this.value = this.value.map(() => 0);
  }
}

/** Scalar dead zone with smooth re-entry (no discontinuity at the edge). */
export function deadZone(v, threshold) {
  const a = Math.abs(v);
  if (a <= threshold) return 0;
  return Math.sign(v) * (a - threshold);
}

/** Sliding-window ring buffer of {t, ...} samples, trimmed to a time span. */
export class Window {
  constructor(spanSeconds = 0.35) {
    this.span = spanSeconds;
    this.items = [];
  }

  push(item) {
    this.items.push(item);
    const cutoff = item.t - this.span;
    while (this.items.length && this.items[0].t < cutoff) this.items.shift();
  }

  clear() {
    this.items = [];
  }

  get length() {
    return this.items.length;
  }
}
