"""Guests (P6-1, DL-P05): phone normalisation, lookup by phone, creation at check-in.

Reuse is explicit (owner, 2026-11-16): the check-in screen looks guests up by phone and
sends guest_id to reuse one; without guest_id, check-in creates a new guest. A shared
family phone therefore never attaches the wrong name.
"""
import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound, ValidationFailed
from app.core.principal import Principal
from app.models import Guest

INDIA_PREFIX = "+91"
_ALLOWED = re.compile(r"^\+?[\d\s\-().]+$")  # digits plus common separators, optional leading '+'
MIN_DIGITS, MAX_DIGITS = 7, 15               # E.164 allows at most 15 digits
LOOKUP_LIMIT = 20


def normalize_phone(raw: str) -> str:
    """India default (owner, 2026-11-16).

    Without '+': 10 digits, '0' + 10 digits, or '91' + 10 digits -> '+91XXXXXXXXXX'.
    With '+': '+' followed by the digits, as typed (e.g. '+44...').
    Anything else: the digits only. Must have 7-15 digits.
    """
    text = (raw or "").strip()
    if not text or not _ALLOWED.match(text):
        raise ValidationFailed("Enter a valid phone number.", code="invalid_phone")
    digits = re.sub(r"\D", "", text)
    if not MIN_DIGITS <= len(digits) <= MAX_DIGITS:
        raise ValidationFailed("Enter a valid phone number.", code="invalid_phone")

    if text.startswith("+"):
        return "+" + digits
    if len(digits) == 10:
        return INDIA_PREFIX + digits
    if len(digits) == 11 and digits.startswith("0"):
        return INDIA_PREFIX + digits[1:]
    if len(digits) == 12 and digits.startswith("91"):
        return "+" + digits
    return digits


def find_by_phone(db: Session, principal: Principal, phone: str) -> list[Guest]:
    """This tenant's guests with this phone (normalised), newest first."""
    return list(db.scalars(
        select(Guest)
        .where(Guest.tenant_id == principal.tenant_id, Guest.phone == normalize_phone(phone))
        .order_by(Guest.created_at.desc(), Guest.id.desc())
        .limit(LOOKUP_LIMIT)
    ))


def search(db: Session, principal: Principal, text: str) -> list[Guest]:
    """Guest search (Day 3): name contains the text, or phone contains its digits. Newest first."""
    text = (text or "").strip()
    if len(text) < 2:
        raise ValidationFailed("Type at least 2 characters.", code="search_too_short")
    conditions = [Guest.full_name.ilike(f"%{text}%")]
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 3:
        conditions.append(Guest.phone.contains(digits))
    return list(db.scalars(
        select(Guest)
        .where(Guest.tenant_id == principal.tenant_id, or_(*conditions))
        .order_by(Guest.created_at.desc(), Guest.id.desc())
        .limit(LOOKUP_LIMIT)
    ))


def get_guest(db: Session, tenant_id: int, guest_id: int) -> Guest:
    """A guest of this tenant. Another tenant's guest is reported as not found."""
    guest = db.scalars(select(Guest).where(Guest.tenant_id == tenant_id, Guest.id == guest_id)).first()
    if guest is None:
        raise NotFound("Guest not found.", code="guest_not_found")
    return guest


def create_guest(db: Session, tenant_id: int, *, full_name: str, phone: str,
                 email: str | None = None, address: str | None = None) -> Guest:
    """Adds and flushes only: check-in commits it (and audits it) together with the stay."""
    full_name = (full_name or "").strip()
    if not full_name:
        raise ValidationFailed("Guest name is required.", code="field_required", details={"field": "full_name"})
    guest = Guest(
        tenant_id=tenant_id, full_name=full_name, phone=normalize_phone(phone),
        email=(email or "").strip().lower() or None, address=(address or "").strip() or None,
    )
    db.add(guest)
    db.flush()
    return guest
