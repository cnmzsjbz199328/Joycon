#!/usr/bin/env node
// Minimal integration example: read Joy-Con 2 buttons and sticks from the
// adapter without knowing anything about BLE packets or the IMU.
//
//   python -m adapter.src.service --source joycon2      # or --source synthetic --side both
//   node examples/input-client.mjs                       # both controllers
//   node examples/input-client.mjs right                 # pick one
//
// Node >= 22 (global WebSocket). The same import works in a browser.

import { connectJoyCon2 } from "../shared/protocol/input-client.mjs";

const pick = process.argv[2]; // "left" | "right" | undefined
const jc = connectJoyCon2({ controllers: pick ? [pick] : ["left", "right"] });

jc.on("adapter", (a) => console.log(`[adapter] ${a.transport}${a.hello ? ` (adapter ${a.hello.adapter}, source ${a.hello.source})` : ""}`));
jc.on("device", (d) => console.log(`[${d.controller}] ${d.online ? "ONLINE" : "offline"} (${d.connection})${d.hint ? ` - ${d.hint}` : ""}`));
jc.on("press", ({ controller, button }) => console.log(`[${controller}] ${button} down`));
jc.on("release", ({ controller, button, reason }) =>
  console.log(`[${controller}] ${button} up${reason !== "input" ? ` (${reason})` : ""}`));

// Sticks: poll the current state at your own rate (here 5 Hz) instead of
// handling every "stick" event.
setInterval(() => {
  for (const c of jc.controllers) {
    const d = jc.device(c);
    if (d.online && (d.stick.x || d.stick.y)) console.log(`[${c}] stick x=${d.stick.x.toFixed(2)} y=${d.stick.y.toFixed(2)}`);
  }
}, 200);

// Example of a combination check against current state.
jc.on("press", () => {
  if (jc.isPressed("right", "a") && jc.isPressed("right", "b")) console.log("A+B combo!");
});

process.on("SIGINT", () => {
  jc.close();
  process.exit(0);
});
