"""JoyCon2Source discovery/ownership with fake BLE scanner + connections."""

import asyncio
from types import SimpleNamespace

import pytest

import adapter.src.bluetooth.connection as connection_mod
import adapter.src.bluetooth.scanner as scanner_mod
from adapter.src.sources import JoyCon2Source, StateChange


class FakeConn:
    gatt_side: dict[str, str] = {}  # address -> side the "GATT table" reveals

    def __init__(self, address, *, device=None, side="unknown", on_notification, on_state_change, **_):
        self.address, self.side = address, side
        self.on_notification, self.on_state = on_notification, on_state_change
        self.stopped = False

    async def run(self):
        self.on_state("connecting", None, {"address": self.address})
        await asyncio.sleep(0)
        self.side = self.gatt_side.get(self.address, self.side)
        self.on_state("connected", None, {"address": self.address})
        while not self.stopped:
            self.on_notification(self.address.encode())
            await asyncio.sleep(0.01)
        self.on_state("stopped", None, {"address": self.address})

    def stop(self):
        self.stopped = True


def adv(address, side):
    return SimpleNamespace(address=address, side=side, device=None, name="Joy-Con 2",
                           side_source="product-id", manufacturer_data=b"")


@pytest.fixture
def fake_ble(monkeypatch):
    plan = []  # list of lists of adverts, one per scan call
    calls = []

    async def fake_scan(timeout, want, exclude_addresses=None):
        calls.append(set(exclude_addresses or ()))
        await asyncio.sleep(0)
        batch = plan.pop(0) if plan else []
        return [a for a in batch if a.address not in (exclude_addresses or ())][:want]

    monkeypatch.setattr(scanner_mod, "scan_for_controllers", fake_scan)
    monkeypatch.setattr(connection_mod, "JoyConConnection", FakeConn)
    FakeConn.gatt_side = {}
    return plan, calls


async def collect(src, seconds=0.4):
    src.settle_s = src.idle_s = 0.05
    items = []

    async def run():
        async for item in src.frames():
            items.append(item)

    task = asyncio.create_task(run())
    await asyncio.sleep(seconds)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await src.aclose()
    return items


def states(items):
    return [(i.side, i.state, i.info.get("address")) for i in items if isinstance(i, StateChange)]


def frame_sides(items):
    return {(i[1], i[0].decode()) for i in items if not isinstance(i, StateChange)}


@pytest.mark.asyncio
async def test_left_and_right_in_one_scan(fake_ble):
    plan, _ = fake_ble
    plan.append([adv("L1", "left"), adv("R1", "right")])
    items = await collect(JoyCon2Source())
    st = states(items)
    assert ("left", "connected", "L1") in st and ("right", "connected", "R1") in st
    assert frame_sides(items) == {("left", "L1"), ("right", "R1")}


@pytest.mark.asyncio
async def test_one_side_mode_skips_the_other_side_and_keeps_looking(fake_ble):
    plan, calls = fake_ble
    plan += [[adv("L1", "left")], [adv("L1", "left"), adv("R1", "right")]]
    items = await collect(JoyCon2Source(sides=("right",)))
    assert "L1" in calls[1], "a skipped unit must be excluded from later scans"
    assert states(items)[-1] == ("right", "connected", "R1")
    assert frame_sides(items) == {("right", "R1")}


@pytest.mark.asyncio
async def test_unknown_side_is_resolved_and_a_duplicate_is_ignored(fake_ble):
    plan, _ = fake_ble
    FakeConn.gatt_side = {"U1": "left", "L2": "left"}
    # adverts repeat like a real scanner; L2 takes the only free scan slot once,
    # resolves to a second left unit, is dropped and excluded, then R1 is found
    plan += [[adv("U1", "unknown")]] + [[adv("L2", "unknown"), adv("R1", "right")]] * 2
    items = await collect(JoyCon2Source())
    st = states(items)
    assert ("left", "connected", "U1") in st and ("right", "connected", "R1") in st
    assert not [s for s in st if s[2] == "L2"], "the second left unit must not speak for the left side"
    assert frame_sides(items) == {("left", "U1"), ("right", "R1")}


@pytest.mark.asyncio
async def test_gatt_correcting_the_advertised_side_frees_the_wrong_slot(fake_ble):
    plan, _ = fake_ble
    FakeConn.gatt_side = {"X1": "right"}  # advertised as left, really a right unit
    plan += [[adv("X1", "left")], [adv("L1", "left")]]
    items = await collect(JoyCon2Source())
    st = states(items)
    assert ("right", "connected", "X1") in st
    assert ("left", "connected", "L1") in st
    assert frame_sides(items) == {("right", "X1"), ("left", "L1")}
