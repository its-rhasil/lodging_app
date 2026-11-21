"""Posting math (architecture.md §8.2): periods_due, period_start, posting keys. No DB."""
from datetime import datetime, timedelta, timezone

import pytest

from app.service.posting_service import next_charge_at, period_start, periods_due, room_posting_key

CHECK_IN = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)  # Mon 08:00


def at(**delta) -> datetime:
    return CHECK_IN + timedelta(**delta)


@pytest.mark.parametrize("horizon,expected", [
    (at(), 1),                                  # at check-in
    (at(hours=24), 1),                          # exactly one day: still inside grace
    (at(hours=24, minutes=29, seconds=59), 1),  # boundary + grace - 1s
    (at(hours=24, minutes=30), 2),              # boundary + grace: day 2 due
    (at(hours=48, minutes=29), 2),
    (at(hours=48, minutes=30), 3),
    (at(days=3, hours=1), 4),                   # multi-day catch-up (Thu 09:00)
    (at(hours=-5), 1),                          # horizon before check-in: still 1
])
def test_full_day_with_30_minutes_grace(horizon, expected):
    assert periods_due(CHECK_IN, horizon, 24, 30) == expected


def test_zero_grace_charges_exactly_at_the_boundary():
    assert periods_due(CHECK_IN, at(hours=24) - timedelta(seconds=1), 24, 0) == 1
    assert periods_due(CHECK_IN, at(hours=24), 24, 0) == 2


@pytest.mark.parametrize("horizon,expected", [
    (at(hours=2, minutes=59), 1),
    (at(hours=3), 2),          # beta lodge fresh-up: check-in 14:00 -> block 2 due 17:00
    (at(hours=4, minutes=59), 2),
    (at(hours=5), 3),
])
def test_beta_lodge_fresh_up_2h_with_60_minutes_grace(horizon, expected):
    assert periods_due(CHECK_IN, horizon, 2, 60) == expected


@pytest.mark.parametrize("period_hours,grace,second_due", [
    (3, 15, at(hours=3, minutes=15)),   # fresh-up block plan
    (1, 10, at(hours=1, minutes=10)),   # hourly plan
])
def test_short_plans(period_hours, grace, second_due):
    assert periods_due(CHECK_IN, second_due - timedelta(seconds=1), period_hours, grace) == 1
    assert periods_due(CHECK_IN, second_due, period_hours, grace) == 2


def test_period_start_is_check_in_plus_whole_periods():
    assert period_start(CHECK_IN, 1, 24) == CHECK_IN
    assert period_start(CHECK_IN, 3, 24) == at(days=2)
    assert period_start(CHECK_IN, 2, 2) == at(hours=2)


@pytest.mark.parametrize("now,expected", [
    (at(), at(hours=24, minutes=30)),                      # owner's example: next charge 24h30 after check-in
    (at(hours=24, minutes=29), at(hours=24, minutes=30)),  # still before it
    (at(hours=24, minutes=30), at(hours=48, minutes=30)),  # day 2 just posted -> day 3 next
])
def test_next_charge_at(now, expected):
    assert next_charge_at(CHECK_IN, now, 24, 30) == expected


def test_next_charge_at_for_fresh_up():
    assert next_charge_at(CHECK_IN, at(hours=1), 2, 60) == at(hours=3)  # 14:00 check-in -> 17:00


def test_posting_key_includes_the_plan():
    assert room_posting_key(7, 3) == "room:7:3"
