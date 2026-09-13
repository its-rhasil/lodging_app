from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.schemas.room import RoomCreate, RoomResponse
from app.service import room_service
from app.models.user import User

router = APIRouter(prefix="/rooms", tags=["rooms"], dependencies=[Depends(get_current_user)])


router.post("/",response_model=RoomResponse)
def create_room(payload: RoomCreate, db: Session, current_user: User = Depends(get_current_user)):
    return room_service.create_room(
        db = db,
        tenant_id= current_user.tenant_id,
        room_type_id= payload.room_type_id,
        room_number= payload.room_number
    )