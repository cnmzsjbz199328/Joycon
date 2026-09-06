// web/src/playground/main.js
// Wires provider -> MotionEngine -> (IMU scope + numeric readouts + 3D sword).

import "../ui/styles.css";
import { ConnectionPanel } from "../ui/connection-panel.js";
import { CalibrationOverlay } from "../ui/calibration.js";
import { MotionEngine } from "../motion/motion-engine.js";
import { ImuViz } from "./imu-viz.js";
import { SwordScene } from "./sword.js";

const engine = new MotionEngine();
let detach = null;

// --- connection -----------------------------------------------------------
const panel = new ConnectionPanel(document.getElementById("conn"), {
  onProvider(provider) {
    if (detach) detach();
    engine.reset();
    detach = engine.attach(provider);
    // if provider says it's not calibrated, offer calibration immediately
    if (!provider.calibrated) cal.run(2);
  },
  onStatus(s) {
    document.getElementById("src-note").textContent = s.hint || "";
  },
});

const cal = new CalibrationOverlay(document.body, engine);
document.getElementById("recal").addEventListener("click", () => cal.run(2));

// --- visualizers --------------------------------------------------------
const viz = new ImuViz(document.getElementById("scope"));
const sword = new SwordScene(document.getElementById("sword"));

// --- numeric readouts -------------------------------------------------
const R = (id) => document.getElementById(id);
function setVec(prefix, v, digits = 2) {
  R(`${prefix}x`).textContent = v.x.toFixed(digits);
  R(`${prefix}y`).textContent = v.y.toFixed(digits);
  R(`${prefix}z`).textContent = v.z.toFixed(digits);
  for (const ax of ["x", "y", "z"]) {
    const el = R(`${prefix}${ax}bar`);
    if (el) {
      const range = prefix === "g" ? 12 : 2;
      const f = Math.max(-1, Math.min(1, v[ax] / range));
      el.style.width = `${Math.abs(f) * 50}%`;
      el.style.left = f >= 0 ? "50%" : `${50 - Math.abs(f) * 50}%`;
    }
  }
}

let latest = null;
engine.addEventListener("motion", (e) => {
  latest = e.detail;
  viz.push(latest);
});

const gestureEl = document.getElementById("gesture");
let gestureStaleAt = 0;
engine.addEventListener("gesture", (e) => {
  const g = e.detail;
  gestureEl.textContent = `${g.gesture.replace("_", " ")}   ·   Strength: ${Math.round(
    g.strength * 100,
  )}%`;
  gestureEl.classList.remove("stale");
  gestureStaleAt = performance.now() + 700;
});

// --- render loop (decoupled from the engine's frame rate) -------------
function frame() {
  if (latest) {
    setVec("g", latest.angularVelocity, 2);
    setVec("a", latest.linearAcceleration, 2);
    R("speed").textContent = latest.motionSpeed.toFixed(2);
    const e = latest.orientation.euler;
    R("euler").textContent = `p ${deg(e.pitch)}  y ${deg(e.yaw)}  r ${deg(e.roll)}`;
    sword.update(latest);
  }
  viz.draw();
  sword.render();
  if (performance.now() > gestureStaleAt) gestureEl.classList.add("stale");
  requestAnimationFrame(frame);
}
const deg = (r) => `${((r * 180) / Math.PI).toFixed(0)}°`.padStart(5);
requestAnimationFrame(frame);
