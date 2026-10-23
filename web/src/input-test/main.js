// web/src/input-test/main.js
// Input test page: consumes ONLY the public interface (adapter WebSocket via
// shared/protocol/input-client.mjs) -- exactly what another project would use.
// ?ws=ws://host:port overrides the adapter URL.

import "../ui/styles.css";
import { connectJoyCon2 } from "../../../shared/protocol/input-client.mjs";
import { WS_DEFAULT_URL, buttonsFor } from "../../../shared/protocol/contracts.mjs";
import { BUTTON_LABELS, ChecklistRunner } from "./checklist.js";

const url = new URLSearchParams(location.search).get("ws") ?? WS_DEFAULT_URL;
const jc = connectJoyCon2({ url });
globalThis.__jc = jc; // for headless checks
const $ = (id) => document.getElementById(id);

// --- adapter --------------------------------------------------------------
$("ws-url").textContent = url;
const WS_CLS = { open: "good", connecting: "warn", closed: "bad" };
jc.on("adapter", (a) => {
  $("ws-state").textContent = a.transport;
  $("ws-dot").className = `dot ${WS_CLS[a.transport] ?? ""}`;
  const h = a.hello;
  $("ws-hello").textContent = h ? `adapter ${h.adapter} · source ${h.source}` : "—";
  if (a.transport === "open") $("ws-error").textContent = "";
  else if (a.transport === "closed") $("ws-error").textContent = `adapter not reachable at ${url} — is "python -m adapter.src.service" running?`;
});
jc.on("error", (e) => ($("ws-error").textContent = e.message));

// --- devices ----------------------------------------------------------------
const CONN_CLS = { connected: "good", connecting: "warn", reconnecting: "warn", cooldown: "bad", disconnected: "bad", stopped: "", unknown: "" };
const view = {};

function buildDevice(side) {
  const el = $(`dev-${side}`);
  el.innerHTML = `
    <div class="it-dev-head">
      <h2>${side.toUpperCase()}</h2>
      <span class="pill"><span class="dot d-dot"></span><span class="d-conn">unknown</span></span>
      <span class="pill d-online">offline</span>
      <span class="pill d-imu">IMU —</span>
      <span class="pill mono d-rate">0 Hz</span>
    </div>
    <div class="it-btns">${buttonsFor(side)
      .map((b) => `<div class="it-btn" data-b="${b}">${b}<small class="d-n">0</small></div>`)
      .join("")}</div>
    <div class="it-stick">
      <canvas width="400" height="400"></canvas>
      <table class="mono">
        <tr><td>x, y</td><td class="d-xy">0.000, 0.000</td></tr>
        <tr><td>r, angle</td><td class="d-ra">0.000</td></tr>
        <tr><td>raw x, y</td><td class="d-raw">—</td></tr>
        <tr><td>raw x range</td><td class="d-rx">—</td></tr>
        <tr><td>raw y range</td><td class="d-ry">—</td></tr>
        <tr><td>max r seen</td><td class="d-maxr">0.000</td></tr>
        <tr><td>address</td><td class="d-addr">—</td></tr>
        <tr><td></td><td><button class="d-reset">reset stats</button></td></tr>
      </table>
    </div>
    <div class="hint d-hint"></div>`;
  const q = (s) => el.querySelector(s);
  const v = {
    el, q, counts: {}, trail: [], dirty: true, frames: 0, rate: 0,
    btn: Object.fromEntries([...el.querySelectorAll(".it-btn")].map((n) => [n.dataset.b, n])),
    canvas: el.querySelector("canvas"),
    stats: null,
  };
  q(".d-reset").addEventListener("click", () => {
    v.stats = null;
    v.trail = [];
    v.counts = {};
    for (const n of Object.values(v.btn)) n.querySelector(".d-n").textContent = "0";
    v.dirty = true;
  });
  view[side] = v;
}
buildDevice("left");
buildDevice("right");

jc.on("device", (d) => {
  const v = view[d.controller];
  v.q(".d-conn").textContent = d.connection;
  v.q(".d-dot").className = `dot d-dot ${CONN_CLS[d.connection] ?? ""}`;
  v.q(".d-online").textContent = d.online ? "online" : d.stale ? "stale" : "offline";
  v.q(".d-imu").textContent = d.calibrated ? "IMU calibrated" : d.online ? "IMU calibrating" : "IMU —";
  v.q(".d-addr").textContent = d.address ?? "—";
  v.q(".d-hint").textContent = d.hint ?? "";
  v.el.classList.toggle("offline", !d.online);
  for (const [b, n] of Object.entries(v.btn)) n.classList.toggle("on", !!d.buttons[b]);
  v.dirty = true;
});

