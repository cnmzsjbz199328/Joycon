import random

import pytest

from adapter.src.calibration.calibrator import Calibrator
from adapter.src.decoder.encode import build_raw_packet
from adapter.src.decoder.packet import decode_packet


def _still_packet(rng: random.Random, gyro_bias=(2.0, -1.0, 0.5)):
    # gravity mostly on Z, small constant gyro bias + noise
    return build_raw_packet(
        side="left",
        accel_g=(0.02, -0.01, 1.0),
        gyro_dps=(
            gyro_bias[0] + rng.gauss(0, 0.4),
            gyro_bias[1] + rng.gauss(0, 0.4),
            gyro_bias[2] + rng.gauss(0, 0.4),
        ),
    )


def test_calibration_recovers_gyro_bias_and_gravity():
    rng = random.Random(42)
    cal = Calibrator(target_samples=124)
    while cal.progress < 1.0:
        cal.feed(decode_packet(_still_packet(rng), "left"))
    res = cal.finish()

    assert res.gyro_bias.x == pytest.approx(2.0, abs=0.3)
    assert res.gyro_bias.y == pytest.approx(-1.0, abs=0.3)
    assert res.gyro_bias.z == pytest.approx(0.5, abs=0.3)
    # gravity reference is a unit vector, dominated by +Z
    mag = (res.gravity_ref.x**2 + res.gravity_ref.y**2 + res.gravity_ref.z**2) ** 0.5
    assert mag == pytest.approx(1.0, abs=1e-6)
    assert res.gravity_ref.z > 0.99
    assert res.gyro_deadzone_dps > 0


def test_apply_removes_bias():
    rng = random.Random(1)
    cal = Calibrator()
    while cal.progress < 1.0:
        cal.feed(decode_packet(_still_packet(rng), "left"))
    res = cal.finish()

    moving = decode_packet(
        build_raw_packet(side="left", gyro_dps=(2.0 + 100.0, -1.0, 0.5)), "left"
    )
    res.apply(moving)
    assert moving.gyro_dps.x == pytest.approx(100.0, abs=0.5)
    assert moving.gyro_dps.y == pytest.approx(0.0, abs=0.5)


def test_not_ready_raises():
    cal = Calibrator(min_samples=60)
    cal.feed(decode_packet(build_raw_packet(side="left"), "left"))
    try:
        cal.finish()
        raise AssertionError("should have raised")
    except RuntimeError:
        pass
