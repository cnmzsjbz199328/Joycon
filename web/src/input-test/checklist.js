// web/src/input-test/checklist.js
// Guided hardware acceptance run for buttons + sticks. Each step tells the
// person one physical action, watches the public input stream (JoyCon2Input
// events) and decides pass / fail / info on its own. Every step start and end
// is sent to the adapter as a `mark`, so a `--record` capture carries the
// action labels next to the raw packets.
//
// Pure logic, no DOM: web/test/checklist.test.js drives it with synthetic events.

import { BUTTONS_LEFT, BUTTONS_RIGHT } from "../../../shared/protocol/contracts.mjs";

export const BUTTON_LABELS = {
  left: {
    up: "D-pad ↑", down: "D-pad ↓", left: "D-pad ←", right: "D-pad →",
    l: "L (shoulder)", zl: "ZL (trigger)", sl: "SL (rail button labelled SL)", sr: "SR (rail button labelled SR)",
    minus: "− Minus", capture: "Capture (square button)", stick: "stick click (press the stick in)",
  },
  right: {
    a: "A", b: "B", x: "X", y: "Y", r: "R (shoulder)", zr: "ZR (trigger)",
    sl: "SL (rail button labelled SL)", sr: "SR (rail button labelled SR)",
    plus: "+ Plus", home: "Home", c: "C (below Home)", stick: "stick click (press the stick in)",
  },
};

const SIDE = { left: "LEFT", right: "RIGHT" };
const key = (side, b) => `${side}.${b}`;
const anyPressed = (input) =>
  Object.values(input.devices).some((d) => Object.values(d.buttons).some(Boolean));
const pressedKeys = (input) =>
  Object.values(input.devices).flatMap((d) =>
    Object.entries(d.buttons).filter(([, v]) => v).map(([b]) => key(d.controller, b)));
const radius = (input, side) => {
  const s = input.device(side)?.stick ?? { x: 0, y: 0 };
  return Math.hypot(s.x, s.y);
};
const rawOf = (input, side) => input.device(side)?.stickRaw ?? null;

// --- step kinds --------------------------------------------------------------
// A step: { id, section, title, detail, expect, timeoutMs, onEvent(type, d, ctx), onTick(ctx) }.
// Handlers return a result { pass: true|false|null, observed, info } to finish.

function single(side, button) {
  const want = key(side, button);
  return {
    id: `btn-${side}-${button}`, section: "Buttons", expect: { press: [want] },
    title: `${SIDE[side]}: press and release ${BUTTON_LABELS[side][button]}`,
    detail: "Only that button. The step checks which bit actually lit up.",
    onEvent(type, d, ctx) {
      if (type === "press") (ctx.s.seen ??= new Set()).add(key(d.controller, d.button));
      if (type === "release" && ctx.s.seen && !anyPressed(ctx.input)) {
        const seen = [...ctx.s.seen];
        return { pass: seen.length === 1 && seen[0] === want, observed: seen };
      }
      return null;
    },
  };
}

function chord(id, title, keys, detail = "Press them together, then let go.") {
  return {
    id, section: "Combos", title, detail, expect: { together: keys }, timeoutMs: 20000,
    onEvent(type, _d, ctx) {
      const now = pressedKeys(ctx.input);
      ctx.s.extra ??= new Set();
      for (const k of now) if (!keys.includes(k)) ctx.s.extra.add(k);
      if (keys.every((k) => now.includes(k))) ctx.s.full = true;
      if (type === "release" && !anyPressed(ctx.input) && ctx.s.full) {
        const extras = [...ctx.s.extra];
        return { pass: extras.length === 0, observed: extras.length ? { unexpected: extras } : "all held together, all released" };
      }
      return null;
    },
  };
}

