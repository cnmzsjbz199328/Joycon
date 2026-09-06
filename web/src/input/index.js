// web/src/input/index.js
// Provider registry + factory. The rest of the app only imports from here.

import { MockIMUProvider } from "./mock-imu-provider.js";
import { JoyCon2Provider } from "./joycon2-provider.js";
import { JoyCon1Provider } from "./joycon1-provider.js";
import { GamepadProvider } from "./gamepad-provider.js";
import { KeyboardProvider } from "./keyboard-provider.js";

/** id -> { ctor, label, providesIMU, experimental } */
export const PROVIDERS = {
  joycon2: { ctor: JoyCon2Provider, label: "Joy-Con 2 (adapter)", providesIMU: true, experimental: true },
  joycon1: { ctor: JoyCon1Provider, label: "Joy-Con 1 (WebHID)", providesIMU: true, experimental: false },
  gamepad: { ctor: GamepadProvider, label: "Gamepad API", providesIMU: false, experimental: false },
  keyboard: { ctor: KeyboardProvider, label: "Keyboard", providesIMU: false, experimental: false },
  "mock-imu": { ctor: MockIMUProvider, label: "Mock IMU", providesIMU: true, experimental: false },
};

export const DEFAULT_PROVIDER = "joycon2";
export const FALLBACK_PROVIDER = "mock-imu";

export function createProvider(id, opts = {}) {
  const entry = PROVIDERS[id];
  if (!entry) throw new Error(`unknown provider: ${id}`);
  return new entry.ctor(opts);
}

/**
 * Try `preferred`; if connect() throws, fall back to `mock-imu` so development /
 * the demo never dead-ends (GOAL.md §13: "Fallback 不阻塞").
 * @returns {Promise<{provider: import('./provider.js').InputProvider, id: string, fellBack: boolean}>}
 */
export async function connectWithFallback(preferred = DEFAULT_PROVIDER, opts = {}) {
  try {
    const provider = createProvider(preferred, opts);
    await provider.connect();
    return { provider, id: preferred, fellBack: false };
  } catch (err) {
    if (preferred === FALLBACK_PROVIDER) throw err;
    const provider = createProvider(FALLBACK_PROVIDER, opts);
    await provider.connect();
    provider.dispatchEvent(
      new CustomEvent("error", {
        detail: { message: `${preferred} failed (${err.message}); using ${FALLBACK_PROVIDER}` },
      }),
    );
    return { provider, id: FALLBACK_PROVIDER, fellBack: true };
  }
}

export { InputProvider } from "./provider.js";
