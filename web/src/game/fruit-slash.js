// web/src/game/fruit-slash.js
// Motion Fruit Slash (GOAL.md Phase 7). Canvas 2D. No game over -- pure "feel".
//
// Motion mapping (game only touches MotionState + gesture, never raw IMU):
//   - blade tip on screen is driven by orientation (yaw -> x, pitch -> y)
//   - the trail becomes "hot" (slicing) when motionSpeed > SLASH_SPEED, or when a
//     SLASH_* / THRUST gesture fires (brief window)
//   - a hot trail segment crossing a fruit slices it (+score); a bomb costs score
//     and shakes the screen. Score never goes below 0.

import { Spawner, segPointDist } from "./entities.js";

const SLASH_SPEED = 0.42; // MotionState.motionSpeed threshold for the continuous hot trail
const GESTURE_HOT_S = 0.16;
const TRAIL_LEN = 14;
const STROKE_LIFE = 0.16; // seconds a gesture slash-stroke stays active

// screen-space travel direction per slash gesture
const STROKE_DIR = {
  SLASH_RIGHT: [1, 0],
  SLASH_LEFT: [-1, 0],
  SLASH_UP: [0, -1],
  SLASH_DOWN: [0, 1],
};

export class FruitSlash {
  constructor(canvas, opts = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this._resize();
    this.spawner = new Spawner(this.w, this.h, opts.spawn);
    this.entities = [];
    this.particles = [];
    this.blades = []; // fading slice marks
    this.strokes = []; // active gesture slash-strokes

    this.score = 0;
    this.combo = 0;
    this._comboUntil = 0;
    this.slices = 0;

    this.tip = { x: this.w / 2, y: this.h / 2 };
    this.trail = [];
    this._hotUntil = 0;
    this._shake = 0;
    this._elapsed = 0;
    this._lastMotion = null;

    this.onScore = opts.onScore ?? (() => {});
    window.addEventListener("resize", () => {
      this._resize();
      this.spawner.resize(this.w, this.h);
    });
  }

  _resize() {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = this.canvas.clientWidth || 720;
    const h = this.canvas.clientHeight || 520;
    this.canvas.width = w * dpr;
    this.canvas.height = h * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.w = w;
    this.h = h;
  }

  /** Called on every MotionEngine "motion" event. */
  onMotion(state) {
    this._lastMotion = state;
    const e = state.orientation.euler;
    // map orientation to screen; clamp. yaw ~ +/-0.9 rad -> full width
    const nx = clamp(-e.yaw / 0.9, -1, 1);
    const ny = clamp(-e.pitch / 0.7, -1, 1);
    this.tip.x = (0.5 + nx * 0.46) * this.w;
    this.tip.y = (0.5 + ny * 0.42) * this.h;

    if (state.motionSpeed > SLASH_SPEED) this._hotUntil = state.timestamp + 0.05;
  }

  /** Called on every MotionEngine "gesture" event. */
  onGesture(g) {
    const now = this._lastMotion?.timestamp ?? performance.now() / 1000;
    this._hotUntil = now + GESTURE_HOT_S;

    const dir = STROKE_DIR[g.gesture];
    if (dir) {
      // A Fruit-Ninja-style swipe: a cut line through the current reticle,
      // perpendicular to travel, sweeping across the field. Band widens with
      // gesture strength so a firm swing is forgiving.
      this.strokes.push({
        x: this.tip.x,
        y: this.tip.y,
        dir,
        band: 46 + 150 * g.strength,
        t: 0,
        strength: g.strength,
      });
    } else if (g.gesture === "THRUST") {
      // point stab: slice fruit near the reticle
      for (const ent of this.entities) {
        if (!ent.sliced && Math.hypot(ent.x - this.tip.x, ent.y - this.tip.y) <= ent.r + 40) {
          this._slice(ent, 0, -1);
        }
      }
    }
  }

  get hot() {
    const now = this._lastMotion?.timestamp ?? 0;
    return now <= this._hotUntil;
  }

  /** Fixed-step-ish game update. dt seconds. */
  update(dt) {
    this._elapsed += dt;
    // spawn + physics
    for (const ent of this.spawner.update(dt, this._elapsed)) this.entities.push(ent);
    for (const ent of this.entities) ent.update(dt, this.spawner.gravity, this.h);

    // trail
    this.trail.push({ x: this.tip.x, y: this.tip.y, hot: this.hot });
    if (this.trail.length > TRAIL_LEN) this.trail.shift();

    // gesture slash-strokes: a horizontal/vertical cut band through the reticle
    for (const st of this.strokes) {
      st.t += dt;
      for (const ent of this.entities) {
        if (ent.sliced) continue;
        const horizontal = st.dir[0] !== 0;
        const off = horizontal ? Math.abs(ent.y - st.y) : Math.abs(ent.x - st.x);
        if (off <= st.band + ent.r) this._slice(ent, st.dir[0], st.dir[1]);
      }
    }
    this.strokes = this.strokes.filter((s) => s.t < STROKE_LIFE);

    // continuous slicing: test the most recent hot trail segment against each entity
    if (this.trail.length >= 2 && this.hot) {
      const a = this.trail[this.trail.length - 2];
      const b = this.trail[this.trail.length - 1];
      const moved = Math.hypot(b.x - a.x, b.y - a.y);
      if (moved > 3) {
        for (const ent of this.entities) {
          if (ent.sliced) continue;
          if (segPointDist(a.x, a.y, b.x, b.y, ent.x, ent.y) <= ent.r) {
            this._slice(ent, b.x - a.x, b.y - a.y);
          }
        }
      }
    }

    // combo decay
    if (this._elapsed > this._comboUntil) this.combo = 0;

    // particles / blades
    for (const p of this.particles) {
      p.t += dt;
      p.vy += 900 * dt;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
    }
    this.particles = this.particles.filter((p) => p.t < p.life);
    for (const bl of this.blades) bl.t += dt;
    this.blades = this.blades.filter((bl) => bl.t < 0.25);

    this.entities = this.entities.filter((e) => !e.dead);
    if (this._shake > 0) this._shake = Math.max(0, this._shake - dt * 60);
  }

