# examples/ — using Joy-Con 2 buttons and sticks from another project

The adapter turns the Joy-Con 2's BLE reports into a WebSocket stream
(`ws://127.0.0.1:8765`, contract in [`shared/protocol/README.md`](../shared/protocol/README.md)).
A consumer never deals with BLE packets or the IMU.

```bash
# 1. adapter: connects a left and a right Joy-Con 2 (press Sync on each)
.venv/bin/python -m adapter.src.service --source joycon2
#    no hardware: two fake controllers walking through every button
.venv/bin/python -m adapter.src.service --source synthetic --side both

# 2a. JavaScript (Node >= 22, or import the same module in a browser)
node examples/input-client.mjs           # both controllers
node examples/input-client.mjs right     # only the right one

# 2b. Python (needs `websockets`)
.venv/bin/python examples/input_client.py
.venv/bin/python examples/input_client.py left
```

Both print controller online/offline, every press/release (with the reason when
a release was forced: `offline`, `stale`, `transport`) and stick values, and
show a combination check.

| Example | Uses | Shows |
| --- | --- | --- |
| [`input-client.mjs`](input-client.mjs) | [`shared/protocol/input-client.mjs`](../shared/protocol/input-client.mjs) (reference client, no dependencies) | device selection, status, press/release events, polling stick state, combos |
| [`input_client.py`](input_client.py) | raw WebSocket + the client rules (protocol README §6) in ~80 lines | same, for Python programs |

A browser page doing the same with a UI: [`web/input.html`](../web/input.html)
(`cd web && npm run dev` → <http://localhost:5173/input.html>).
