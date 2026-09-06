// web/src/playground/imu-viz.js
// Rolling oscilloscope for gyro (rad/s) and accel (g), plus a motion-speed meter.
// Fed a MotionState snapshot each animation frame; keeps its own ring buffers.

const COLORS = { x: "#f2637e", y: "#57c98a", z: "#6ea8fe" };

export class ImuViz {
  constructor(canvas, { seconds = 6, gyroRange = 12, accelRange = 2 } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.seconds = seconds;
    this.gyroRange = gyroRange;
    this.accelRange = accelRange;
    this.buf = []; // { t, g:{x,y,z}, a:{x,y,z}, speed }
    this._resize();
    window.addEventListener("resize", () => this._resize());
  }

  _resize() {
    const dpr = window.devicePixelRatio || 1;
    const w = this.canvas.clientWidth || 720;
    const h = this.canvas.clientHeight || 320;
    this.canvas.width = w * dpr;
    this.canvas.height = h * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.w = w;
    this.h = h;
  }

  push(state) {
    const t = state.timestamp;
    this.buf.push({
      t,
      g: { ...state.angularVelocity },
      a: { ...state.linearAcceleration },
      speed: state.motionSpeed,
    });
    const cutoff = t - this.seconds;
    while (this.buf.length && this.buf[0].t < cutoff) this.buf.shift();
  }

  draw() {
    const { ctx, w, h } = this;
    ctx.clearRect(0, 0, w, h);
    if (this.buf.length < 2) return;

    const t1 = this.buf[this.buf.length - 1].t;
    const t0 = t1 - this.seconds;
    const meterH = 26;
    const gap = 10;
    const scopeH = (h - meterH - gap * 2) / 2;

    this._scope(0, scopeH, "GYRO  rad/s", this.gyroRange, (d) => d.g);
    this._scope(scopeH + gap, scopeH, "ACCEL  g (gravity removed)", this.accelRange, (d) => d.a);
    this._meter(h - meterH, meterH, this.buf[this.buf.length - 1].speed);

    // time cursor helpers
    void t0;
  }

  _scope(y, height, title, range, pick) {
    const { ctx, w } = this;
    const t1 = this.buf[this.buf.length - 1].t;
    const t0 = t1 - this.seconds;
    const midY = y + height / 2;

    ctx.fillStyle = "#0a0d13";
    ctx.fillRect(0, y, w, height);
    ctx.strokeStyle = "#2b3446";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, midY);
    ctx.lineTo(w, midY);
    ctx.stroke();

    ctx.fillStyle = "#8b93a7";
    ctx.font = "11px ui-monospace, monospace";
    ctx.fillText(`${title}   ±${range}`, 8, y + 14);

    for (const axis of ["x", "y", "z"]) {
      ctx.strokeStyle = COLORS[axis];
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      let started = false;
      for (const d of this.buf) {
        const px = ((d.t - t0) / this.seconds) * w;
        const val = Math.max(-range, Math.min(range, pick(d)[axis]));
        const py = midY - (val / range) * (height / 2 - 4);
        if (!started) {
          ctx.moveTo(px, py);
          started = true;
        } else ctx.lineTo(px, py);
      }
      ctx.stroke();
    }

    // legend
    let lx = w - 92;
    for (const axis of ["x", "y", "z"]) {
      ctx.fillStyle = COLORS[axis];
      ctx.fillText(axis.toUpperCase(), lx, y + 14);
      lx += 28;
    }
  }

  _meter(y, height, speed) {
    const { ctx, w } = this;
    ctx.fillStyle = "#0a0d13";
    ctx.fillRect(0, y, w, height);
    const frac = Math.max(0, Math.min(1, speed));
    const grad = ctx.createLinearGradient(0, 0, w, 0);
    grad.addColorStop(0, "#4fd6be");
    grad.addColorStop(0.7, "#6ea8fe");
    grad.addColorStop(1, "#f2637e");
    ctx.fillStyle = grad;
    ctx.fillRect(0, y + 6, frac * w, height - 12);
    ctx.fillStyle = "#8b93a7";
    ctx.font = "11px ui-monospace, monospace";
    ctx.fillText(`MOTION SPEED  ${speed.toFixed(2)}`, 8, y + height - 8);
  }
}
