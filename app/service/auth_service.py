from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.models.user import User
from app.models.session import UserSession
from app.models.tenant import Tenant
from app.core.security import hash_password, verify_password, generate_token, hash_token, get_token_expiry

def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.query(User).filter(User.email == email).first()

    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if user.is_active == False:
        raise ValueError("Account Deactivated")

    return user

def create_session(db: Session, user: User) -> str:
    raw_token = generate_token()
    session = UserSession(
        user_id = user.id,
        token_hash = hash_token(raw_token),
        expires_at = get_token_expiry()
    )
    db.add(session)
    db.commit()
    return raw_token

def signup_tenant(db: Session, tenant_name: str, admin_email: str, admin_phone: str, admin_password: str, address: str, name: str) -> User:
    existing = db.query(User).filter(User.email == admin_email).first()
    if existing:
        raise ValueError("Email already registered!")

    tenant = Tenant(name = tenant_name, contact_email= admin_email, contact_phone= admin_phone, address=address)
    db.add(tenant)
    db.flush()

    admin = User(
        tenant_id = tenant.id,
        email = admin_email,
        name = name,
        hashed_password = hash_password(admin_password),
        role = "admin",
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return tenant, admin

def register(db: Session, email: str, password: str, role: str, name: str, acting_user: User) -> User:
    if acting_user.role != "admin":
        raise PermissionError("Access Denied!")
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise ValueError("Email already registered!")

    user = User(
        tenant_id = acting_user.tenant_id, email = email, hashed_password= hash_password(password), role = role, name = name
        )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def deactivate(db: Session, acting_user: User, target_user_id: int):
    if acting_user.role != "admin":
        raise PermissionError("Acesss Denied!")

    target = db.query(User).filter(User.id == target_user_id, User.tenant_id == acting_user.tenant_id).first()
    if target is None:
        raise ValueError("User not found!")
    if target.id == acting_user.id:
        raise  ValueError("Owner can't deactivate themselves!")

    target.is_active = False

    db.query(UserSession).filter(
        UserSession.user_id == target.id,
        UserSession.revoked_at.is_(None),
    ).update(
        {"revoked_at": datetime.now(timezone.utc)},
        synchronize_session=False,
    )
    db.commit()
    return target

def logout(db: Session, token: str):
    token_hash = hash_token(token)
    session = db.query(UserSession).filter(
        UserSession.token_hash == token_hash, UserSession.revoked_at.is_(None)
        ).first()
    if session is not None:
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()

def list_users(db: Session, acting_user: User):
    if acting_user.role != "admin":
        raise PermissionError("Access Denied!")

    return db.query(User).filter(User.tenant_id == acting_user.tenant_id).all()