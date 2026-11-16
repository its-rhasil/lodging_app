from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.request_context import request_id_middleware
from app.database import get_db
from app.routes import auth, platform_auth, users
# Detached until rebuilt on the M1 models (Day 2-3): dashboard, room_type, room, stay, payment.
# They still use the pre-beta schema (User.role, Payment, RoomTypePrice) and no longer import.


app = FastAPI()
register_error_handlers(app)
app.middleware("http")(request_id_middleware)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=[settings.frontend_origin],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
# Every router goes through this tuple: tests/unit/test_route_guards.py inspects it.
ROUTERS = (auth.router, users.router, platform_auth.router)
for _router in ROUTERS:
    app.include_router(_router)

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1"))
    return {"status": "connected", "result": result.scalar()}