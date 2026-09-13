from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.database import get_db
from app.models.user import User
from app.models.session import UserSession
from app.core.security import hash_token


def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if token is None:
        raise HTTPException(status_code=401, detail="Not Authenticated")
    hashed_token = hash_token(token)
    session = db.query(UserSession).filter(UserSession.token_hash == hashed_token).first()

    if session is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    if session.revoked:
        raise HTTPException(status_code=401, detail="Session revoked")
    if session.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session Expired")

    user = db.query(User).filter(User.id == session.user_id, User.is_active == True).first()

    if user is None:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user