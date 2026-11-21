"""Plain factory functions (no factory_boy). Each one adds + flushes and returns the row."""
import itertools
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache

from app.core.security import generate_token, get_token_expiry, hash_password, hash_token
from app.models import (
    Folio, Guest, Room, RoomType, RoomTypeRate, Stay, StayPlan, Tenant, TenantSettings, User,
    UserPermissionOverride, UserSession,
)

DEFAULT_PASSWORD = "password123"
_seq = itertools.count(1)


@lru_cache
def _default_password_hash() -> str:
    return hash_password(DEFAULT_PASSWORD)  # bcrypt is slow; hash once per run


def make_tenant(db, name: str | None = None, status: str = "active") -> Tenant:
    """Tenant + settings + the daily plan, like the create-tenant CLI will do."""
    n = next(_seq)
    tenant = Tenant(
        name=name or f"Lodge {n}", contact_email=f"lodge{n}@example.com",
        contact_phone="9000000000", status=status,
    )
    db.add(tenant)
    db.flush()
    db.add(TenantSettings(tenant_id=tenant.id))
    db.add(StayPlan(tenant_id=tenant.id, name="Full day", period_hours=24, grace_minutes=30, is_daily=True))
    db.flush()
    return tenant


def daily_plan(db, tenant: Tenant) -> StayPlan:
    return db.query(StayPlan).filter_by(tenant_id=tenant.id, is_daily=True).one()


def make_user(db, tenant: Tenant, role_code: str = "receptionist", email: str | None = None,
              password: str | None = None, is_active: bool = True) -> User:
    user = User(
        tenant_id=tenant.id,
        email=(email or f"user{next(_seq)}@example.com").lower(),
        name="Test User",
        hashed_password=hash_password(password) if password else _default_password_hash(),
        role_code=role_code,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    return user


def make_session(db, user: User, **fields) -> tuple[str, UserSession]:
    """A live session row without going through /auth/login. Returns (raw token, row)."""
    token = generate_token()
    fields.setdefault("expires_at", get_token_expiry())
    session = UserSession(user_id=user.id, token_hash=hash_token(token), **fields)
    db.add(session)
    db.flush()
    return token, session


def log_in(client, db, user: User) -> str:
    """Put a live session cookie for `user` on the test client."""
    token, _ = make_session(db, user)
    client.cookies.set("access_token", token)
    return token


def add_override(db, user: User, permission_code: str, effect: str) -> UserPermissionOverride:
    override = UserPermissionOverride(
        tenant_id=user.tenant_id, user_id=user.id, permission_code=permission_code, effect=effect,
    )
    db.add(override)
    db.flush()
    return override


def make_plan(db, tenant: Tenant, name: str | None = None, period_hours: int = 2,
              grace_minutes: int = 60, is_active: bool = True) -> StayPlan:
    """A non-daily plan (default: the beta lodge's fresh-up, 2h + 60 min grace)."""
    plan = StayPlan(tenant_id=tenant.id, name=name or f"Plan {next(_seq)}", period_hours=period_hours,
                    grace_minutes=grace_minutes, is_active=is_active)
    db.add(plan)
    db.flush()
    return plan


def make_room_type(db, tenant: Tenant, capacity: int = 2, daily_price: str = "1000.00",
                   extra_rates: dict[tuple[int, int], str] | None = None) -> RoomType:
    """Room type with a complete daily-plan rate set (1..capacity).

    extra_rates: {(stay_plan_id, occupancy): price} for other plans.
    """
    room_type = RoomType(tenant_id=tenant.id, name=f"Type {next(_seq)}", capacity=capacity)
    db.add(room_type)
    db.flush()
    plan = daily_plan(db, tenant)
    for occ in range(1, capacity + 1):
        db.add(RoomTypeRate(
            tenant_id=tenant.id, room_type_id=room_type.id, stay_plan_id=plan.id,
            occupancy=occ, price=Decimal(daily_price),
        ))
    for (plan_id, occ), price in (extra_rates or {}).items():
        db.add(RoomTypeRate(
            tenant_id=tenant.id, room_type_id=room_type.id, stay_plan_id=plan_id,
            occupancy=occ, price=Decimal(price),
        ))
    db.flush()
    return room_type


def make_room(db, tenant: Tenant, room_type: RoomType | None = None, number: str | None = None) -> Room:
    room_type = room_type or make_room_type(db, tenant)
    room = Room(tenant_id=tenant.id, room_type_id=room_type.id, room_number=number or str(100 + next(_seq)))
    db.add(room)
    db.flush()
    return room


def make_guest(db, tenant: Tenant, phone: str | None = None) -> Guest:
    guest = Guest(tenant_id=tenant.id, full_name="Test Guest", phone=phone or f"98{next(_seq):08d}")
    db.add(guest)
    db.flush()
    return guest


def make_stay(db, tenant: Tenant, created_by: User, room: Room | None = None,
              check_in_at: datetime | None = None, with_folio: bool = True,
              plan: StayPlan | None = None) -> Stay:
    """Bare stay row (no posting), on the daily plan unless `plan` is given."""
    room = room or make_room(db, tenant)
    plan = plan or daily_plan(db, tenant)
    stay = Stay(
        tenant_id=tenant.id, room_id=room.id, guest_id=make_guest(db, tenant).id,
        stay_plan_id=plan.id, actual_check_in_at=check_in_at or datetime(2026, 11, 1, 12, tzinfo=timezone.utc),
        agreed_price=Decimal("1000.00"), listed_price=Decimal("1000.00"), occupancy=1,
        period_hours=plan.period_hours,
        grace_minutes=plan.grace_minutes, created_by_user_id=created_by.id,
    )
    db.add(stay)
    db.flush()
    if with_folio:
        db.add(Folio(tenant_id=tenant.id, stay_id=stay.id))
        db.flush()
    return stay
