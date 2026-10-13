from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.stay import StayOut, CheckInRequest, ExtendStayRequest, CheckoutResponse, CheckInPreview, ChangeRoomPreview, ChangeRoomResult, ConfirmRoomChangeRequest
from app.models.user import User
from app.service.stay_service import check_in, extend_stay, check_out, preview_check_in, preview_room_change, confirm_room_change
from app.core.deps import get_current_user
from app.database import get_db

router = APIRouter(prefix="/stay", tags=["stay"], dependencies=[Depends(get_current_user)])

@router.post("/",response_model = StayOut)
def check_in_endpoint(payload: CheckInRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return check_in(
        db = db, 
        tenant_id= current_user.tenant_id,
        room_id = payload.room_id,
        guest_full_name= payload.guest_full_name,
        guest_phone = payload.guest_phone,
        guest_email= payload.guest_email,
        guest_address= payload.guest_address,
        stay_hours= payload.stay_hours,
        occupancy= payload.occupancy,
        agreed_price= payload.agreed_price,
        actual_check_in_at= payload.actual_check_in_at
    )

@router.get("/check-in/preview", response_model=CheckInPreview)
def preview_check_in_endpoint(
    room_id: int,
    occupancy: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return preview_check_in(db, tenant_id=current_user.tenant_id, room_id=room_id, occupancy=occupancy)


@router.patch("/{stay_id}/extend", response_model=StayOut)
def extend_stay_endpoint(
    stay_id: int,
    payload: ExtendStayRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return extend_stay(db, tenant_id=current_user.tenant_id, stay_id=stay_id, new_expected_checkout_at=payload.new_expected_checkout_at)

@router.patch("/{stay_id}/checkout", response_model=CheckoutResponse)
def checkout_endpoint(
    stay_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return check_out(db, tenant_id=current_user.tenant_id, stay_id=stay_id, force=force)

@router.get("/{stay_id}/change-room/preview", response_model=ChangeRoomPreview)
def preview_room_change_endpoint(
    stay_id: int,
    new_room_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return preview_room_change(db, tenant_id=current_user.tenant_id, stay_id=stay_id, new_room_id=new_room_id)


@router.patch("/{stay_id}/change-room/confirm", response_model=ChangeRoomResult)
def confirm_room_change_endpoint(
    stay_id: int,
    payload: ConfirmRoomChangeRequest,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return confirm_room_change(
        db,
        tenant_id=current_user.tenant_id,
        stay_id=stay_id,
        new_room_id=payload.new_room_id,
        final_price=payload.final_price,
        force=force,
    )