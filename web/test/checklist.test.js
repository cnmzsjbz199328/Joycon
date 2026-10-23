import { test } from "node:test";
import assert from "node:assert/strict";
import { JoyCon2Input } from "../../shared/protocol/input-client.mjs";
import { PROTOCOL_VERSION, BUTTONS_LEFT, BUTTONS_RIGHT } from "../../shared/protocol/contracts.mjs";
import { ChecklistRunner, defaultSteps } from "../src/input-test/checklist.js";

const V = PROTOCOL_VERSION;

function rig(only) {
  let t = 0;
  const input = new JoyCon2Input({ now: () => t, staleMs: 1e9 });
  const marks = [];
  const steps = defaultSteps().filter((s) => only.includes(s.id));
  const run = new ChecklistRunner(input, steps, { now: () => t, send: (type, data) => marks.push(data) });
  const results = [];
  run.addEventListener("result", (e) => results.push(e.detail));
  const status = (c, connection = "connected") =>
    input.handleMessage({ v: V, type: "status", data: { controller: c, connection, calibrated: false } });
  const frame = (c, pressed = [], stick = { x: 0, y: 0 }, imuReady = true) =>
    input.handleMessage({
      v: V, type: "frame",
      data: {
        timestamp: t / 1000, seq: 0, controller: c, stick, stickRaw: { x: 2048, y: 2048 }, imuReady,
        buttons: Object.fromEntries((c === "left" ? BUTTONS_LEFT : BUTTONS_RIGHT).map((n) => [n, pressed.includes(n)])),
        accelerometer: { x: 0, y: 0, z: 1 }, gyroscope: { x: 0, y: 0, z: 0 },
      },
    });
  const wait = (ms) => {
    for (let i = 0; i < ms / 50; i++) { t += 50; run.tick(); }
  };
  status("left");
  status("right");
  return { run, results, marks, frame, status, wait };
}

test("single-button step passes on the right bit and fails, with evidence, on a swapped one", () => {
  const r = rig(["btn-right-a", "btn-right-b"]);
  r.run.start();
  r.frame("right", ["b"]); // person pressed A, adapter reported "b"
  r.frame("right", []);
  r.run.next();
  r.frame("right", ["b"]);
  r.frame("right", []);
  assert.deepEqual(r.results.map((x) => [x.id, x.pass, x.observed]), [
    ["btn-right-a", false, ["right.b"]],
    ["btn-right-b", true, ["right.b"]],
  ]);
  assert.deepEqual(r.marks.map((m) => `${m.event}:${m.id}`), [
    "step-start:btn-right-a", "step-end:btn-right-a", "step-start:btn-right-b", "step-end:btn-right-b"]);
});

test("chord across both controllers, and an extra button fails it", () => {
  const r = rig(["chord-cross"]);
  r.run.start();
  r.frame("left", ["l"]);
  r.frame("right", ["r"]);
  r.frame("left", []);
  r.frame("right", []);
  assert.equal(r.results[0].pass, true);
  r.run.retry();
  r.frame("left", ["l", "zl"]);
  r.frame("right", ["r"]);
  r.frame("left", []);
  r.frame("right", []);
  assert.equal(r.results[1].pass, false);
  assert.deepEqual(r.results[1].observed, { unexpected: ["left.zl"] });
});

test("release-order step measures how long the other button stayed held", () => {
  const r = rig(["order-right-a-b"]);
  r.run.start();
  r.frame("right", ["a", "b"]);
  r.wait(200);
  r.frame("right", ["a"]);
  r.wait(1200);
  r.frame("right", []);
  assert.equal(r.results[0].pass, true);
  assert.ok(r.results[0].observed.heldAloneMs >= 1150);
});

test("stick direction needs the right sign, sustained", () => {
  const r = rig(["stick-left-up"]);
  r.run.start();
  r.frame("left", [], { x: 0, y: -1 }); // wrong way
  r.wait(1000);
  assert.equal(r.results.length, 0);
  r.frame("left", [], { x: 0.05, y: 0.99 });
  r.wait(600);
  assert.equal(r.results[0].pass, true);
});

test("buttons-without-IMU step and disconnect-while-held step", () => {
  const r = rig(["imu-free-right", "disconnect-held-right"]);
  r.run.start();
  r.frame("right", ["a"], undefined, false);
  assert.equal(r.results[0].pass, true);
  r.frame("right", []);
  r.run.next();
  r.frame("right", ["a"]);
  r.status("right", "disconnected");
  assert.equal(r.results[1].pass, true);
  assert.equal(r.results[1].observed.reason, "offline");
});

test("default run covers every button on both sides", () => {
  const ids = new Set(defaultSteps().map((s) => s.id));
  for (const b of BUTTONS_LEFT) assert.ok(ids.has(`btn-left-${b}`), b);
  for (const b of BUTTONS_RIGHT) assert.ok(ids.has(`btn-right-${b}`), b);
  assert.equal(ids.size, defaultSteps().length, "step ids are unique");
});
