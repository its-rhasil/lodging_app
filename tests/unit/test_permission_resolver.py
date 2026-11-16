import pytest

from app.core.deps import require_permission
from app.service.permission_service import combine


def test_role_permissions_only():
    assert combine({"a", "b"}, []) == {"a", "b"}


def test_grant_adds_a_permission():
    assert combine({"a"}, [("b", "grant")]) == {"a", "b"}


def test_deny_removes_a_role_permission():
    assert combine({"a", "b"}, [("b", "deny")]) == {"a"}


def test_deny_wins_over_grant():
    assert combine({"a"}, [("b", "grant"), ("b", "deny")]) == {"a"}


def test_overrides_may_be_a_generator():
    assert combine({"a"}, (o for o in [("b", "grant"), ("a", "deny")])) == {"b"}


def test_unknown_permission_code_fails_at_declaration():
    with pytest.raises(ValueError, match="Unknown permission"):
        require_permission("folio.wave")  # typo of folio.waive
