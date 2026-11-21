"""Architecture test (architecture.md §6.4): no route ships without an authorization guard.

A route passes if its dependency tree contains require_permission(...) or
require_platform_user, or it is on one of the two short allow-lists below.

Routes are read from app.main.ROUTERS (FastAPI doesn't expose included routes
publicly), and a second test checks that list covers everything the app serves.
"""
from fastapi.routing import APIRoute

from app.core.deps import get_current_principal
from app.main import ROUTERS, app

# No login needed.
PUBLIC = {
    ("GET", "/health"),
    ("HEAD", "/health"),  # uptime monitors
    ("POST", "/auth/login"),
    ("POST", "/auth/logout"),
    ("POST", "/platform/auth/login"),
    ("POST", "/platform/auth/logout"),
}
# Logged in, but about yourself only: no permission code applies.
SELF_ONLY = {
    ("GET", "/auth/me"),
}


def _calls(dependant):
    for dep in dependant.dependencies:
        yield dep.call
        yield from _calls(dep)


def _guard(route: APIRoute) -> str | None:
    for call in _calls(route.dependant):
        if getattr(call, "required_permission", None):
            return f"permission:{call.required_permission}"
        if getattr(call, "platform_guard", False):
            return "platform"
        if call is get_current_principal:
            return "authenticated"
    return None


def _routes():
    for router in (app.router, *ROUTERS):
        for route in router.routes:
            if isinstance(route, APIRoute):
                for method in route.methods:
                    yield method, route.path, route


def test_inspected_routes_are_everything_the_app_serves():
    served = {(method.upper(), path) for path, ops in app.openapi()["paths"].items() for method in ops}
    inspected = {(m, p) for m, p, _ in _routes()}
    assert served == inspected, "a router was included without being added to app.main.ROUTERS"
    assert len(inspected) > 5  # guard against walking nothing


def test_every_route_has_a_guard_or_is_allow_listed():
    unguarded = []
    for method, path, route in _routes():
        guard = _guard(route)
        key = (method, path)
        if key in PUBLIC:
            continue
        if key in SELF_ONLY:
            assert guard is not None, f"{method} {path} must at least require a login"
            continue
        if guard is None or guard == "authenticated":
            unguarded.append(f"{method} {path}")
    assert unguarded == [], f"Routes without require_permission/require_platform_user: {unguarded}"


def test_allow_lists_have_no_stale_entries():
    existing = {(m, p) for m, p, _ in _routes()}
    assert (PUBLIC | SELF_ONLY) <= existing
