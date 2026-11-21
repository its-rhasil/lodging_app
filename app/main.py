from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.request_context import request_id_middleware
from app.database import get_db
from app.routes import (
    audit, auth, dashboard, folio, guest, platform_auth, room, room_type, settings as settings_routes,
    stay, stay_plan, users,
)


app = FastAPI()
register_error_handlers(app)
app.middleware("http")(request_id_middleware)
if settings.frontend_origin:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
# Every router goes through this tuple: tests/unit/test_route_guards.py inspects it.
ROUTERS = (
    auth.router, users.router, platform_auth.router,
    stay_plan.router, room_type.router, room.router,
    guest.router, stay.router, folio.router,
    dashboard.router, audit.router, settings_routes.router,
)
for _router in ROUTERS:
    app.include_router(_router)


@app.get("/health")
@app.head("/health")
def health_check(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1"))
    return {"status": "connected", "result": result.scalar()}