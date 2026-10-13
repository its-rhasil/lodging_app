from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.service import room_type_service
from app.crud.room_type import list_room_types, list_room_types_without_price
from app.models.user import User
from app.schemas.room_type import RoomtypeCreate, RoomTypeResponse, RoomTypeUpdate, RoomTypeResponseWP
from app.core.deps import get_current_user, require_role
from app.database import get_db

router = APIRouter(prefix="/room-type", tags=["room-type"], dependencies=[Depends(get_current_user)])

@router.post("/", response_model=RoomTypeResponse, status_code=201)
def create_room_type(payload: RoomtypeCreate, db: Session = Depends(get_db), current_user: User = Depends(require_role("admin"))):
    return room_type_service.add_room_type(
        db = db,
        tenant_id=current_user.tenant_id,
        name = payload.name,
        description= payload.description,
        capacity=payload.capacity,
        prices = [(p.occupancy, p.price) for p in payload.prices],
    )

@router.get("/", response_model = list[RoomTypeResponse])
def list_room_type(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return list_room_types(db = db, tenant_id= current_user.tenant_id)

@router.get("/room_type", response_model = list[RoomTypeResponseWP])
def list_room_type(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return list_room_types_without_price(db = db, tenant_id= current_user.tenant_id)

@router.patch("/{room_type_id}",response_model=RoomTypeResponse)
def update_room_type(room_type_id: int,payload: RoomTypeUpdate,db: Session = Depends(get_db),current_user: User = Depends(require_role("admin"))):
    try:

        return room_type_service.update_room_type(
            db=db,
            room_type_id=room_type_id,
            tenant_id=current_user.tenant_id,
            name=payload.name,
            description=payload.description,
            capacity=payload.capacity,
            prices=payload.prices
        )

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )