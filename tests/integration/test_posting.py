"""post_due_room_charges against the DB (architecture.md §8.2; owner decisions 2026-11-16/17)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import Folio, FolioTransaction
from app.service.posting_service import post_due_room_charges
from tests.factories import make_plan, make_stay, make_tenant, make_user

MON_0800 = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def tenant(db):
    return make_tenant(db)


@pytest.fixture
def user(db, tenant):
    return make_user(db, tenant)


def folio_of(db, stay):
    return db.query(Folio).filter_by(stay_id=stay.id).one()


def room_charges(db, stay):
    return (db.query(FolioTransaction)
            .filter_by(folio_id=folio_of(db, stay).id, txn_type="room_charge")
            .order_by(FolioTransaction.period_no).all())


def post(db, stay, now):
    return post_due_room_charges(db, folio_of(db, stay), stay, now)


def test_period_1_posts_at_check_in_as_the_system(db, tenant, user):
    stay = make_stay(db, tenant, user, check_in_at=MON_0800)
    post(db, stay, MON_0800)
    [charge] = room_charges(db, stay)
    assert (charge.period_no, charge.amount, charge.direction) == (1, Decimal("1000.00"), "debit")
    assert charge.period_start_at == MON_0800
    assert charge.posting_key == f"room:{stay.stay_plan_id}:1"
    assert charge.created_by_user_id is None
    assert charge.description == "Full day 1"


def test_day_2_posts_only_after_deadline_plus_grace(db, tenant, user):
    stay = make_stay(db, tenant, user, check_in_at=MON_0800)
    post(db, stay, MON_0800)

    assert post(db, stay, MON_0800 + timedelta(hours=24, minutes=29, seconds=59)) == []
    assert len(room_charges(db, stay)) == 1

    post(db, stay, MON_0800 + timedelta(hours=24, minutes=30))
    assert [c.period_no for c in room_charges(db, stay)] == [1, 2]


def test_posting_twice_adds_nothing(db, tenant, user):
    stay = make_stay(db, tenant, user, check_in_at=MON_0800)
    later = MON_0800 + timedelta(days=2, hours=1)
    post(db, stay, later)
    assert post(db, stay, later) == []
    assert [c.period_no for c in room_charges(db, stay)] == [1, 2, 3]


def test_catch_up_dates_each_period_by_when_it_began(db, tenant, user):
    stay = make_stay(db, tenant, user, check_in_at=MON_0800)
    post(db, stay, MON_0800)
    post(db, stay, MON_0800 + timedelta(days=3, hours=1))  # nobody opened it until Thu 09:00
    charges = room_charges(db, stay)
    assert [c.period_no for c in charges] == [1, 2, 3, 4]
    assert [c.period_start_at for c in charges] == [MON_0800 + timedelta(days=n) for n in range(4)]


@pytest.mark.parametrize("period_hours,grace,second_due", [
    (2, 60, timedelta(hours=3)),              # beta lodge fresh-up: 14:00 -> block 2 at 17:00
    (1, 10, timedelta(hours=1, minutes=10)),  # hourly
])
def test_short_plans(db, tenant, user, period_hours, grace, second_due):
    plan = make_plan(db, tenant, period_hours=period_hours, grace_minutes=grace)
    stay = make_stay(db, tenant, user, check_in_at=MON_0800, plan=plan)
    post(db, stay, MON_0800 + second_due - timedelta(seconds=1))
    assert len(room_charges(db, stay)) == 1
    post(db, stay, MON_0800 + second_due)
    assert len(room_charges(db, stay)) == 2
    assert room_charges(db, stay)[1].posting_key == f"room:{plan.id}:2"


def test_checked_out_stay_stops_at_checkout(db, tenant, user):
    stay = make_stay(db, tenant, user, check_in_at=MON_0800)
    stay.status = "checked_out"
    stay.actual_checkout_at = MON_0800 + timedelta(hours=24, minutes=20)  # left inside the grace
    post(db, stay, MON_0800 + timedelta(days=7))                         # folio opened a week later
    assert [c.period_no for c in room_charges(db, stay)] == [1]


def test_price_change_only_affects_later_periods(db, tenant, user):
    stay = make_stay(db, tenant, user, check_in_at=MON_0800)
    post(db, stay, MON_0800 + timedelta(hours=25))        # days 1-2 at 1000
    stay.listed_price = Decimal("1500.00")                 # e.g. moved to a dearer room:
    stay.agreed_price = Decimal("1500.00")                 # a room change sets both prices
    post(db, stay, MON_0800 + timedelta(hours=49))        # day 3
    assert [c.amount for c in room_charges(db, stay)] == [Decimal("1000.00"), Decimal("1000.00"),
                                                          Decimal("1500.00")]


def test_reversed_period_is_not_posted_again(db, tenant, user):
    stay = make_stay(db, tenant, user, check_in_at=MON_0800)
    post(db, stay, MON_0800 + timedelta(hours=25))
    day_2 = room_charges(db, stay)[1]
    db.add(FolioTransaction(
        tenant_id=tenant.id, folio_id=day_2.folio_id, txn_type="reversal", direction="credit",
        amount=day_2.amount, related_txn_id=day_2.id, reason="test", created_by_user_id=user.id,
    ))
    db.flush()
    assert post(db, stay, MON_0800 + timedelta(hours=26)) == []


def test_a_wrong_check_in_time_posts_nothing_instead_of_thousands(db, tenant, user):
    from app.service.posting_service import MAX_PERIODS_PER_CATCH_UP, TooManyPeriods
    stay = make_stay(db, tenant, user, check_in_at=MON_0800.replace(year=26))  # the owner's typo, 2026-11-17
    with pytest.raises(TooManyPeriods):
        post(db, stay, MON_0800)
    assert room_charges(db, stay) == []

    stay.actual_check_in_at = MON_0800 - timedelta(days=MAX_PERIODS_PER_CATCH_UP)  # exactly the limit: 400 due
    post(db, stay, MON_0800)
    assert len(room_charges(db, stay)) == MAX_PERIODS_PER_CATCH_UP


def test_editing_the_plan_does_not_change_a_current_stay(db, tenant, user):
    plan = make_plan(db, tenant, period_hours=2, grace_minutes=60)
    stay = make_stay(db, tenant, user, check_in_at=MON_0800, plan=plan)
    plan.grace_minutes = 0  # the stay keeps its own copy (60)
    post(db, stay, MON_0800 + timedelta(hours=2, minutes=30))
    assert len(room_charges(db, stay)) == 1
