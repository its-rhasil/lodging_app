"""Who is making the request (architecture.md §5). Built once per request from the session."""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Actor:
    """Who did something, as written to audit_events (ck_audit_actor_type / ck_audit_actor_ids)."""
    type: str  # tenant_user | platform_user | system | anonymous
    user_id: int | None = None
    platform_user_id: int | None = None

    @classmethod
    def tenant_user(cls, user_id: int) -> "Actor":
        return cls("tenant_user", user_id=user_id)

    @classmethod
    def platform_user(cls, platform_user_id: int) -> "Actor":
        return cls("platform_user", platform_user_id=platform_user_id)


SYSTEM = Actor("system")        # CLI commands, the posting engine
ANONYMOUS = Actor("anonymous")  # not logged in, e.g. a failed login


@dataclass(frozen=True)
class Principal:
    kind: Literal["tenant", "platform"]
    user_id: int
    tenant_id: int | None          # None for platform users
    role_code: str | None          # None for platform users
    permissions: frozenset[str]    # effective set: role ∪ grants − denies
    session_id: int

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    @property
    def actor(self) -> Actor:
        if self.kind == "platform":
            return Actor.platform_user(self.user_id)
        return Actor.tenant_user(self.user_id)
