// web/src/ui/connection-panel.js
// Provider picker + connect/disconnect + live connection/controller status.
// Renders into a container; emits nothing -- call getProvider() after "connected".

import { PROVIDERS, DEFAULT_PROVIDER, createProvider } from "../input/index.js";

const CONN_LABEL = {
  connecting: ["warn", "Connecting…"],
  connected: ["good", "Connected"],
  disconnected: ["bad", "Disconnected"],
  reconnecting: ["warn", "Reconnecting…"],
  cooldown: ["bad", "Controller cooldown"],
  stopped: ["", "Stopped"],
};

export class ConnectionPanel {
  /** @param {HTMLElement} el @param {(p:import('../input/provider.js').InputProvider)=>void} onProvider */
  constructor(el, { onProvider, onStatus, defaultId = DEFAULT_PROVIDER } = {}) {
    this.el = el;
    this.onProvider = onProvider ?? (() => {});
    this.onStatus = onStatus ?? (() => {});
    this.provider = null;
    this._render(defaultId);
  }

  _render(defaultId) {
    const opts = Object.entries(PROVIDERS)
      .map(
        ([id, m]) =>
          `<option value="${id}" ${id === defaultId ? "selected" : ""}>${m.label}${
            m.experimental ? " ⚠" : ""
          }</option>`,
      )
      .join("");

    this.el.innerHTML = `
      <h2>Joy-Con Connection</h2>
      <div class="row">
        <select class="cp-src">${opts}</select>
      </div>
      <div class="row">
        <button class="cp-connect primary">Connect</button>
        <button class="cp-disconnect" disabled>Disconnect</button>
      </div>
      <div class="row spread" style="margin-top:12px">
        <span class="pill"><span class="dot cp-dot"></span><span class="cp-conn">Disconnected</span></span>
        <span class="pill">Controller: <b class="cp-ctrl">—</b></span>
      </div>
      <div class="row spread">
        <span class="pill"><span class="dot cp-caldot"></span><span class="cp-cal">Not calibrated</span></span>
        <span class="pill cp-src-tag">—</span>
      </div>
      <div class="hint cp-hint"></div>
    `;

    this.$ = (s) => this.el.querySelector(s);
    this.$(".cp-connect").addEventListener("click", () => this.connect());
    this.$(".cp-disconnect").addEventListener("click", () => this.disconnect());
  }

  async connect() {
    this.disconnect();
    const id = this.$(".cp-src").value;
    const meta = PROVIDERS[id];
    this.$(".cp-src-tag").textContent = meta.experimental ? "EXPERIMENTAL" : id;
    this.$(".cp-src-tag").classList.toggle("tag-exp", !!meta.experimental);
    if (!meta.providesIMU) {
      this._hint(`${meta.label}: no real IMU — motion is synthesised.`);
    } else {
      this._hint("");
    }

    const provider = createProvider(id);
    this.provider = provider;
    provider.addEventListener("status", (e) => this._status(e.detail));
    provider.addEventListener("error", (e) => this._hint(e.detail.message));

    this.$(".cp-connect").disabled = true;
    try {
      await provider.connect();
      this.$(".cp-disconnect").disabled = false;
      this.onProvider(provider);
    } catch (err) {
      this._status({ connection: "disconnected" });
      this._hint(`${err.message}. Try “Mock IMU”.`);
      this.$(".cp-connect").disabled = false;
      this.provider = null;
    }
  }

  disconnect() {
    if (this.provider) {
      try {
        this.provider.disconnect();
      } catch {}
      this.provider = null;
    }
    this.$(".cp-connect").disabled = false;
    this.$(".cp-disconnect").disabled = true;
  }

  _status(s) {
    const [cls, label] = CONN_LABEL[s.connection] ?? ["", s.connection];
    this.$(".cp-conn").textContent = label;
    this.$(".cp-dot").className = `dot cp-dot ${cls}`;
    if (s.controller && s.controller !== "unknown") {
      this.$(".cp-ctrl").textContent = s.controller.toUpperCase();
    }
    if (typeof s.calibrated === "boolean") {
      this.$(".cp-cal").textContent = s.calibrated ? "Calibrated" : "Not calibrated";
      this.$(".cp-caldot").className = `dot cp-caldot ${s.calibrated ? "good" : "warn"}`;
    }
    if (s.hint) this._hint(s.hint);
    this.onStatus(s);
  }

  _hint(msg) {
    this.$(".cp-hint").textContent = msg || "";
  }
}