function releaseOrder(side, hold, first, holdMs = 1000) {
  const h = key(side, hold), f = key(side, first);
  return {
    id: `order-${side}-${hold}-${first}`, section: "Combos", expect: { hold: h, releaseFirst: f, holdMs },
    title: `${SIDE[side]}: hold ${BUTTON_LABELS[side][hold]} + ${BUTTON_LABELS[side][first]}; let go of ${BUTTON_LABELS[side][first]} only, keep ${BUTTON_LABELS[side][hold]} held ${holdMs / 1000} s, then let go`,
    detail: "Checks that releasing one button does not release the other.", timeoutMs: 30000,
    onEvent(type, d, ctx) {
      const k = key(d.controller, d.button);
      const p = pressedKeys(ctx.input);
      if (type === "press" && p.includes(h) && p.includes(f)) ctx.s.both = true;
      if (type === "release" && ctx.s.both && k === f && !ctx.s.firstAt) {
        if (!ctx.input.isPressed(side, hold)) return { pass: false, observed: `${hold} was released together with ${first}` };
        ctx.s.firstAt = ctx.now();
      }
      if (type === "release" && k === h && ctx.s.both) {
        if (!ctx.s.firstAt) return { pass: false, observed: `${hold} released before ${first}` };
        const held = ctx.now() - ctx.s.firstAt;
        return { pass: held >= holdMs - 50, observed: { heldAloneMs: Math.round(held), reason: d.reason } };
      }
      return null;
    },
  };
}

function hold(side, button, ms) {
  const k = key(side, button);
  return {
    id: `hold-${side}-${button}`, section: "Combos", expect: { hold: k, ms },
    title: `${SIDE[side]}: hold ${BUTTON_LABELS[side][button]} for ${ms / 1000} s, then let go`,
    detail: "One press event, no flicker, one release.", timeoutMs: 30000,
    onEvent(type, d, ctx) {
      if (key(d.controller, d.button) !== k) return null;
      if (type === "press") { ctx.s.at = ctx.now(); ctx.s.presses = (ctx.s.presses ?? 0) + 1; }
      if (type === "release" && ctx.s.at != null) {
        const held = ctx.now() - ctx.s.at;
        if (held < ms - 50) { ctx.s.short = (ctx.s.short ?? 0) + 1; return null; } // too short, try again
        return { pass: true, observed: { heldMs: Math.round(held), shortAttempts: ctx.s.short ?? 0 } };
      }
      return null;
    },
  };
}

function imuFree(side, button) {
  return {
    id: `imu-free-${side}`, section: "No IMU calibration", expect: { press: [key(side, button)], imuReady: false },
    title: `${SIDE[side]}: keep the Joy-Con moving in your hand and press ${BUTTON_LABELS[side][button]} a few times`,
    detail: "Buttons must work while the IMU calibration has not run (it only completes when the controller is still).",
    timeoutMs: 30000,
    onEvent(type, d, ctx) {
      if (type !== "press" || d.controller !== side || d.button !== button) return null;
      const ready = ctx.input.device(side).imuReady;
      return ready
        ? { pass: null, observed: "IMU was already calibrated — inconclusive (restart the adapter while holding the controller to retest)" }
        : { pass: true, observed: "press delivered while imuReady=false" };
    },
  };
}

function stickRest(side, ms = 2000) {
  return {
    id: `stick-${side}-rest`, section: "Sticks", expect: { stick: "0,0" },
    title: `${SIDE[side]} stick: hands off for ${ms / 1000} s`,
    detail: "Must read exactly 0,0 at rest (dead zone covers the rest offset).",
    onTick(ctx) {
      if (ctx.elapsed() < 500) return null; // time to let go
      const r = radius(ctx.input, side);
      const raw = rawOf(ctx.input, side);
      ctx.s.maxR = Math.max(ctx.s.maxR ?? 0, r);
      if (raw) {
        ctx.s.raw ??= { minX: raw.x, maxX: raw.x, minY: raw.y, maxY: raw.y };
        Object.assign(ctx.s.raw, { minX: Math.min(ctx.s.raw.minX, raw.x), maxX: Math.max(ctx.s.raw.maxX, raw.x), minY: Math.min(ctx.s.raw.minY, raw.y), maxY: Math.max(ctx.s.raw.maxY, raw.y) });
      }
      if (ctx.elapsed() < 500 + ms) return null;
      return { pass: ctx.s.maxR === 0, observed: { maxRadius: +ctx.s.maxR.toFixed(3), raw: ctx.s.raw ?? null } };
    },
  };
}

const DIRS = {
  up: { label: "fully UP", ok: (x, y) => y >= 0.95 && Math.abs(x) <= 0.35, along: (x, y) => y },
  down: { label: "fully DOWN", ok: (x, y) => y <= -0.95 && Math.abs(x) <= 0.35, along: (x, y) => -y },
  left: { label: "fully LEFT", ok: (x, y) => x <= -0.95 && Math.abs(y) <= 0.35, along: (x) => -x },
  right: { label: "fully RIGHT", ok: (x, y) => x >= 0.95 && Math.abs(y) <= 0.35, along: (x) => x },
};

