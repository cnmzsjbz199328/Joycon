import { test } from "node:test";
import assert from "node:assert/strict";
import { MotionEngine } from "../src/motion/motion-engine.js";
import { MockIMUProvider } from "../src/input/mock-imu-provider.js";

/** Feed the engine N seconds of scripted mock frames at fixed dt. */
function drive(engine, seconds, rateHz = 62) {
  const mock = new MockIMUProvider({ scripted: true });
  const frames = [];
  mock.addEventListener("frame", (e) => frames.push(e.detail));
  const dt = 1 / rateHz;
  for (let t = 0; t <= seconds; t += dt) mock.step(t);
  const motions = [];
  const gestures = [];
  engine.addEventListener("motion", (e) => motions.push(e.detail));
  engine.addEventListener("gesture", (e) => gestures.push(e.detail));
  for (const f of frames) engine.feed(f);
  return { motions, gestures, frames };
}

test("emits one MotionState per frame with the right shape", () => {
  const engine = new MotionEngine();
  const { motions, frames } = drive(engine, 1.0);
  assert.equal(motions.length, frames.length);
  const m = motions.at(-1);
  assert.equal(m.orientation.quaternion.length, 4);
  for (const k of ["pitch", "yaw", "roll"]) assert.ok(k in m.orientation.euler);
  for (const k of ["angularVelocity", "linearAcceleration"]) {
    assert.ok("x" in m[k] && "y" in m[k] && "z" in m[k]);
  }
  assert.ok(typeof m.motionSpeed === "number" && m.motionSpeed >= 0);
});

test("scripted mock produces the 4 slash directions + THRUST over one cycle", () => {
  const engine = new MotionEngine();
  const { gestures } = drive(engine, 12.5);
  const kinds = new Set(gestures.map((g) => g.gesture));
  for (const want of ["SLASH_RIGHT", "SLASH_LEFT", "SLASH_UP", "SLASH_DOWN", "THRUST"]) {
    assert.ok(kinds.has(want), `missing ${want}; got ${[...kinds].join(",")}`);
  }
});

test("motionSpeed rises during a scripted slash and settles when idle", () => {
  const engine = new MotionEngine();
  const { motions } = drive(engine, 3.5);
  const speeds = motions.map((m) => m.motionSpeed);
  const peak = Math.max(...speeds);
  const tail = speeds.slice(-20).reduce((s, v) => s + v, 0) / 20;
  assert.ok(peak > 0.5, `peak=${peak}`);
  assert.ok(tail < peak * 0.6, `tail=${tail} peak=${peak}`);
});

test("gesture is attached to MotionState briefly then clears", () => {
  const engine = new MotionEngine();
  const { motions } = drive(engine, 3.0);
  assert.ok(motions.some((m) => m.gesture && m.gesture.gesture === "SLASH_RIGHT"));
  assert.ok(motions.some((m) => m.gesture === null));
});

test("still input after calibration -> near-zero angular velocity (dead zone)", () => {
  const engine = new MotionEngine();
  // feed 2.5 s of pure-still frames (no script) via a non-scripted mock
  const mock = new MockIMUProvider({ scripted: false });
  const frames = [];
  mock.addEventListener("frame", (e) => frames.push(e.detail));
  const dt = 1 / 62;
  for (let t = 0; t <= 3; t += dt) mock.step(t);

  engine.startCalibration(2);
  const speeds = [];
  for (const f of frames) {
    const m = engine.feed(f);
    if (!engine.isCalibrating()) speeds.push(Math.hypot(m.angularVelocity.x, m.angularVelocity.y, m.angularVelocity.z));
  }
  const avg = speeds.reduce((s, v) => s + v, 0) / speeds.length;
  assert.ok(avg < 0.2, `avg angular speed after calibration = ${avg}`);
});
