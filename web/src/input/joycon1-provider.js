// web/src/input/joycon1-provider.js
// First-gen Nintendo Switch Joy-Con over WebHID (they ARE Bluetooth HID, unlike
// Joy-Con 2). This is a genuine fallback when a Joy-Con 2 / adapter is not
// available (GOAL.md §13). Protocol: standard full input report 0x30 with the
// IMU enabled -- see https://github.com/dekuNukem/Nintendo_Switch_Reverse_Engineering
//
// Requires a user gesture to call navigator.hid.requestDevice(). Runs only in
// Chromium with WebHID.

import { InputProvider, nowSeconds } from "./provider.js";

const NINTENDO_VID = 0x057e;
const PIDS = { 0x2006: "left", 0x2007: "right", 0x2009: "pro", 0x200e: "charge-grip" };

// gen1 IMU scale factors (uncalibrated, dekuNukem RE notes)
const ACC_G_PER_LSB = 0.000244;         // ~ +/- 8 g
const GYR_DPS_PER_LSB = 0.06103 * 4.0;  // ~ +/- 2000 dps
const DEG2RAD = Math.PI / 180;

let _subCounter = 0;

function subcommand(id, ...params) {
  const buf = new Uint8Array(10);
  buf[0] = _subCounter++ & 0x0f;
  // neutral rumble
  buf.set([0x00, 0x01, 0x40, 0x40, 0x00, 0x01, 0x40, 0x40], 1);
  const out = new Uint8Array(1 + buf.length + 1 + params.length);
  out[0] = 0x01; // rumble+subcmd report
  out.set(buf, 1);
  out[1 + buf.length] = id;
  out.set(params, 1 + buf.length + 1);
  return out;
}

export class JoyCon1Provider extends InputProvider {
  constructor(opts = {}) {
    super("joycon1", opts);
    this._device = null;
    this._onReport = (e) => this._handleReport(e);
    this._seq = 0;
  }

  get label() {
    return "Joy-Con (1st gen) via WebHID";
  }

  async connect() {
    if (!("hid" in navigator)) throw new Error("WebHID unavailable (use Chromium)");
    this._emitStatus("connecting");

    const existing = await navigator.hid.getDevices();
    let dev = existing.find((d) => d.vendorId === NINTENDO_VID && d.productId in PIDS);
    if (!dev) {
      const picked = await navigator.hid.requestDevice({
        filters: Object.keys(PIDS).map((pid) => ({
          vendorId: NINTENDO_VID,
          productId: Number(pid),
        })),
      });
      dev = picked[0];
    }
    if (!dev) throw new Error("no Joy-Con selected");
    if (!dev.opened) await dev.open();

    this._device = dev;
    this.controller = PIDS[dev.productId] ?? this.controller;
    dev.addEventListener("inputreport", this._onReport);

    // 0x40,0x01 -> enable IMU ; 0x03,0x30 -> standard full mode
    await dev.sendReport(0x01, subcommand(0x40, 0x01).slice(1));
    await new Promise((r) => setTimeout(r, 60));
    await dev.sendReport(0x01, subcommand(0x03, 0x30).slice(1));

    this.connected = true;
    this.calibrated = false; // gen1 has SPI calibration; not read here -> engine calibrates
    this._emitStatus("connected");
  }

  disconnect() {
    if (this._device) {
      this._device.removeEventListener("inputreport", this._onReport);
      this._device.close?.();
    }
    this._device = null;
    super.disconnect();
  }

  _handleReport(event) {
    if (event.reportId !== 0x30) return;
    const d = event.data; // DataView, IMU block starts at offset 12 within data
    const s16 = (o) => d.getInt16(o, true);

    // Average the 3 IMU sub-samples in the report.
    let ax = 0, ay = 0, az = 0, gx = 0, gy = 0, gz = 0;
    for (let i = 0; i < 3; i++) {
      const b = 12 + i * 12;
      ax += s16(b + 0); ay += s16(b + 2); az += s16(b + 4);
      gx += s16(b + 6); gy += s16(b + 8); gz += s16(b + 10);
    }
    const accel = {
      x: (ax / 3) * ACC_G_PER_LSB,
      y: (ay / 3) * ACC_G_PER_LSB,
      z: (az / 3) * ACC_G_PER_LSB,
    };
    const gyro = {
      x: (gx / 3) * GYR_DPS_PER_LSB * DEG2RAD,
      y: (gy / 3) * GYR_DPS_PER_LSB * DEG2RAD,
      z: (gz / 3) * GYR_DPS_PER_LSB * DEG2RAD,
    };

    const btnBytes = [d.getUint8(2), d.getUint8(3), d.getUint8(4)];
    const buttons = { _raw0: btnBytes[0], _raw1: btnBytes[1], _raw2: btnBytes[2] };

    this._emitFrame({
      timestamp: nowSeconds(),
      seq: this._seq++,
      controller: this.controller === "pro" ? "left" : this.controller,
      buttons,
      stick: { x: 0, y: 0 },
      accelerometer: accel,
      gyroscope: gyro,
      battery: null,
      temperature: null,
    });
  }
}
