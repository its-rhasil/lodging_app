from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.service import room_type_service
from app.crud import room_type
from app.models.user import User
from app.schemas.room_type import RoomtypeCreate, RoomTypeResponse
from app.core.deps import get_current_user
from app.database import get_db

router = APIRouter(prefix=["/room-type"], tags=["room-type"], dependencies=[Depends(get_current_user)])

router.post("/room-type", response_model=RoomTypeResponse)
def create_room_type(payload: RoomtypeCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return room_type_service.add_room_type(
        db = db,
        tenant_id=current_user.tenant_id,
        name = payload.name,
        description= payload.description,
        default_price= payload.default_price,
        capacity=payload.capacity
    )

router.get("/", response_model = RoomTypeResponse)
def list_room_type(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return room_type.list_room_type(db = db, tenant_id= current_user.tenant_id)

