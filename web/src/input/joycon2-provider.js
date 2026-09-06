// web/src/input/joycon2-provider.js
//
// @experimental
// Target hardware path: connects to the native Python adapter's WebSocket bridge
// (adapter/src/service.py) and forwards its InputFrames. The BLE reverse
// engineering behind the adapter is UNVERIFIED on real hardware in this repo --
// see docs/JOYCON2_PROTOCOL.md. Marked experimental until the J1-J12 checklist
// passes on a physical Joy-Con 2.

import { InputProvider } from "./provider.js";
import {
  WS_DEFAULT_URL,
  PROTOCOL_VERSION,
  parseEnvelope,
  isInputFrame,
} from "../../../shared/protocol/contracts.mjs";

export class JoyCon2Provider extends InputProvider {
  constructor(opts = {}) {
    super("joycon2", opts);
    this.url = opts.url ?? WS_DEFAULT_URL;
    this._ws = null;
    this._retry = 0;
    this._closedByUs = false;
  }

  get label() {
    return "Joy-Con 2 (via adapter) — experimental";
  }

  async connect() {
    this._closedByUs = false;
    await this._open();
  }

  _open() {
    return new Promise((resolve, reject) => {
      let settled = false;
      this._emitStatus("connecting");
      const ws = new WebSocket(this.url);
      this._ws = ws;

      ws.onopen = () => {
        this._retry = 0;
        this.connected = true;
        settled = true;
        this._emitStatus("connected");
        resolve();
      };

      ws.onmessage = (ev) => {
        const msg = parseEnvelope(ev.data);
        if (!msg) return;
        if (msg.v !== PROTOCOL_VERSION) {
          this._emitError(`protocol v${msg.v} != v${PROTOCOL_VERSION}`);
          return;
        }
        if (msg.type === "frame") {
          if (isInputFrame(msg.data)) {
            this.controller = msg.data.controller;
            this._emitFrame(msg.data);
          }
        } else if (msg.type === "status") {
          this.calibrated = !!msg.data.calibrated;
          if (msg.data.controller && msg.data.controller !== "unknown") {
            this.controller = msg.data.controller;
          }
          this._emitStatus(msg.data.connection, { hint: msg.data.hint ?? null });
        } else if (msg.type === "hello") {
          this.dispatchEvent(new CustomEvent("hello", { detail: msg.data }));
        }
      };

      ws.onerror = () => {
        if (!settled) {
          settled = true;
          reject(new Error(`cannot reach adapter at ${this.url}`));
        }
        this._emitError(`websocket error (${this.url})`);
      };

      ws.onclose = () => {
        this.connected = false;
        this._ws = null;
        if (this._closedByUs) {
          this._emitStatus("stopped");
          return;
        }
        this._emitStatus("disconnected");
        // browser-side reconnect with capped backoff (mirrors adapter policy intent)
        const delay = Math.min(8000, 500 * 2 ** this._retry++);
        setTimeout(() => {
          if (!this._closedByUs) this._open().catch(() => {});
        }, delay);
      };
    });
  }

  disconnect() {
    this._closedByUs = true;
    if (this._ws) this._ws.close();
    this._ws = null;
    super.disconnect();
  }
}
