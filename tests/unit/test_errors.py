from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app.core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed, register_error_handlers


def _integrity(constraint: str | None) -> IntegrityError:
    orig = Exception("boom")
    orig.diag = SimpleNamespace(constraint_name=constraint)
    return IntegrityError("INSERT ...", {}, orig)


class Payload(BaseModel):
    amount: int


app = FastAPI()
register_error_handlers(app)


@app.get("/raise/{kind}")
def raise_(kind: str):
    errors = {
        "not_found": NotFound("Room not found."),
        "conflict": Conflict("Room busy.", code="room_busy", details={"room_id": 1}),
        "denied": PermissionDenied("Missing permission."),
        "invalid": ValidationFailed("Bad occupancy."),
        "integrity_known": _integrity("uq_room_number_per_tenant"),
        "integrity_unknown": _integrity("some_new_constraint"),
        "http": HTTPException(status_code=404, detail="Legacy not found"),
        "crash": RuntimeError("secret internals"),
    }
    raise errors[kind]


@app.post("/validate")
def validate(payload: Payload):
    return payload


client = TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "kind,status,code",
    [
        ("not_found", 404, "not_found"),
        ("conflict", 409, "room_busy"),
        ("denied", 403, "permission_denied"),
        ("invalid", 422, "validation_failed"),
        ("http", 404, "not_found"),
    ],
)
def test_errors_map_to_status_and_stable_code(kind, status, code):
    r = client.get(f"/raise/{kind}")
    assert r.status_code == status
    body = r.json()
    assert body["code"] == code
    assert set(body) == {"code", "message", "details"}


def test_domain_error_details_are_returned():
    assert client.get("/raise/conflict").json()["details"] == {"room_id": 1}


def test_known_constraint_maps_to_409_with_its_code():
    r = client.get("/raise/integrity_known")
    assert r.status_code == 409
    assert r.json()["code"] == "room_number_taken"


def test_unknown_constraint_is_a_generic_409():
    r = client.get("/raise/integrity_unknown")
    assert r.status_code == 409
    assert r.json()["code"] == "conflict"


def test_request_validation_has_field_path():
    r = client.post("/validate", json={"amount": "abc"})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "invalid_request"
    assert body["details"][0]["loc"] == ["body", "amount"]


def test_unhandled_error_hides_internals():
    r = client.get("/raise/crash")
    assert r.status_code == 500
    assert r.json()["code"] == "internal_error"
    assert "secret" not in r.text
