import { test } from "node:test";
import assert from "node:assert/strict";
import { JoyCon2Input } from "../../shared/protocol/input-client.mjs";
import { PROTOCOL_VERSION, BUTTONS_LEFT, BUTTONS_RIGHT } from "../../shared/protocol/contracts.mjs";

const V = PROTOCOL_VERSION;
const status = (controller, connection, extra = {}) => ({ v: V, type: "status", data: { connection, controller, calibrated: false, hint: null, ...extra } });
let seq = 0;
const frame = (controller, pressed = [], stick = { x: 0, y: 0 }, extra = {}) => ({
  v: V,
  type: "frame",
  data: {
    timestamp: seq / 33, seq: seq++, controller,
    buttons: Object.fromEntries((controller === "left" ? BUTTONS_LEFT : BUTTONS_RIGHT).map((n) => [n, pressed.includes(n)])),
    stick, stickRaw: { x: 2048, y: 2048 },
    accelerometer: { x: 0, y: 0, z: 1 }, gyroscope: { x: 0, y: 0, z: 0 }, imuReady: true, ...extra,
  },
});

function setup(opts = {}) {
  let t = 0;
  const input = new JoyCon2Input({ now: () => t, ...opts });
  const log = [];
  for (const type of ["press", "release", "stick", "error"]) input.on(type, (d) => log.push({ type, ...d }));
  return { input, log, advance: (ms) => (t += ms), events: (type) => log.filter((e) => e.type === type) };
}

const brief = (evs) => evs.map((e) => `${e.type}:${e.controller}.${e.button}${e.reason && e.reason !== "input" ? `(${e.reason})` : ""}`);

test("press and release are edge-triggered, a held button does not repeat", () => {
  const { input, log } = setup();
  input.handleMessage(status("right", "connected"));
  input.handleMessage(frame("right", ["a"]));
  for (let i = 0; i < 90; i++) input.handleMessage(frame("right", ["a"])); // ~3 s hold
  assert.ok(input.isPressed("right", "a"));
  input.handleMessage(frame("right", []));
  assert.deepEqual(brief(log.filter((e) => e.type !== "stick")), ["press:right.a", "release:right.a"]);
});

test("chords and independent release", () => {
  const { input, log } = setup();
  input.handleMessage(status("left", "connected"));
  input.handleMessage(frame("left", ["zl"]));
  input.handleMessage(frame("left", ["zl", "up", "right"])); // diagonal on the d-pad while holding ZL
  input.handleMessage(frame("left", ["zl", "right"])); // release up only
  assert.ok(input.isPressed("left", "zl") && input.isPressed("left", "right") && !input.isPressed("left", "up"));
  input.handleMessage(frame("left", []));
  // events inside one frame come out in BUTTONS_LEFT order
  assert.deepEqual(brief(log), [
    "press:left.zl", "press:left.up", "press:left.right", "release:left.up", "release:left.right", "release:left.zl",
  ]);
});

test("left and right are isolated, including same-named buttons", () => {
  const { input } = setup();
  input.handleMessage(status("left", "connected"));
  input.handleMessage(status("right", "connected"));
  input.handleMessage(frame("left", ["sl", "stick"], { x: -1, y: 0 }));
  input.handleMessage(frame("right", ["sr"], { x: 0, y: 0.5 }));
  assert.ok(input.isPressed("left", "sl") && input.isPressed("left", "stick") && !input.isPressed("left", "sr"));
  assert.ok(input.isPressed("right", "sr") && !input.isPressed("right", "sl") && !input.isPressed("right", "stick"));
  assert.deepEqual(input.device("left").stick, { x: -1, y: 0 });
  assert.deepEqual(input.device("right").stick, { x: 0, y: 0.5 });
  input.handleMessage(status("right", "disconnected"));
  assert.ok(input.isPressed("left", "sl"), "right going offline must not touch left");
  assert.equal(input.device("left").online, true);
});

