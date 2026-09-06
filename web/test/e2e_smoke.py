"""Headless smoke test for the three web pages, driven by the Mock IMU provider.

Asserts (no hardware):
  - no console errors / page errors
  - Playground: provider connects, a gesture fires, motionSpeed peaks > 0.4,
    controller shows LEFT, 3D sword canvas renders non-blank
  - Fruit Slash: score and slice count increase while the scripted mock slashes
"""

import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
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
    pg.screenshot(path="/private/tmp/claude-501/-Users-tangjiang-Public-Joycon/67fab509-9d15-402c-9f9b-b31e73bfb59d/scratchpad/playground.png", full_page=True)

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
    gm.screenshot(path="/private/tmp/claude-501/-Users-tangjiang-Public-Joycon/67fab509-9d15-402c-9f9b-b31e73bfb59d/scratchpad/game.png", full_page=True)

    browser.close()


with sync_playwright() as p:
    run(p)

if FAILS:
    print("\n--- FAILURES ---")
    for f in FAILS:
        print(" -", f)
    sys.exit(1)
print("\nALL SMOKE CHECKS PASSED")