function stickDir(side, dir) {
  const D = DIRS[dir];
  return {
    id: `stick-${side}-${dir}`, section: "Sticks", expect: { stick: dir, min: 0.95 },
    title: `${SIDE[side]} stick: push ${D.label} and hold until ✓`,
    detail: "Also checks the sign: up = +y, right = +x.", timeoutMs: 15000,
    onTick(ctx) {
      const s = ctx.input.device(side)?.stick ?? { x: 0, y: 0 };
      const along = D.along(s.x, s.y);
      if (along > (ctx.s.peak ?? -2)) { ctx.s.peak = along; ctx.s.peakAt = { ...s, raw: rawOf(ctx.input, side) }; }
      if (D.ok(s.x, s.y)) {
        ctx.s.okSince ??= ctx.now();
        if (ctx.now() - ctx.s.okSince >= 500) return { pass: true, observed: { stick: s, raw: rawOf(ctx.input, side) } };
      } else ctx.s.okSince = null;
      return null;
    },
    onTimeout: (ctx) => ({ pass: false, observed: { peak: ctx.s.peak ?? null, at: ctx.s.peakAt ?? null } }),
  };
}

function stickCircle(side) {
  return {
    id: `stick-${side}-circle`, section: "Sticks", expect: { everySector: 0.95 },
    title: `${SIDE[side]} stick: roll it slowly around the outer edge, 2–3 full circles`,
    detail: "All 8 directions, diagonals included, must reach the edge (≥ 0.95).", timeoutMs: 25000,
    onTick(ctx) {
      const s = ctx.input.device(side)?.stick ?? { x: 0, y: 0 };
      const raw = rawOf(ctx.input, side);
      const r = Math.hypot(s.x, s.y);
      ctx.s.sectors ??= Array(8).fill(0);
      if (r > 0.3) {
        const i = ((Math.round(Math.atan2(s.y, s.x) / (Math.PI / 4)) % 8) + 8) % 8;
        ctx.s.sectors[i] = Math.max(ctx.s.sectors[i], r);
      }
      if (raw) {
        ctx.s.raw ??= { minX: raw.x, maxX: raw.x, minY: raw.y, maxY: raw.y };
        Object.assign(ctx.s.raw, { minX: Math.min(ctx.s.raw.minX, raw.x), maxX: Math.max(ctx.s.raw.maxX, raw.x), minY: Math.min(ctx.s.raw.minY, raw.y), maxY: Math.max(ctx.s.raw.maxY, raw.y) });
      }
      if (ctx.s.sectors.every((v) => v >= 0.95) && ctx.elapsed() > 2000) {
        return { pass: true, observed: { sectors: ctx.s.sectors.map((v) => +v.toFixed(3)), raw: ctx.s.raw } };
      }
      return null;
    },
    onTimeout: (ctx) => ({ pass: false, observed: { sectors: (ctx.s.sectors ?? []).map((v) => +v.toFixed(3)), raw: ctx.s.raw ?? null } }),
  };
}

function stickClick(side) {
  return {
    id: `stick-${side}-click-deflected`, section: "Sticks", expect: { press: [key(side, "stick")], deflected: 0.8 },
    title: `${SIDE[side]} stick: push it to any edge AND click it in, hold 1 s, let go`,
    detail: "Stick click must register while the stick is deflected.", timeoutMs: 20000,
    onTick(ctx) {
      const r = radius(ctx.input, side);
      if (ctx.input.isPressed(side, "stick") && r >= 0.8) {
        ctx.s.since ??= ctx.now();
        if (ctx.now() - ctx.s.since >= 1000) ctx.s.ok = true;
      } else ctx.s.since = null;
      if (ctx.s.ok && !anyPressed(ctx.input)) return { pass: true, observed: "click held while deflected" };
      return null;
    },
  };
}

