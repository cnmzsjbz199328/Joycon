// web/src/input/provider.js
// InputProvider: the ONLY thing the Motion Engine, Playground and Game know about.
// They never see BLE, WebSocket, WebHID or a specific controller.
//
// Events (CustomEvent, detail = payload):
//   "status"  -> { connection, controller, calibrated, hint }   (shared/protocol Status)
//   "frame"   -> InputFrame   (shared/protocol §8.1)
//   "error"   -> { message }
//
// Lifecycle: new Provider(opts) -> await connect() -> ...frames... -> disconnect()

import { emptyInputFrame } from "../../../shared/protocol/contracts.mjs";

export class InputProvider extends EventTarget {
  /** @param {string} id  short machine name, e.g. "mock-imu" */
  constructor(id, { controller = "left" } = {}) {
    super();
    this.id = id;
    this.controller = controller;
    this.connected = false;
    this.calibrated = false;
    this._lastFrame = emptyInputFrame(controller);
  }

  /** Human label for the UI. */
  get label() {
    return this.id;
  }

  /** True if this provider can deliver real accelerometer + gyroscope data. */
  get providesIMU() {
    return true;
  }

  /** Override. Must resolve once frames are (about to start) flowing. */
  async connect() {
    throw new Error(`${this.id}: connect() not implemented`);
  }

  /** Override. Idempotent. */
  disconnect() {
    this.connected = false;
    this._emitStatus("stopped");
  }

  get lastFrame() {
    return this._lastFrame;
  }

  // --- helpers for subclasses ------------------------------------------------
  _emitFrame(frame) {
    this._lastFrame = frame;
    this.dispatchEvent(new CustomEvent("frame", { detail: frame }));
  }

  _emitStatus(connection, extra = {}) {
    const detail = {
      connection,
      controller: this.controller,
      calibrated: this.calibrated,
      hint: null,
      ...extra,
    };
    this.dispatchEvent(new CustomEvent("status", { detail }));
  }

  _emitError(message) {
    this.dispatchEvent(new CustomEvent("error", { detail: { message } }));
  }
}

/** Local monotonic seconds, matches the adapter's time.monotonic() semantics. */
export function nowSeconds() {
  return performance.now() / 1000;
}
