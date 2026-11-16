"""Superadmin login (DL-P07). Separate cookie and session table from tenant staff."""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.cookies import PLATFORM_SESSION_COOKIE, clear_session_cookie, set_session_cookie
from app.core.deps import require_platform_user
from app.core.principal import Principal
from app.core.request_context import RequestMeta, get_request_meta
from app.database import get_db
from app.schemas.auth import LoginRequest
from app.schemas.platform import PlatformMeResponse
from app.service import platform_service

router = APIRouter(prefix="/platform/auth", tags=["platform"])


@router.post("/login", response_model=PlatformMeResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db),
          meta: RequestMeta = Depends(get_request_meta)):
    token, user = platform_service.login(db, email=payload.email, password=payload.password, meta=meta)
    set_session_cookie(response, token, name=PLATFORM_SESSION_COOKIE)
    return platform_service.profile(db, user.id)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db),
           meta: RequestMeta = Depends(get_request_meta)):
    platform_service.logout(db, token=request.cookies.get(PLATFORM_SESSION_COOKIE), meta=meta)
    clear_session_cookie(response, name=PLATFORM_SESSION_COOKIE)


@router.get("/me", response_model=PlatformMeResponse)
def me(principal: Principal = Depends(require_platform_user), db: Session = Depends(get_db)):
    return platform_service.profile(db, principal.user_id)