jc.on("frame", ({ controller, frame }) => {
  const v = view[controller];
  v.frames++;
  const raw = frame.stickRaw;
  if (raw) {
    const s = (v.stats ??= { minX: raw.x, maxX: raw.x, minY: raw.y, maxY: raw.y, maxR: 0 });
    s.minX = Math.min(s.minX, raw.x); s.maxX = Math.max(s.maxX, raw.x);
    s.minY = Math.min(s.minY, raw.y); s.maxY = Math.max(s.maxY, raw.y);
  }
  if (v.stats) v.stats.maxR = Math.max(v.stats.maxR, Math.hypot(frame.stick.x, frame.stick.y));
  v.raw = raw;
  v.dirty = true;
});

jc.on("stick", ({ controller, x, y }) => {
  const v = view[controller];
  v.trail.push([x, y]);
  if (v.trail.length > 90) v.trail.shift();
  v.dirty = true;
});

// --- event log ----------------------------------------------------------
const logEl = $("log");
function log(cls, text) {
  const li = document.createElement("li");
  li.className = cls;
  li.textContent = `${(performance.now() / 1000).toFixed(2).padStart(8)}  ${text}`;
  logEl.prepend(li);
  while (logEl.children.length > 80) logEl.lastChild.remove();
}
jc.on("press", (e) => {
  const v = view[e.controller];
  v.btn[e.button]?.classList.add("on");
  v.counts[e.button] = (v.counts[e.button] ?? 0) + 1;
  v.btn[e.button].querySelector(".d-n").textContent = v.counts[e.button];
  log("", `${e.controller.padEnd(5)} ▼ ${e.button}`);
});
jc.on("release", (e) => {
  view[e.controller].btn[e.button]?.classList.remove("on");
  log("rel", `${e.controller.padEnd(5)} ▲ ${e.button}${e.reason !== "input" ? `   (${e.reason})` : ""}`);
});
let lastConn = {};
jc.on("device", (d) => {
  const s = `${d.connection}${d.stale ? " (stale)" : ""}`;
  if (lastConn[d.controller] !== s) log("sys", `${d.controller.padEnd(5)} ● ${s}`);
  lastConn[d.controller] = s;
});
$("log-clear").addEventListener("click", () => (logEl.innerHTML = ""));

// --- render loop ----------------------------------------------------------
function drawStick(v, d) {
  const c = v.canvas, g = c.getContext("2d");
  const W = c.width, R = W * 0.42, C = W / 2;
  g.clearRect(0, 0, W, W);
  g.strokeStyle = "#2b3446";
  g.lineWidth = 2;
  g.beginPath(); g.arc(C, C, R, 0, Math.PI * 2); g.stroke();
  g.setLineDash([6, 6]);
  g.beginPath(); g.arc(C, C, R * 0.95, 0, Math.PI * 2); g.stroke();
  g.setLineDash([]);
  g.beginPath(); g.moveTo(C - R, C); g.lineTo(C + R, C); g.moveTo(C, C - R); g.lineTo(C, C + R); g.stroke();
  v.trail.forEach(([x, y], i) => {
    g.fillStyle = `rgba(79,214,190,${(i / v.trail.length) * 0.5})`;
    g.beginPath(); g.arc(C + x * R, C - y * R, 4, 0, Math.PI * 2); g.fill();
  });
  const { x, y } = d.stick;
  g.fillStyle = d.online ? "#4fd6be" : "#8b93a7";
  g.beginPath(); g.arc(C + x * R, C - y * R, 11, 0, Math.PI * 2); g.fill();
}

