// web/src/game/entities.js
// Fruit / Bomb entities + spawning + parabolic physics for Motion Fruit Slash.

export const FRUITS = {
  watermelon: { r: 42, color: "#3fae5a", core: "#e8506b", score: 3, juice: "#e8506b" },
  orange: { r: 30, color: "#e8912b", core: "#ffbd6b", score: 2, juice: "#ffb15c" },
  apple: { r: 28, color: "#e14b5a", core: "#f7e7c8", score: 2, juice: "#f2a6b0" },
  banana: { r: 34, color: "#f2c744", core: "#fff2c2", score: 1, juice: "#ffe680" },
};

const FRUIT_KEYS = Object.keys(FRUITS);
let _id = 1;

export class Entity {
  constructor(x, y, vx, vy, kind) {
    this.id = _id++;
    this.x = x;
    this.y = y;
    this.vx = vx;
    this.vy = vy;
    this.kind = kind; // "watermelon" | ... | "bomb"
    this.isBomb = kind === "bomb";
    this.spec = this.isBomb
      ? { r: 30, color: "#2b2f38", core: "#f2637e", score: -5, juice: "#ff8a3d" }
      : FRUITS[kind];
    this.r = this.spec.r;
    this.angle = Math.random() * Math.PI * 2;
    this.spin = (Math.random() - 0.5) * 6;
    this.sliced = false;
    this.dead = false;
    this.t = 0;
  }

  update(dt, gravity, floorY) {
    this.t += dt;
    this.vy += gravity * dt;
    this.x += this.vx * dt;
    this.y += this.vy * dt;
    this.angle += this.spin * dt;
    if (this.y - this.r > floorY + 80) this.dead = true;
  }
}

export class Spawner {
  constructor(width, height, opts = {}) {
    this.w = width;
    this.h = height;
    this.next = 0;
    this.minGap = opts.minGap ?? 0.55;
    this.maxGap = opts.maxGap ?? 1.15;
    this.bombChance = opts.bombChance ?? 0.16;
    this.gravity = opts.gravity ?? 1400;
  }

  resize(w, h) {
    this.w = w;
    this.h = h;
  }

  /** @returns {Entity[]} zero or more new entities this tick */
  update(dt, elapsed) {
    this.next -= dt;
    if (this.next > 0) return [];
    this.next = this.minGap + Math.random() * (this.maxGap - this.minGap);

    const burst = Math.random() < 0.25 ? 2 + ((Math.random() * 2) | 0) : 1;
    const out = [];
    for (let i = 0; i < burst; i++) {
      const fromLeftHalf = Math.random() < 0.5;
      const x = fromLeftHalf
        ? this.w * (0.12 + Math.random() * 0.33)
        : this.w * (0.55 + Math.random() * 0.33);
      const y = this.h + 40;
      const apex = this.h * (0.16 + Math.random() * 0.28);
      // vy so that it just reaches apex: v^2 = 2 g (h - apex)
      const vy = -Math.sqrt(2 * this.gravity * (this.h - apex));
      const vx = (this.w / 2 - x) * (0.35 + Math.random() * 0.5);
      const kind =
        Math.random() < this.bombChance
          ? "bomb"
          : FRUIT_KEYS[(Math.random() * FRUIT_KEYS.length) | 0];
      out.push(new Entity(x, y, vx, vy, kind));
    }
    void elapsed;
    return out;
  }
}

/** Distance from point P to segment AB. */
export function segPointDist(ax, ay, bx, by, px, py) {
  const dx = bx - ax;
  const dy = by - ay;
  const len2 = dx * dx + dy * dy || 1e-9;
  let t = ((px - ax) * dx + (py - ay) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  const cx = ax + t * dx;
  const cy = ay + t * dy;
  return Math.hypot(px - cx, py - cy);
}
