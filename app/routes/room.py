from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.crud.stay import get_stay_history
from app.schemas.room import RoomCreate, RoomResponse, RoomDetail, RoomStatusUpdate, RoomOut
from app.schemas.stay import StayHistoryEntry
from app.service import room_service
from app.service.payment_service import get_billing_summary
from app.models.user import User

router = APIRouter(prefix="/rooms", tags=["rooms"], dependencies=[Depends(get_current_user)])


@router.post("/",response_model=RoomResponse)
def create_room(payload: RoomCreate, db: Session = Depends(get_db), current_user: User = Depends(require_role("admin"))):
    try:
        return room_service.create_room(
            db = db,
            tenant_id= current_user.tenant_id,
            room_type_id= payload.room_type_id,
            room_number= payload.room_number
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{room_id}", response_model=RoomDetail)
def get_room_detail_endpoint(
    room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return room_service.get_room_detail(db, tenant_id=current_user.tenant_id, room_id=room_id)

@router.get("/{room_id}/stays", response_model=list[StayHistoryEntry])
def get_room_stay_history(
    room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    stays = get_stay_history(db, current_user.tenant_id, room_id)
    return [
        StayHistoryEntry(
            guest_name=s.guest.full_name,
            actual_check_in_at=s.actual_check_in_at,
            actual_checkout_at=s.actual_checkout_at,
            agreed_price=s.agreed_price,
            billing = get_billing_summary(db, current_user.tenant_id, s)
        )
        for s in stays
    ]

@router.patch("/{room_id}/status", response_model=RoomOut)
def update_room_status_endpoint(
    room_id: int,
    payload: RoomStatusUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return room_service.update_room_status(db, tenant_id=current_user.tenant_id, room_id=room_id, new_status=payload.operational_status)