function render() {
  for (const side of ["left", "right"]) {
    const v = view[side], d = jc.device(side);
    if (!v.dirty) continue;
    v.dirty = false;
    const { x, y } = d.stick;
    const r = Math.hypot(x, y);
    v.q(".d-xy").textContent = `${x.toFixed(3)}, ${y.toFixed(3)}`;
    v.q(".d-ra").textContent = `${r.toFixed(3)}   ${r ? `${Math.round((Math.atan2(y, x) * 180) / Math.PI)}°` : ""}`;
    v.q(".d-raw").textContent = v.raw ? `${v.raw.x}, ${v.raw.y}` : "—";
    const s = v.stats;
    v.q(".d-rx").textContent = s ? `${s.minX} … ${s.maxX}` : "—";
    v.q(".d-ry").textContent = s ? `${s.minY} … ${s.maxY}` : "—";
    v.q(".d-maxr").textContent = s ? s.maxR.toFixed(3) : "0.000";
    drawStick(v, d);
  }
  requestAnimationFrame(render);
}
requestAnimationFrame(render);
setInterval(() => {
  for (const v of Object.values(view)) {
    v.q(".d-rate").textContent = `${v.frames} Hz`;
    v.frames = 0;
  }
}, 1000);

// --- guided run -------------------------------------------------------------
const runner = new ChecklistRunner(jc, undefined, { send: (type, data) => jc.send(type, data) });
globalThis.__runner = runner;
const ICON = { true: "✓", false: "✗", null: "•" };
const CLS = { true: "pass", false: "fail", null: "info" };

function showStep() {
  const s = runner.current;
  $("cl-progress").textContent = runner.index < 0 ? "—" : `${Math.min(runner.index + 1, runner.steps.length)} / ${runner.steps.length}`;
  for (const id of ["cl-back", "cl-retry", "cl-skip"]) $(id).disabled = !s;
  $("cl-state").textContent = "";
  $("cl-state").className = "it-step-state";
  if (!s) {
    if (runner.index >= 0) {
      const sum = runner.report().summary;
      $("cl-section").textContent = "Run complete";
      $("cl-title").textContent = `✓ ${sum.pass}   ✗ ${sum.fail}   • ${sum.info}   not run ${sum.notRun}`;
      $("cl-detail").textContent = "The report was sent to the adapter (lands in the --record capture). You can also download it.";
    }
    return;
  }
  $("cl-section").textContent = s.section;
  $("cl-title").textContent = s.title;
  $("cl-detail").textContent = s.detail ?? "";
  $("cl-state").textContent = "waiting for you…";
}

function showResults() {
  const ol = $("cl-results");
  ol.innerHTML = "";
  for (const s of runner.steps) {
    const r = runner.results.get(s.id);
    if (!r) continue;
    const li = document.createElement("li");
    li.className = CLS[r.pass];
    const obs = typeof r.observed === "string" ? r.observed : JSON.stringify(r.observed);
    li.textContent = `${ICON[r.pass]} ${s.id}  ${obs ?? ""}`;
    ol.appendChild(li);
  }
}

let advanceTimer = null;
runner.addEventListener("change", showStep);
runner.addEventListener("result", (e) => {
  const r = e.detail;
  $("cl-state").textContent = `${ICON[r.pass]} ${r.pass === true ? "pass" : r.pass === false ? "FAIL" : "recorded"}  ${typeof r.observed === "string" ? r.observed : JSON.stringify(r.observed)}`;
  $("cl-state").className = `it-step-state ${CLS[r.pass]}`;
  showResults();
  clearTimeout(advanceTimer);
  advanceTimer = setTimeout(() => runner.next(), r.pass === false ? 2500 : 900);
});
setInterval(() => runner.tick(), 50);

$("cl-start").addEventListener("click", () => {
  clearTimeout(advanceTimer);
  jc.send("mark", { event: "run-start", userAgent: navigator.userAgent, devices: runner.report().devices });
  runner.start();
  $("cl-start").textContent = "Restart";
});
$("cl-back").addEventListener("click", () => { clearTimeout(advanceTimer); runner.back(); });
$("cl-retry").addEventListener("click", () => { clearTimeout(advanceTimer); runner.retry(); });
$("cl-skip").addEventListener("click", () => { clearTimeout(advanceTimer); runner.skip(); });
$("cl-report").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(runner.report(), null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `joycon2-input-report-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
  a.click();
});

// keyboard shortcuts for the run: Enter = retry, → = skip, ← = back
window.addEventListener("keydown", (e) => {
  if (!runner.current) return;
  if (e.key === "ArrowRight") $("cl-skip").click();
  else if (e.key === "ArrowLeft") $("cl-back").click();
  else if (e.key === "Enter") $("cl-retry").click();
});
