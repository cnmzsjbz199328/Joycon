# tests/

Tests live next to the code they cover:

| Suite | Location | Run |
| --- | --- | --- |
| Adapter (Python, pytest) | [`adapter/tests/`](../adapter/tests/) | `cd adapter && ../.venv/bin/python -m pytest -q` |
| Web unit (node:test) | [`web/test/*.test.js`](../web/test/) | `cd web && npm test` |
| Web end-to-end (Playwright, headless) | [`web/test/e2e_smoke.py`](../web/test/e2e_smoke.py) | see [../docs/TESTING.md](../docs/TESTING.md) §1 |

Phase-by-phase test record and the Definition-of-Done status: [../docs/TESTING.md](../docs/TESTING.md).
