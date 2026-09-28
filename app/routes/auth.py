from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.models.user import User
from app.database import get_db
from app.core.deps import get_current_user
from app.service import auth_service
from app.schemas.auth import LoginRequest, SignupRequest, SignupResponse, RegisterRequest, RegisterResponse, UserResponse

router = APIRouter(prefix="/auth",tags=["auth"])#, dependencies=[Depends(get_current_user)])

@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    try:
        user = auth_service.authenticate(db=db, email= payload.email, password=payload.password)
        if user is None:
            raise HTTPException(status_code=401, detail = "Invalid Email/Password")
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    token = auth_service.create_session(db, user)
    response.set_cookie(
        key = "access_token",
        value = token,
        httponly = True,
        secure = False, # SET To False in development
        samesite = "lax",
        max_age= 60 * 60 * 24 * 7
    )
    return {"Detail": "Logged in"}

@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if token is not None:
        auth_service.logout(db = db, token=token)

    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=False,
        samesite="lax"
    )
    return {"detail": "Logged out successfully!"}

@router.post("/signup-tenant",response_model= SignupResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    try:
        tenant, admin = auth_service.signup_tenant(
            db = db, 
            tenant_name= payload.tenant_name, 
            admin_email=payload.admin_email, 
            admin_phone= payload.admin_phone,
            admin_password=payload.admin_password,
            address = payload.address,
            name= payload.name
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "tenant_id": admin.tenant_id,
        "tenant_name": tenant.name,
        "user_id": admin.id,
        "name": admin.name,
        "email": admin.email,
        "address": tenant.address,
    }

@router.post("/register", response_model=RegisterResponse)
def signup(payload: RegisterRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        user = auth_service.register(
            db=db,
            email = payload.email, 
            password=payload.password, 
            role = payload.role,
            name=payload.name,
            acting_user= current_user
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return user

@router.get("/users",response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        return auth_service.list_users(
            db = db,
            acting_user= current_user
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

@router.patch("/{user_id}/deactivate", response_model=UserResponse)
def deactivate(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        return auth_service.deactivate(db = db, acting_user= current_user, target_user_id= user_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))