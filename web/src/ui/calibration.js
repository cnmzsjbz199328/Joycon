// web/src/ui/calibration.js
// Modal overlay implementing GOAL.md §15 steps 5-6: "hold the Joy-Con flat for
// 2 seconds" -> progress -> "Calibration Complete". Drives MotionEngine.startCalibration.

export class CalibrationOverlay {
  /** @param {HTMLElement} host @param {import('../motion/motion-engine.js').MotionEngine} engine */
  constructor(host, engine) {
    this.engine = engine;
    this.el = document.createElement("div");
    this.el.style.cssText = `
      position: fixed; inset: 0; display: none; z-index: 50;
      background: rgba(6,9,14,.82); backdrop-filter: blur(3px);
      align-items: center; justify-content: center;`;
    this.el.innerHTML = `
      <div class="panel" style="width: 340px; text-align: center">
        <h2 style="margin-bottom:6px">Calibration</h2>
        <p class="cal-msg">Put the Joy-Con down flat and hold still…</p>
        <div class="bar" style="height:10px; margin:14px 0">
          <span class="cal-fill" style="left:0; width:0%; background:var(--accent)"></span>
        </div>
        <div class="row" style="justify-content:center; gap:8px">
          <button class="cal-start primary">Start</button>
          <button class="cal-close">Close</button>
        </div>
      </div>`;
    host.appendChild(this.el);

    this.$ = (s) => this.el.querySelector(s);
    this.$(".cal-start").addEventListener("click", () => this.run());
    this.$(".cal-close").addEventListener("click", () => this.hide());

    engine.addEventListener("calibration", (e) => this._on(e.detail));
  }

  show() { this.el.style.display = "flex"; }
  hide() { this.el.style.display = "none"; }

  run(seconds = 2) {
    this.show();
    this.$(".cal-fill").style.width = "0%";
    this.$(".cal-msg").textContent = "Hold still…";
    this.$(".cal-start").disabled = true;
    this.engine.startCalibration(seconds);
  }

  _on(d) {
    if (d.phase === "collecting" || d.phase === "start") {
      this.$(".cal-fill").style.width = `${Math.round(d.progress * 100)}%`;
    } else if (d.phase === "done") {
      this.$(".cal-fill").style.width = "100%";
      this.$(".cal-msg").textContent = "Calibration Complete";
      this.$(".cal-start").disabled = false;
      setTimeout(() => this.hide(), 750);
    }
  }
}
