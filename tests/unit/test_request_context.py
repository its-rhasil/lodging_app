from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.request_context import (
    REQUEST_ID_HEADER, RequestMeta, clean_ip, get_request_meta, request_id_middleware,
)


def _app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(request_id_middleware)

    @app.get("/meta")
    def meta(m: RequestMeta = Depends(get_request_meta)):
        return {"request_id": m.request_id, "ip": m.ip, "user_agent": m.user_agent}

    return app


def test_request_id_is_generated_and_echoed():
    res = TestClient(_app()).get("/meta")
    rid = res.headers[REQUEST_ID_HEADER]
    assert len(rid) == 32
    assert res.json()["request_id"] == rid


def test_plain_client_request_id_is_kept_and_odd_one_replaced():
    client = TestClient(_app())
    assert client.get("/meta", headers={REQUEST_ID_HEADER: "abc-123"}).json()["request_id"] == "abc-123"
    replaced = client.get("/meta", headers={REQUEST_ID_HEADER: "bad id; drop table"}).json()["request_id"]
    assert replaced != "bad id; drop table"


def test_user_agent_is_truncated():
    res = TestClient(_app()).get("/meta", headers={"user-agent": "x" * 2000})
    assert len(res.json()["user_agent"]) == 512


def test_clean_ip_accepts_addresses_and_rejects_names():
    assert clean_ip("203.0.113.7") == "203.0.113.7"
    assert clean_ip("::1") == "::1"
    assert clean_ip("testclient") is None  # TestClient's fake host would break the INET column
    assert clean_ip(None) is None
