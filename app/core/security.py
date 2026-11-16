import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from email_validator import EmailNotValidError, validate_email
from passlib.context import CryptContext

from app.core.config import settings
from app.core.errors import ValidationFailed

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

PASSWORD_MIN_LENGTH = 8
# bcrypt only uses the first 72 bytes; refuse longer passwords instead of silently cutting them.
PASSWORD_MAX_BYTES = 72


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    """Emails are stored and compared lowercase (DL-P06)."""
    return email.strip().lower()


def validate_email_address(email: str) -> str:
    """For input that doesn't pass through a Pydantic EmailStr (the CLI). Returns it normalised."""
    try:
        validate_email(email.strip(), check_deliverability=False)
    except EmailNotValidError as exc:
        raise ValidationFailed(f"Invalid email address: {exc}", code="invalid_email") from exc
    return normalize_email(email)


def validate_new_password(password: str) -> None:
    """Rules for a password being set (not for checking one at login)."""
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValidationFailed(
            f"Password must be at least {PASSWORD_MIN_LENGTH} characters.", code="password_too_short",
        )
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise ValidationFailed("Password is too long.", code="password_too_long")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)


@lru_cache
def dummy_password_hash() -> str:
    """A real bcrypt hash of a random value. Login verifies against it when the email
    is unknown, so an unknown email takes as long as a wrong password."""
    return hash_password(secrets.token_urlsafe(16))


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def get_token_expiry() -> datetime:
    return utcnow() + timedelta(minutes=settings.session_expires_minutes)