function bothSticks() {
  return {
    id: "sticks-both", section: "Both controllers", expect: { both: 0.95 },
    title: "Push BOTH sticks fully (any direction) at the same time and hold until ✓",
    detail: "Left and right stick values must stay independent.", timeoutMs: 20000,
    onTick(ctx) {
      const ok = radius(ctx.input, "left") >= 0.95 && radius(ctx.input, "right") >= 0.95;
      if (ok) {
        ctx.s.since ??= ctx.now();
        if (ctx.now() - ctx.s.since >= 500) {
          return { pass: true, observed: { left: ctx.input.device("left").stick, right: ctx.input.device("right").stick } };
        }
      } else ctx.s.since = null;
      return null;
    },
  };
}

function alternate(n = 8) {
  const a = key("left", "down"), b = key("right", "a");
  return {
    id: "alternate-left-right", section: "Both controllers", expect: { [a]: n, [b]: n },
    title: `Tap LEFT D-pad ↓ and RIGHT A alternately, fast, about ${n + 2} times each`,
    detail: "Counts presses per controller; nothing else may light up.", timeoutMs: 30000,
    onEvent(type, d, ctx) {
      if (type !== "press") return null;
      const k = key(d.controller, d.button);
      ctx.s.n ??= {};
      ctx.s.n[k] = (ctx.s.n[k] ?? 0) + 1;
      if ((ctx.s.n[a] ?? 0) >= n && (ctx.s.n[b] ?? 0) >= n) {
        const others = Object.keys(ctx.s.n).filter((x) => x !== a && x !== b);
        return { pass: others.length === 0, observed: ctx.s.n };
      }
      return null;
    },
  };
}

function syncProbe(side, ms = 8000) {
  return {
    id: `sync-${side}`, section: "Sync / disconnect", expect: { info: "does Sync report as input? does it disconnect?" },
    title: `${SIDE[side]}: press the small Sync button once (short press), then wait`,
    detail: `Watches ${ms / 1000} s for any button bit or connection change. Informational.`,
    onEvent(type, d, ctx) {
      if (type === "press") (ctx.s.pressed ??= new Set()).add(key(d.controller, d.button));
      if (type === "device" && d.controller === side) (ctx.s.states ??= []).push(`${d.connection}${d.stale ? "/stale" : ""}`);
      return null;
    },
    onTick(ctx) {
      if (ctx.elapsed() < ms) return null;
      return { pass: null, observed: { buttonsSeen: [...(ctx.s.pressed ?? [])], connectionChanges: ctx.s.states ?? [] } };
    },
  };
}

function disconnectHeld(side, button) {
  const k = key(side, button);
  return {
    id: `disconnect-held-${side}`, section: "Sync / disconnect", expect: { release: k, reason: ["offline", "stale"] },
    title: `${SIDE[side]}: hold ${BUTTON_LABELS[side][button]} and, while holding it, make the ${SIDE[side]} Joy-Con disconnect (press its Sync button)`,
    detail: "The held button must be released by the disconnect, not stay stuck.", timeoutMs: 60000,
    onEvent(type, d, ctx) {
      if (type === "release" && key(d.controller, d.button) === k) {
        if (d.reason === "offline" || d.reason === "stale") {
          return { pass: !ctx.input.isPressed(side, button), observed: { reason: d.reason, connection: ctx.input.device(side).connection } };
        }
        ctx.s.byHand = (ctx.s.byHand ?? 0) + 1; // let go too early -- keep waiting
      }
      return null;
    },
  };
}

function reconnect(side, button) {
  return {
    id: `reconnect-${side}`, section: "Sync / disconnect", expect: { online: side, then: key(side, button) },
    title: `${SIDE[side]}: let it reconnect (press Sync again if it does not come back), then press ${BUTTON_LABELS[side][button]}`,
    detail: "Measures time until it is online again; input must work right away.", timeoutMs: 180000,
    onEvent(type, d, ctx) {
      if (type === "device" && d.controller === side && d.online && ctx.s.onlineAt == null) ctx.s.onlineAt = ctx.now();
      if (type === "press" && d.controller === side && d.button === button && ctx.input.device(side).online) {
        return { pass: true, observed: { onlineAfterMs: ctx.s.onlineAt == null ? 0 : Math.round(ctx.s.onlineAt - ctx.t0) } };
      }
      return null;
    },
  };
}

