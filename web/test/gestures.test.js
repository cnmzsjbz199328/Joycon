import { test } from "node:test";
import assert from "node:assert/strict";
import { GestureRecognizer } from "../src/motion/gestures.js";

const RATE = 62;
const DT = 1 / RATE;

/** Drive a bell-shaped angular-velocity burst on one axis; return emitted events. */
function swing(rec, { axis, peak, durS = 0.16, startT = 0, quietAfterS = 0.3 }) {
  const events = [];
  let t = startT;
  const n = Math.round(durS / DT);
  for (let i = 0; i < n; i++) {
    const env = Math.sin((i / (n - 1)) * Math.PI);
    const g = [0, 0, 0];
    g[axis] = peak * env;
    const ev = rec.update(t, g, [0, 0, 0]);
    if (ev) events.push(ev);
    t += DT;
  }
  const quietN = Math.round(quietAfterS / DT);
  for (let i = 0; i < quietN; i++) {
    const ev = rec.update(t, [0, 0, 0], [0, 0, 0]);
    if (ev) events.push(ev);
    t += DT;
  }
  return { events, endT: t };
}

test("z+ swing -> SLASH_RIGHT, z- -> SLASH_LEFT", () => {
  const rec = new GestureRecognizer();
  const a = swing(rec, { axis: 2, peak: 16 });
  assert.equal(a.events.length, 1);
  assert.equal(a.events[0].gesture, "SLASH_RIGHT");
  assert.ok(a.events[0].strength > 0.7);

  const b = swing(rec, { axis: 2, peak: -16, startT: a.endT });
  assert.equal(b.events.at(-1).gesture, "SLASH_LEFT");
});

test("x+ swing -> SLASH_UP, x- -> SLASH_DOWN", () => {
  const rec = new GestureRecognizer();
  const up = swing(rec, { axis: 0, peak: 16 });
  assert.equal(up.events.at(-1).gesture, "SLASH_UP");
  const down = swing(rec, { axis: 0, peak: -16, startT: up.endT });
  assert.equal(down.events.at(-1).gesture, "SLASH_DOWN");
});

test("four directions are distinguishable in sequence", () => {
  const rec = new GestureRecognizer();
  let t = 0;
  const got = [];
  for (const [axis, peak] of [[2, 16], [2, -16], [0, 16], [0, -16]]) {
    const r = swing(rec, { axis, peak, startT: t });
    got.push(r.events.at(-1).gesture);
    t = r.endT;
  }
  assert.deepEqual(got, ["SLASH_RIGHT", "SLASH_LEFT", "SLASH_UP", "SLASH_DOWN"]);
});

test("gentle motion below threshold emits nothing", () => {
  const rec = new GestureRecognizer();
  const r = swing(rec, { axis: 2, peak: 3 });
  assert.equal(r.events.length, 0);
});

test("THRUST: forward accel spike with low rotation", () => {
  const rec = new GestureRecognizer();
  let t = 0;
  let ev = null;
  for (let i = 0; i < 10; i++) {
    ev = rec.update(t, [0, 0, 0], [0, 3.2, 0]) || ev;
    t += DT;
  }
  assert.ok(ev && ev.gesture === "THRUST");
});

test("refractory: a second swing too soon is suppressed", () => {
  const rec = new GestureRecognizer({ refractory: 0.5 });
  const a = swing(rec, { axis: 2, peak: 16, quietAfterS: 0.05 });
  const b = swing(rec, { axis: 2, peak: 16, startT: a.endT, quietAfterS: 0.05 });
  assert.equal(a.events.length + b.events.length, 1);
});

test("gesture event has full contract shape", () => {
  const rec = new GestureRecognizer();
  const { events } = swing(rec, { axis: 2, peak: 16 });
  const e = events[0];
  for (const k of ["gesture", "strength", "speed", "direction", "timestamp", "controller"]) {
    assert.ok(k in e, `missing ${k}`);
  }
  assert.equal(e.direction.length, 3);
  assert.ok(e.strength >= 0 && e.strength <= 1);
});
