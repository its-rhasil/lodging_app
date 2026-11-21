"""Authorization matrix (testing-strategy.md §8): every guarded tenant route x every role.

Generated from app.main.ROUTERS, so a new route is covered automatically.
- Role holds the permission  -> anything but 401/403 (it may be 404/422: dummy ids and bodies).
- Role lacks the permission  -> 403.
The permission check runs before path/body validation, so dummy ids and an empty body are enough.
"""
import re

import pytest
from fastapi.routing import APIRoute

from app.core.permissions import ROLE_PERMISSIONS
from app.main import ROUTERS
from tests.factories import log_in, make_tenant, make_user

DUMMY_ID = "999999"


def _required_permission(route: APIRoute) -> str | None:
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        code = getattr(dep.call, "required_permission", None)
        if code:
            return code
        stack.extend(dep.dependencies)
    return None


def _guarded_routes():
    for router in ROUTERS:
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            code = _required_permission(route)
            if code is None:
                continue
            for method in route.methods:
                yield method, route.path, code


CASES = [
    (role, method, path, code)
    for method, path, code in sorted(_guarded_routes())
    for role in sorted(ROLE_PERMISSIONS)
]


def test_matrix_covers_routes():
    assert len(CASES) > 60  # guard against walking nothing


@pytest.mark.parametrize("role,method,path,code", CASES, ids=lambda v: str(v))
def test_role_can_call_route_only_with_the_permission(db, client, role, method, path, code):
    tenant = make_tenant(db)
    log_in(client, db, make_user(db, tenant, role_code=role))
    db.commit()

    url = re.sub(r"\{[^}]+\}", DUMMY_ID, path)
    res = client.request(method, url, json={})

    if code in ROLE_PERMISSIONS[role]:
        assert res.status_code not in (401, 403), f"{role} should reach {method} {path}: {res.json()}"
    else:
        assert res.status_code == 403, f"{role} must not reach {method} {path} (needs {code})"
        assert res.json()["details"]["permission"] == code