  _slice(ent, dirx, diry) {
    ent.sliced = true;
    ent.dead = true;
    this.slices++;
    const len = Math.hypot(dirx, diry) || 1;
    this.blades.push({ x: ent.x, y: ent.y, dx: dirx / len, dy: diry / len, t: 0, color: ent.spec.juice });

    if (ent.isBomb) {
      this.score = Math.max(0, this.score - 5);
      this.combo = 0;
      this._shake = 16;
      this._burst(ent, 26, "#ff8a3d");
    } else {
      this.combo++;
      this._comboUntil = this._elapsed + 1.4;
      const gain = ent.spec.score * (1 + Math.floor(this.combo / 3));
      this.score += gain;
      this._burst(ent, 16, ent.spec.juice);
    }
    this.onScore({ score: this.score, combo: this.combo, slices: this.slices, bomb: ent.isBomb });
  }

  _burst(ent, n, color) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2;
      const sp = 60 + Math.random() * 320;
      this.particles.push({
        x: ent.x, y: ent.y,
        vx: Math.cos(a) * sp, vy: Math.sin(a) * sp - 120,
        t: 0, life: 0.4 + Math.random() * 0.5, color, r: 2 + Math.random() * 4,
      });
    }
  }

  render() {
    const { ctx, w, h } = this;
    ctx.save();
    if (this._shake > 0) {
      ctx.translate((Math.random() - 0.5) * this._shake, (Math.random() - 0.5) * this._shake);
    }
    // bg
    const grd = ctx.createLinearGradient(0, 0, 0, h);
    grd.addColorStop(0, "#141a26");
    grd.addColorStop(1, "#0a0d13");
    ctx.fillStyle = grd;
    ctx.fillRect(-40, -40, w + 80, h + 80);

    // entities
    for (const ent of this.entities) this._drawEntity(ent);

    // gesture slash-strokes
    for (const st of this.strokes) {
      const k = 1 - st.t / STROKE_LIFE;
      const horizontal = st.dir[0] !== 0;
      ctx.strokeStyle = `rgba(79,214,190,${0.5 * k})`;
      ctx.lineWidth = st.band * 0.5 * (0.5 + 0.5 * k);
      ctx.lineCap = "round";
      ctx.beginPath();
      if (horizontal) {
        ctx.moveTo(0, st.y);
        ctx.lineTo(w, st.y);
      } else {
        ctx.moveTo(st.x, 0);
        ctx.lineTo(st.x, h);
      }
      ctx.stroke();
    }

    // blades (slice marks)
    for (const bl of this.blades) {
      const k = 1 - bl.t / 0.25;
      ctx.strokeStyle = hexA(bl.color, k);
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(bl.x - bl.dx * 60, bl.y - bl.dy * 60);
      ctx.lineTo(bl.x + bl.dx * 60, bl.y + bl.dy * 60);
      ctx.stroke();
    }

    // particles
    for (const p of this.particles) {
      ctx.globalAlpha = Math.max(0, 1 - p.t / p.life);
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    this._drawTrail();
    this._drawReticle();
    ctx.restore();
  }

  _drawEntity(ent) {
    const { ctx } = this;
    ctx.save();
    ctx.translate(ent.x, ent.y);
    ctx.rotate(ent.angle);
    if (ent.isBomb) {
      ctx.fillStyle = ent.spec.color;
      ctx.beginPath();
      ctx.arc(0, 0, ent.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = ent.spec.core;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(0, -ent.r);
      ctx.lineTo(0, -ent.r - 10);
      ctx.stroke();
      ctx.fillStyle = "#f2637e";
      ctx.font = "bold 18px system-ui";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("!", 0, 1);
    } else {
      ctx.fillStyle = ent.spec.color;
      ctx.beginPath();
      ctx.arc(0, 0, ent.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = hexA(ent.spec.core, 0.9);
      ctx.beginPath();
      ctx.arc(-ent.r * 0.28, -ent.r * 0.28, ent.r * 0.42, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  _drawTrail() {
    const { ctx } = this;
    if (this.trail.length < 2) return;
    for (let i = 1; i < this.trail.length; i++) {
      const a = this.trail[i - 1];
      const b = this.trail[i];
      const k = i / this.trail.length;
      ctx.strokeStyle = b.hot ? `rgba(79,214,190,${k * 0.9})` : `rgba(110,168,254,${k * 0.25})`;
      ctx.lineWidth = (b.hot ? 10 : 3) * k + 1;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
  }

  _drawReticle() {
    const { ctx } = this;
    ctx.strokeStyle = this.hot ? "#4fd6be" : "#6ea8fe";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(this.tip.x, this.tip.y, this.hot ? 10 : 6, 0, Math.PI * 2);
    ctx.stroke();
  }
}

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}
function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r},${g},${b},${Math.max(0, Math.min(1, a))})`;
}
