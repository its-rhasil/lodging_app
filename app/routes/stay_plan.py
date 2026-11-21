"""Stay plans. Reading needs room.view (the check-in screen lists them); changes need inventory.manage."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_permission
from app.core.principal import Principal
from app.core.request_context import RequestMeta, get_request_meta
from app.database import get_db
from app.schemas.stay_plan import StayPlanCreate, StayPlanOut, StayPlanUpdate
from app.service import stay_plan_service

router = APIRouter(prefix="/stay-plans", tags=["stay-plans"])
can_view = require_permission("room.view")
can_manage = require_permission("inventory.manage")


@router.get("", response_model=list[StayPlanOut])
def list_stay_plans(principal: Principal = Depends(can_view), db: Session = Depends(get_db)):
    return stay_plan_service.list_plans(db, principal)


@router.post("", response_model=StayPlanOut, status_code=201)
def create_stay_plan(payload: StayPlanCreate, principal: Principal = Depends(can_manage),
                     db: Session = Depends(get_db), meta: RequestMeta = Depends(get_request_meta)):
    return stay_plan_service.create_plan(db, principal, meta=meta, **payload.model_dump())


@router.delete("/{plan_id}", status_code=204)
def delete_stay_plan(plan_id: int, principal: Principal = Depends(can_manage),
                     db: Session = Depends(get_db), meta: RequestMeta = Depends(get_request_meta)):
    stay_plan_service.delete_plan(db, principal, plan_id, meta=meta)


@router.patch("/{plan_id}", response_model=StayPlanOut)
def update_stay_plan(plan_id: int, payload: StayPlanUpdate, principal: Principal = Depends(can_manage),
                     db: Session = Depends(get_db), meta: RequestMeta = Depends(get_request_meta)):
    return stay_plan_service.update_plan(db, principal, plan_id, payload.model_dump(exclude_unset=True),
                                         meta=meta)
