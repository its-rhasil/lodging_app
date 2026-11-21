from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEventOut(BaseModel):
    id: int
    created_at: datetime
    actor_type: str
    actor_user_id: int | None
    actor_name: str | None  # the staff member's name; None for system / anonymous / platform actors
    action: str
    entity_type: str | None
    entity_id: str | None
    summary: str | None
    changes: dict[str, Any] | None
    reason: str | None
    request_id: str | None

    model_config = ConfigDict(from_attributes=True)
