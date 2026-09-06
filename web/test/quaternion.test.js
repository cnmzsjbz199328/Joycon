import { test } from "node:test";
import assert from "node:assert/strict";
import {
  qIdentity,
  qIntegrate,
  qRotate,
  qBetween,
  qToEuler,
  qMul,
  qConjugate,
} from "../src/motion/quaternion.js";

const near = (a, b, eps = 1e-6) => Math.abs(a - b) <= eps;

test("identity rotates nothing", () => {
  assert.deepEqual(qRotate(qIdentity(), [1, 2, 3]), [1, 2, 3]);
});

test("integrating 90 deg/s about z for 1 s yaws x -> y", () => {
  let q = qIdentity();
  const w = [0, 0, Math.PI / 2];
  for (let i = 0; i < 1000; i++) q = qIntegrate(q, w, 1 / 1000);
  const v = qRotate(q, [1, 0, 0]);
  assert.ok(near(v[0], 0, 1e-3), `x=${v[0]}`);
  assert.ok(near(v[1], 1, 1e-3), `y=${v[1]}`);
});

test("qBetween aligns a onto b", () => {
  const q = qBetween([0, 0, 1], [1, 0, 0]);
  const v = qRotate(q, [0, 0, 1]);
  assert.ok(near(v[0], 1, 1e-6) && near(v[1], 0, 1e-6) && near(v[2], 0, 1e-6));
});

test("q * conj(q) = identity", () => {
  const q = [0.5, 0.5, 0.5, 0.5];
  const r = qMul(q, qConjugate(q));
  assert.ok(near(r[0], 1) && near(r[1], 0) && near(r[2], 0) && near(r[3], 0));
});

test("euler round-trips small angles", () => {
  let q = qIdentity();
  q = qIntegrate(q, [0.3, 0, 0], 1); // ~0.3 rad roll
  const e = qToEuler(q);
  assert.ok(near(e.roll, 0.3, 1e-2), `roll=${e.roll}`);
});