test("disconnect releases everything held and recenters the stick", () => {
  const { input, events } = setup();
  input.handleMessage(status("right", "connected"));
  input.handleMessage(frame("right", ["a", "zr"], { x: 0.9, y: 0.1 }));
  input.handleMessage(status("right", "disconnected"));
  const rel = events("release");
  assert.deepEqual(rel.map((e) => [e.button, e.reason]).sort(), [["a", "offline"], ["zr", "offline"]]);
  assert.deepEqual(input.device("right").stick, { x: 0, y: 0 });
  assert.equal(input.device("right").online, false);
  // late frames for an offline controller are ignored, so nothing re-presses
  input.handleMessage(frame("right", ["a"]));
  assert.equal(input.isPressed("right", "a"), false);
  assert.equal(input.device("right").ignoredFrames, 1);
});

test("reconnect starts clean and a still-held button presses again", () => {
  const { input, log } = setup();
  input.handleMessage(status("right", "connected"));
  input.handleMessage(frame("right", ["b"]));
  input.handleMessage(status("right", "reconnecting"));
  input.handleMessage(status("right", "connected"));
  input.handleMessage(frame("right", ["b"]));
  assert.deepEqual(brief(log.filter((e) => e.type !== "stick")), ["press:right.b", "release:right.b(offline)", "press:right.b"]);
});

test("WebSocket close releases every controller", () => {
  const { input, events } = setup();
  input.handleMessage(status("left", "connected"));
  input.handleMessage(status("right", "connected"));
  input.handleMessage(frame("left", ["l"]));
  input.handleMessage(frame("right", ["r"]));
  input.handleTransportClosed();
  assert.deepEqual(events("release").map((e) => `${e.controller}.${e.button}:${e.reason}`).sort(), ["left.l:transport", "right.r:transport"]);
  assert.equal(input.device("left").connection, "unknown");
  input.handleMessage(frame("left", ["l"]));
  assert.equal(input.isPressed("left", "l"), false, "no frames accepted until a fresh status");
});

test("stale stream releases after staleMs and recovers on the next frame", () => {
  const { input, advance, log } = setup({ staleMs: 1000 });
  input.handleMessage(status("left", "connected"));
  input.handleMessage(frame("left", ["minus"]));
  advance(900);
  input.tick();
  assert.ok(input.isPressed("left", "minus"));
  advance(200);
  input.tick();
  assert.equal(input.isPressed("left", "minus"), false);
  assert.equal(input.device("left").stale, true);
  input.handleMessage(frame("left", ["minus"]));
  assert.equal(input.device("left").stale, false);
  assert.deepEqual(brief(log), ["press:left.minus", "release:left.minus(stale)", "press:left.minus"]);
});

test("controller filter: a right-only client never sees left input", () => {
  const { input, log } = setup({ controllers: ["right"] });
  input.handleMessage(status("left", "connected"));
  input.handleMessage(frame("left", ["up"]));
  assert.equal(input.device("left"), null);
  assert.deepEqual(log, []);
});

test("protocol version mismatch is reported once and ignored", () => {
  const { input, events } = setup();
  input.handleMessage({ v: 1, type: "status", data: { connection: "connected", controller: "left", calibrated: true } });
  input.handleMessage({ v: 1, type: "frame", data: {} });
  assert.equal(events("error").length, 1);
  assert.equal(input.device("left").connection, "unknown");
});

test("stick events carry raw counts; buttons stay valid while imuReady is false", () => {
  const { input, events } = setup();
  input.handleMessage(status("left", "connected"));
  input.handleMessage(frame("left", ["capture"], { x: 0.7071, y: 0.7071 }, { imuReady: false, stickRaw: { x: 2900, y: 2950 } }));
  assert.ok(input.isPressed("left", "capture"));
  assert.equal(input.device("left").imuReady, false);
  assert.deepEqual(events("stick").at(-1), { type: "stick", controller: "left", x: 0.7071, y: 0.7071, raw: { x: 2900, y: 2950 } });
});
