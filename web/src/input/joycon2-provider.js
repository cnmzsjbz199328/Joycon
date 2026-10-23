// web/src/input/joycon2-provider.js
//
// Hardware path for the Motion Engine: connects to the native Python adapter's
// WebSocket bridge (adapter/src/service.py) and forwards ONE controller's
// InputFrames. The BLE link is verified on hardware (docs/HARDWARE_BRINGUP.md
// §5); the "experimental" tag stays until the remaining J-checklist items pass.
//
// Protocol v2: the adapter can stream a left and a right Joy-Con on one socket,
// with a status per controller. This provider follows `opts.controller`
// ("left" | "right"), or -- by default -- the first controller that comes
// online, and reports "connected" only while THAT controller is online (an
// open WebSocket alone is "connecting"). Buttons/sticks for other projects:
// use shared/protocol/input-client.mjs instead of this provider.

import { InputProvider } from "./provider.js";
import { WS_DEFAULT_URL, PROTOCOL_VERSION } from "../../../shared/protocol/contracts.mjs";

export class JoyCon2Provider extends InputProvider {
  constructor(opts = {}) {
    super("joycon2", opts);
    this.url = opts.url ?? WS_DEFAULT_URL;
    this.want = opts.controller ?? null; // null = lock onto the first one online
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

  _mine(controller) {
    if (controller !== "left" && controller !== "right") return false;
    if (this.want == null) this.want = controller;
    return controller === this.want;
  }

  _open() {
    return new Promise((resolve, reject) => {
      let settled = false;
      this._emitStatus("connecting");
      const ws = new WebSocket(this.url);
      this._ws = ws;

      ws.onopen = () => {
        this._retry = 0;
        settled = true;
        this._emitStatus("connecting", { hint: "adapter reachable — waiting for the Joy-Con 2 to come online" });
        resolve();
      };

      ws.onmessage = (ev) => {
        let msg;
        try {
          msg = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (!msg || typeof msg.type !== "string") return;
        if (msg.v !== PROTOCOL_VERSION) {
          this._emitError(`adapter protocol v${msg.v} != v${PROTOCOL_VERSION} — update the adapter or the page`);
          return;
        }
        const d = msg.data ?? {};
        if (msg.type === "frame") {
          if (this.connected && this._mine(d.controller)) this._emitFrame(d);
        } else if (msg.type === "status") {
          // lock only onto a controller that is actually online
          if (this.want == null && d.connection !== "connected") return;
          if (!this._mine(d.controller)) return;
          this.controller = d.controller;
          this.calibrated = !!d.calibrated;
          this.connected = d.connection === "connected";
          this._emitStatus(d.connection, { hint: d.hint ?? null });
        } else if (msg.type === "hello") {
          this.dispatchEvent(new CustomEvent("hello", { detail: d }));
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
        this._emitStatus("disconnected", { hint: "adapter connection lost — retrying" });
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
