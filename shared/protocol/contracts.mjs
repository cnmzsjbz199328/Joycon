// shared/protocol/contracts.mjs
// Single source of truth for the browser side. Mirrors schema.json / frame.py.
// No build step: plain ES module, importable from web/ and from tests.

export const PROTOCOL_VERSION = 1;

export const WS_DEFAULT_URL = "ws://127.0.0.1:8765";

export const CONTROLLER = /** @type {const} */ (["left", "right"]);

export const GESTURES = /** @type {const} */ ([
  "SLASH_LEFT",
  "SLASH_RIGHT",
  "SLASH_UP",
  "SLASH_DOWN",
  "THRUST",
  "SHAKE",
  "ROTATE",
]);

export const CONNECTION_STATES = /** @type {const} */ ([
  "connecting",
  "connected",
  "disconnected",
  "reconnecting",
  "cooldown",
  "stopped",
]);

/** Button name lists per side (mirror adapter/src/decoder/buttons.py). */
export const BUTTONS_LEFT = [
  "up", "down", "left", "right", "minus", "l", "zl", "stick", "sl", "sr",
];
export const BUTTONS_RIGHT = [
  "a", "b", "x", "y", "plus", "r", "zr", "stick", "sl", "sr",
];

/** @returns {{v:number,type:string,data:object}|null} */
export function parseEnvelope(text) {
  let msg;
  try {
    msg = JSON.parse(text);
  } catch {
    return null;
  }
  if (!msg || msg.v !== PROTOCOL_VERSION || typeof msg.type !== "string") return null;
  if (typeof msg.data !== "object" || msg.data === null) return null;
  return msg;
}

/** Cheap runtime validation -- enough to catch a contract drift, not a full schema check. */
export function isInputFrame(f) {
  return (
    f &&
    typeof f.timestamp === "number" &&
    Number.isFinite(f.seq) &&
    (f.controller === "left" || f.controller === "right") &&
    f.stick && typeof f.stick.x === "number" && typeof f.stick.y === "number" &&
    isVec3(f.accelerometer) &&
    isVec3(f.gyroscope) &&
    f.buttons && typeof f.buttons === "object"
  );
}

export function isVec3(v) {
  return v && typeof v.x === "number" && typeof v.y === "number" && typeof v.z === "number";
}

export function isGestureEvent(g) {
  return (
    g &&
    GESTURES.includes(g.gesture) &&
    typeof g.strength === "number" &&
    typeof g.speed === "number" &&
    Array.isArray(g.direction) &&
    typeof g.timestamp === "number"
  );
}

/** Empty frame -- used as the initial state before the first packet arrives. */
export function emptyInputFrame(controller = "left") {
  return {
    timestamp: 0,
    seq: 0,
    controller,
    buttons: {},
    stick: { x: 0, y: 0 },
    accelerometer: { x: 0, y: 0, z: 1 },
    gyroscope: { x: 0, y: 0, z: 0 },
    battery: null,
    temperature: null,
  };
}

export function emptyMotionState(controller = "left") {
  return {
    timestamp: 0,
    controller,
    orientation: { quaternion: [1, 0, 0, 0], euler: { pitch: 0, yaw: 0, roll: 0 } },
    angularVelocity: { x: 0, y: 0, z: 0 },
    linearAcceleration: { x: 0, y: 0, z: 0 },
    motionSpeed: 0,
    gesture: null,
  };
}
