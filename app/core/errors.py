"""Domain exceptions and the global error handlers (DL-P02, P2-1, P2-2).

Pattern ("one commit per use case"):
- Services validate, raise a DomainError subclass when a rule fails, and call
  db.commit() exactly once at the end. CRUD/repository functions only add/flush.
- Routes don't catch anything. The handlers below turn every error into
  JSON of one shape: {"code": ..., "message": ..., "details": ...}.
- If a DB constraint fires at flush/commit, the IntegrityError handler maps
  the constraint name to a 409 with a stable code. get_db() rolls back.
"""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class DomainError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, details: Any = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details = details


class NotAuthenticated(DomainError):
    status_code = 401
    code = "not_authenticated"


class PermissionDenied(DomainError):
    status_code = 403
    code = "permission_denied"


class NotFound(DomainError):
    status_code = 404
    code = "not_found"


class Conflict(DomainError):
    status_code = 409
    code = "conflict"


class ValidationFailed(DomainError):
    status_code = 422
    code = "validation_failed"


# Constraint name -> (error code, message). Names match the models (data-model.md).
CONSTRAINT_ERRORS: dict[str, tuple[str, str]] = {
    "uq_users_email": ("email_taken", "This email is already registered."),
    "uq_platform_users_email": ("email_taken", "This email is already registered."),
    "uq_one_tenant_admin": ("tenant_admin_exists", "This tenant already has a tenant admin."),
    "uq_room_type_name_per_tenant": ("room_type_name_taken", "A room type with this name already exists."),
    "uq_room_number_per_tenant": ("room_number_taken", "A room with this number already exists."),
    "uq_stay_plan_name": ("stay_plan_name_taken", "A stay plan with this name already exists."),
    "uq_one_daily_plan": ("daily_plan_exists", "This tenant already has a daily plan."),
    "uq_rate": ("rate_exists", "A rate for this plan and occupancy already exists."),
    "uq_one_active_stay_per_room": ("room_occupied", "This room already has an active stay."),
    "uq_folio_posting_key": ("duplicate_posting", "This transaction was already recorded."),
    "uq_one_reversal_per_txn": ("already_reversed", "This transaction was already reversed."),
}


def _body(code: str, message: str, details: Any = None) -> dict:
    return {"code": code, "message": message, "details": details}


def _constraint_name(exc: IntegrityError) -> str | None:
    diag = getattr(exc.orig, "diag", None)  # psycopg2 exposes the violated constraint here
    return getattr(diag, "constraint_name", None)


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=_body(exc.code, exc.message, exc.details))


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    name = _constraint_name(exc)
    if name in CONSTRAINT_ERRORS:
        code, message = CONSTRAINT_ERRORS[name]
    else:
        # Unmapped constraint: still a 409, but log it so it gets a proper mapping/validation.
        logger.warning("Unmapped integrity error on constraint %r", name)
        code, message = "conflict", "The request conflicts with existing data."
    return JSONResponse(status_code=409, content=_body(code, message, {"constraint": name}))


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Legacy HTTPException raises and framework 404/405s get the same body shape.
    codes = {401: "not_authenticated", 403: "permission_denied", 404: "not_found",
             405: "method_not_allowed", 409: "conflict"}
    return JSONResponse(
        status_code=exc.status_code,
        content=_body(codes.get(exc.status_code, "http_error"), str(exc.detail)),
        headers=getattr(exc, "headers", None),
    )


async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"loc": list(err.get("loc", ())), "msg": err.get("msg"), "type": err.get("type")}
        for err in exc.errors()
    ]
    return JSONResponse(status_code=422, content=_body("invalid_request", "Request validation failed.", details))


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content=_body("internal_error", "Something went wrong."))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
