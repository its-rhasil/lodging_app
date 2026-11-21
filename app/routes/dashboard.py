"""Room grid. Loading it posts due room charges for the guests shown (DL-R21)."""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.clock import get_now
from app.core.deps import require_permission
from app.core.principal import Principal
from app.database import get_db
from app.schemas.dashboard import DashboardOut
from app.service import dashboard

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def read_dashboard(principal: Principal = Depends(require_permission("dashboard.view")),
                   db: Session = Depends(get_db), now: datetime = Depends(get_now)):
    return dashboard.build_dashboard(db, principal, now=now)
