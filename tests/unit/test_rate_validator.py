"""validate_rate_set: the one validator for room-type create and update (P1-10, DL-R17)."""
from decimal import Decimal

import pytest

from app.core.errors import NotFound, ValidationFailed
from app.models import StayPlan
from app.service.room_type_service import validate_rate_set

DAILY, FRESHUP = 1, 2
PLANS = {
    DAILY: StayPlan(id=DAILY, name="Full day", period_hours=24, is_daily=True),
    FRESHUP: StayPlan(id=FRESHUP, name="Fresh-up", period_hours=2, is_daily=False),
}


def rate(plan_id: int, occupancy: int, price: str = "1000.00") -> dict:
    return {"stay_plan_id": plan_id, "occupancy": occupancy, "price": Decimal(price)}


def test_complete_daily_set_passes():
    validate_rate_set(3, [rate(DAILY, 1), rate(DAILY, 2), rate(DAILY, 3)], PLANS)


def test_other_plans_are_optional_and_may_be_partial():
    # The beta example: fresh-up for 1 and 2 guests only.
    validate_rate_set(3, [rate(DAILY, 1), rate(DAILY, 2), rate(DAILY, 3),
                          rate(FRESHUP, 1, "500"), rate(FRESHUP, 2, "500")], PLANS)


def test_missing_daily_occupancy_is_rejected_and_listed():
    with pytest.raises(ValidationFailed) as exc:
        validate_rate_set(3, [rate(DAILY, 1), rate(FRESHUP, 3)], PLANS)
    assert exc.value.code == "daily_rates_incomplete"
    assert exc.value.details["missing_occupancies"] == [2, 3]


def test_occupancy_above_capacity_is_rejected():
    with pytest.raises(ValidationFailed) as exc:
        validate_rate_set(2, [rate(DAILY, 1), rate(DAILY, 2), rate(FRESHUP, 3)], PLANS)
    assert exc.value.code == "occupancy_exceeds_capacity"
    assert exc.value.details["occupancies"] == [3]


def test_duplicate_plan_and_occupancy_is_rejected():
    with pytest.raises(ValidationFailed) as exc:
        validate_rate_set(1, [rate(DAILY, 1), rate(DAILY, 1, "900")], PLANS)
    assert exc.value.code == "duplicate_rate"


def test_plan_of_another_tenant_reads_as_not_found():
    with pytest.raises(NotFound) as exc:
        validate_rate_set(1, [rate(DAILY, 1), rate(99, 1)], PLANS)
    assert exc.value.code == "stay_plan_not_found"
