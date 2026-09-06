// web/src/game/main.js
// Provider -> MotionEngine -> FruitSlash. Same input/motion stack as the
// Playground; only the consumer changes (GOAL.md §19).

import "../ui/styles.css";
import { ConnectionPanel } from "../ui/connection-panel.js";
import { CalibrationOverlay } from "../ui/calibration.js";
import { MotionEngine } from "../motion/motion-engine.js";
import { FruitSlash } from "./fruit-slash.js";

const engine = new MotionEngine();
const game = new FruitSlash(document.getElementById("stage"), {
  onScore({ score, combo, slices }) {
    document.getElementById("score").textContent = score;
    document.getElementById("combo").textContent = combo;
    document.getElementById("slices").textContent = slices;
  },
});

engine.addEventListener("motion", (e) => game.onMotion(e.detail));
engine.addEventListener("gesture", (e) => game.onGesture(e.detail));

let detach = null;
const panel = new ConnectionPanel(document.getElementById("conn"), {
  onProvider(provider) {
    if (detach) detach();
    engine.reset();
    detach = engine.attach(provider);
    if (!provider.calibrated) cal.run(2);
  },
  onStatus(s) {
    document.getElementById("note").textContent = s.hint || "";
  },
});
const cal = new CalibrationOverlay(document.body, engine);

let last = performance.now();
function loop(now) {
  let dt = (now - last) / 1000;
  last = now;
  if (!(dt > 0) || dt > 0.1) dt = 1 / 60;
  game.update(dt);
  game.render();
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
