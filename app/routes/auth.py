"""Tenant staff login. Public signup is gone: tenants are created with the CLI (DL-R03)."""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.cookies import TENANT_SESSION_COOKIE, clear_session_cookie, set_session_cookie
from app.core.deps import get_current_principal
from app.core.principal import Principal
from app.core.request_context import RequestMeta, get_request_meta
from app.database import get_db
from app.schemas.auth import LoginRequest, MeResponse
from app.service import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=MeResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db),
          meta: RequestMeta = Depends(get_request_meta)):
    token, user = auth_service.login(db, email=payload.email, password=payload.password, meta=meta)
    set_session_cookie(response, token)
    return auth_service.profile(db, user.id)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db),
           meta: RequestMeta = Depends(get_request_meta)):
    auth_service.logout(db, token=request.cookies.get(TENANT_SESSION_COOKIE), meta=meta)
    clear_session_cookie(response)


@router.get("/me", response_model=MeResponse)
def me(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)):
    return auth_service.profile(db, principal.user_id, principal.permissions)
