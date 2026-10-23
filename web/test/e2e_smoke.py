"""Headless smoke test for the web pages (no hardware).

Asserts:
  - no console errors / page errors
  - Playground (Mock IMU): provider connects, a gesture fires, motionSpeed peaks
    > 0.4, controller shows LEFT, 3D sword canvas renders non-blank
  - Fruit Slash (Mock IMU): score and slice count increase while the scripted mock slashes
  - Input Test (real adapter, --source synthetic --side both, spawned here):
    both controllers online, press/release events from both sides, and killing
    the adapter while a button is held releases it ("transport"); restarting
    the adapter brings both back
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
OUT = Path(os.environ.get("E2E_OUT", tempfile.gettempdir()))
ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PORT = 8798
FAILS: list[str] = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def wire_console(page, tag):
    def on_console(m):
        if m.type == "error":
            FAILS.append(f"[{tag}] console.error: {m.text}")
    page.on("console", on_console)
    page.on("pageerror", lambda e: FAILS.append(f"[{tag}] pageerror: {e}"))


def connect_mock(page):
    page.select_option("select.cp-src", "mock-imu")
    page.click("button.cp-connect")
    for _ in range(50):
        if page.inner_text(".cp-conn").strip() == "Connected":
            return True
        page.wait_for_timeout(100)
    return False


def run(p):
    browser = p.chromium.launch(headless=True)

    # ---------------- Playground + 3D Sword ----------------
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    wire_console(pg, "playground")
    pg.goto(f"{BASE}/playground.html")
    pg.wait_for_load_state("networkidle")
    check(connect_mock(pg), "playground: provider connected")
    check(pg.inner_text(".cp-ctrl").strip() == "LEFT", f"playground: controller LEFT ({pg.inner_text('.cp-ctrl').strip()})")

    # Observe the engine directly for ~13 s (one full mock script cycle).
    obs = pg.evaluate(
        """() => new Promise(res => {
          const seen = new Set();
          let peakSpeed = 0, frames = 0;
          // hook the engine via the gesture flash + speed readout
          const gEl = document.getElementById('gesture');
          const sEl = document.getElementById('speed');
          const iv = setInterval(() => {
            frames++;
            const s = parseFloat(sEl.textContent) || 0;
            if (s > peakSpeed) peakSpeed = s;
            const m = gEl.textContent.match(/^([A-Z ]+)\\s+·/);
            if (m) seen.add(m[1].trim());
          }, 50);
          setTimeout(() => { clearInterval(iv); res({ gestures: [...seen], peakSpeed, frames }); }, 13000);
        })"""
    )
    check(obs["frames"] > 100, f"playground: readout loop ran ({obs['frames']} ticks)")
    check(obs["peakSpeed"] > 0.4, f"playground: motionSpeed peaked > 0.4 ({obs['peakSpeed']:.2f})")
    check(len(obs["gestures"]) >= 1, f"playground: gesture(s) fired ({obs['gestures']})")

    sword_px = pg.evaluate(
        """() => {
          const c = document.getElementById('sword');
          const g = c.getContext('webgl2') || c.getContext('webgl');
          if (!g) return -1;
          const px = new Uint8Array(4 * c.width * c.height);
          g.readPixels(0, 0, c.width, c.height, g.RGBA, g.UNSIGNED_BYTE, px);
          let nz = 0;
          for (let i = 0; i < px.length; i += 4) if (px[i] || px[i+1] || px[i+2]) nz++;
          return nz;
        }"""
    )
    check(sword_px > 500, f"playground: 3D sword canvas rendered (nonzero px={sword_px})")
    pg.screenshot(path=str(OUT / "playground.png"), full_page=True)

    # ---------------- Fruit Slash ----------------
    gm = browser.new_page(viewport={"width": 1280, "height": 900})
    wire_console(gm, "game")
    gm.goto(f"{BASE}/game.html")
    gm.wait_for_load_state("networkidle")
    check(connect_mock(gm), "game: provider connected")

    gm.wait_for_timeout(16000)
    score = int(gm.inner_text("#score"))
    slices = int(gm.inner_text("#slices"))
    check(slices > 0, f"game: slices registered ({slices})")
    check(score > 0, f"game: score increased ({score})")
    gm.screenshot(path=str(OUT / "game.png"), full_page=True)

    run_input_page(browser)
    browser.close()


def start_adapter():
    proc = subprocess.Popen(
        [sys.executable, "-m", "adapter.src.service", "--source", "synthetic", "--side", "both",
         "--port", str(ADAPTER_PORT)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", ADAPTER_PORT), timeout=0.2).close()
            return proc
        except OSError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("adapter did not start")


def run_input_page(browser):
    adapter = start_adapter()
    try:
        ip = browser.new_page(viewport={"width": 1280, "height": 1300})
        wire_console(ip, "input")
        ip.goto(f"{BASE}/input.html?ws=ws://127.0.0.1:{ADAPTER_PORT}")
        ip.wait_for_function(
            "globalThis.__jc?.device('left').online && globalThis.__jc?.device('right').online", timeout=8000)
        check(True, "input: left and right online")
        ip.wait_for_timeout(2500)  # synthetic button walk: one button per side per second
        log = ip.eval_on_selector_all("#log li", "els => els.map(e => e.textContent)")
        check(any("left  \u25bc" in t for t in log) and any("right \u25bc" in t for t in log),
              "input: press events from both controllers")
        check(any("\u25b2" in t for t in log), "input: release events")

        ip.wait_for_function(
            "Object.values(globalThis.__jc.devices).some(d => Object.values(d.buttons).some(Boolean))", timeout=3000)
        adapter.kill()
        adapter.wait()
        ip.wait_for_function("globalThis.__jc.adapter.transport !== 'open'", timeout=5000)
        state = ip.evaluate("""() => ({
          pressed: Object.values(globalThis.__jc.devices).flatMap(d => Object.entries(d.buttons).filter(([,v]) => v)),
          online: Object.values(globalThis.__jc.devices).map(d => d.online),
          lit: document.querySelectorAll('.it-btn.on').length,
          log: [...document.querySelectorAll('#log li')].map(e => e.textContent).slice(0, 8),
        })""")
        check(state["pressed"] == [] and state["lit"] == 0, f"input: adapter killed mid-hold -> nothing stays pressed ({state['pressed']})")
        check(not any(state["online"]), "input: both controllers offline after adapter loss")
        check(any("(transport)" in t for t in state["log"]), "input: release logged with reason 'transport'")

        adapter = start_adapter()
        ip.wait_for_function(
            "globalThis.__jc.device('left').online && globalThis.__jc.device('right').online", timeout=15000)
        check(True, "input: both back online after adapter restart")
        ip.screenshot(path=str(OUT / "input.png"), full_page=True)
    finally:
        adapter.kill()


with sync_playwright() as p:
    run(p)

if FAILS:
    print("\n--- FAILURES ---")
    for f in FAILS:
        print(" -", f)
    sys.exit(1)
print("\nALL SMOKE CHECKS PASSED")
