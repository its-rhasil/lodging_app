"""Audit writer (DL-R12, P3-4).

Services call record() inside their own transaction, before their single commit,
so the audit row and the change it describes are saved together or not at all.
record() only adds the row; it never commits.
"""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.principal import ANONYMOUS, SYSTEM, Actor  # noqa: F401  (re-exported for callers)
from app.core.request_context import RequestMeta
from app.models import AuditEvent, User

# Keys that must never appear in `changes` (data-model.md §4.5).
_SECRET_KEY_PARTS = ("password", "token", "hash", "secret")


def _check_no_secrets(value: Any, path: str = "changes") -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            if any(part in str(key).lower() for part in _SECRET_KEY_PARTS):
                raise ValueError(f"audit {path} must not contain secret field {key!r}")
            _check_no_secrets(inner, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for item in value:
            _check_no_secrets(item, path)


def record(
    db: Session,
    *,
    action: str,
    actor: Actor,
    tenant_id: int | None,
    entity_type: str | None = None,
    entity_id: Any = None,
    summary: str | None = None,
    changes: dict | None = None,
    reason: str | None = None,
    meta: RequestMeta | None = None,
) -> AuditEvent:
    if changes is not None:
        _check_no_secrets(changes)
    meta = meta or RequestMeta()
    event = AuditEvent(
        tenant_id=tenant_id,
        actor_type=actor.type,
        actor_user_id=actor.user_id,
        actor_platform_user_id=actor.platform_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=None if entity_id is None else str(entity_id),
        summary=summary,
        changes=changes,
        reason=reason,
        request_id=meta.request_id,
        ip=meta.ip,
        user_agent=meta.user_agent,
    )
    db.add(event)
    return event


def list_events(db: Session, tenant_id: int, *, date_from=None, date_to=None, actor_user_id=None,
                action=None, entity_type=None, entity_id=None, limit=50, offset=0) -> list[dict]:
    """This tenant's audit trail, newest first (P3-5). date_from is inclusive, date_to exclusive.

    Each row carries the actor's name, so anyone with audit.view sees who did it
    (not only users who may list the staff).
    """
    query = select(AuditEvent, User.name).outerjoin(User, User.id == AuditEvent.actor_user_id) \
        .where(AuditEvent.tenant_id == tenant_id)
    if date_from is not None:
        query = query.where(AuditEvent.created_at >= date_from)
    if date_to is not None:
        query = query.where(AuditEvent.created_at < date_to)
    if actor_user_id is not None:
        query = query.where(AuditEvent.actor_user_id == actor_user_id)
    if action:
        query = query.where(AuditEvent.action == action)
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditEvent.entity_id == str(entity_id))
    limit = max(1, min(limit, 200))
    rows = db.execute(
        query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit).offset(max(0, offset))
    ).all()
    return [
        {
            "id": event.id, "created_at": event.created_at, "actor_type": event.actor_type,
            "actor_user_id": event.actor_user_id, "actor_name": actor_name, "action": event.action,
            "entity_type": event.entity_type, "entity_id": event.entity_id, "summary": event.summary,
            "changes": event.changes, "reason": event.reason, "request_id": event.request_id,
        }
        for event, actor_name in rows
    ]