export function defaultSteps() {
  return [
    imuFree("right", "a"),
    imuFree("left", "down"),
    ...BUTTONS_LEFT.map((b) => single("left", b)),
    ...BUTTONS_RIGHT.map((b) => single("right", b)),
    chord("chord-left", "LEFT: hold ZL + L + D-pad ↑ together, then let go", ["left.zl", "left.l", "left.up"]),
    chord("chord-right", "RIGHT: hold A + B + R together, then let go", ["right.a", "right.b", "right.r"]),
    chord("chord-cross", "Hold LEFT L and RIGHT R at the same time, then let go", ["left.l", "right.r"]),
    releaseOrder("right", "a", "b"),
    releaseOrder("left", "zl", "up"),
    hold("right", "zr", 3000),
    ...["left", "right"].flatMap((s) => [
      stickRest(s), stickDir(s, "up"), stickDir(s, "down"), stickDir(s, "left"), stickDir(s, "right"),
      stickCircle(s), { ...stickRest(s), id: `stick-${s}-return`, title: `${SIDE[s]} stick: let go — back to centre, hands off 2 s` },
      stickClick(s),
    ]),
    bothSticks(),
    alternate(),
    syncProbe("right"),
    disconnectHeld("right", "a"),
    reconnect("right", "a"),
  ];
}

export class ChecklistRunner extends EventTarget {
  /** @param {import('../../../shared/protocol/input-client.mjs').JoyCon2Input} input */
  constructor(input, steps = defaultSteps(), { now = () => performance.now(), send = () => {} } = {}) {
    super();
    this.input = input;
    this.steps = steps;
    this.now = now;
    this.send = send;
    this.index = -1;
    this.results = new Map();
    this.ctx = null;
    for (const type of ["press", "release", "stick", "device"]) {
      input.on(type, (d) => this._dispatch(type, d));
    }
  }

  get current() {
    return this.steps[this.index] ?? null;
  }

  get done() {
    return this.index >= this.steps.length;
  }

  _emit() {
    this.dispatchEvent(new CustomEvent("change", { detail: { index: this.index, step: this.current } }));
  }

  start(i = 0) {
    this.goto(i);
  }

  goto(i) {
    this.index = Math.max(0, Math.min(i, this.steps.length));
    const step = this.current;
    if (!step) {
      this.ctx = null;
      this.send("mark", { event: "run-end", report: this.report() });
      this._emit();
      return;
    }
    const t0 = this.now();
    this.ctx = { input: this.input, t0, s: {}, now: this.now, elapsed: () => this.now() - t0, finished: false };
    this.send("mark", { event: "step-start", id: step.id, title: step.title, expect: step.expect });
    this._emit();
  }

  next() { this.goto(this.index + 1); }
  back() { this.goto(this.index - 1); }
  retry() { this.goto(this.index); }
  skip() { this._finish({ pass: null, observed: "skipped" }); }

  _finish(result) {
    const step = this.current;
    if (!step || this.ctx.finished) return;
    this.ctx.finished = true;
    const rec = { id: step.id, section: step.section, title: step.title, ...result, ms: Math.round(this.ctx.elapsed()) };
    this.results.set(step.id, rec);
    this.send("mark", { event: "step-end", ...rec });
    this.dispatchEvent(new CustomEvent("result", { detail: rec }));
  }

  _dispatch(type, d) {
    const step = this.current;
    if (!step || this.ctx.finished || !step.onEvent) return;
    const r = step.onEvent(type, d, this.ctx);
    if (r) this._finish(r);
  }

  tick() {
    const step = this.current;
    if (!step || this.ctx.finished) return;
    const r = step.onTick?.(this.ctx);
    if (r) return this._finish(r);
    if (step.timeoutMs && this.ctx.elapsed() > step.timeoutMs) {
      this._finish(step.onTimeout?.(this.ctx) ?? { pass: false, observed: "timed out", s: this.ctx.s });
    }
  }

  report() {
    const rows = this.steps.map((s) => this.results.get(s.id) ?? { id: s.id, title: s.title, pass: undefined });
    const count = (v) => rows.filter((r) => r.pass === v).length;
    return {
      summary: { pass: count(true), fail: count(false), info: count(null), notRun: count(undefined), total: rows.length },
      devices: Object.fromEntries(Object.entries(this.input.devices).map(([k, d]) => [k, { address: d.address, frames: d.frames, connection: d.connection }])),
      steps: rows,
    };
  }
}
