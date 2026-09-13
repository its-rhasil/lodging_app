from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.service.dashboard import build_dashboard
from app.models.user import User
from app.schemas.dashboard import DashboardResponse

router = APIRouter(prefix=["dashboard"], tags=["dashboard"], dependencies=Depends(get_current_user))

router.get("/",response_model=DashboardResponse)
def read_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return build_dashboard(db=db, tenant_id=current_user.tenant_id)