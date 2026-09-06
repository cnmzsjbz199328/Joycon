from adapter.src.bluetooth.reconnect import ReconnectPolicy


def test_backoff_grows_then_caps():
    p = ReconnectPolicy(base_delay_s=1.0, ceiling_s=60.0, jitter_frac=0.0)
    delays = [p.next_delay() for _ in range(8)]
    # 1, 2, 4, 8, then cooldown holds at ceiling
    assert delays[0] == 1.0
    assert delays[1] == 2.0
    assert delays[2] == 4.0
    assert delays[3] == 8.0
    assert all(d == 60.0 for d in delays[4:])


def test_cooldown_flag_and_hint():
    p = ReconnectPolicy(jitter_frac=0.0, cooldown_after_failures=4)
    for _ in range(3):
        p.next_delay()
    assert not p.in_cooldown
    assert p.status_hint() is None
    p.next_delay()  # 4th failure
    assert p.in_cooldown
    assert "wait" in p.status_hint().lower()


def test_reset_after_success():
    p = ReconnectPolicy(jitter_frac=0.0)
    for _ in range(6):
        p.next_delay()
    assert p.in_cooldown
    p.reset()
    assert not p.in_cooldown
    assert p.next_delay() == 1.0


def test_jitter_within_bounds():
    p = ReconnectPolicy(base_delay_s=10.0, jitter_frac=0.2)
    d = p.next_delay()
    assert 8.0 <= d <= 12.0
