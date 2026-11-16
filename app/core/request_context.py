"""Per-request metadata for the audit trail: request id, client IP, user agent."""
import ipaddress
import re
import uuid
from dataclasses import dataclass

from fastapi import Request

REQUEST_ID_HEADER = "X-Request-ID"
# A client-supplied id is reused only if it is short and plain; anything else is replaced.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MAX_USER_AGENT_LENGTH = 512


@dataclass(frozen=True)
class RequestMeta:
    request_id: str | None = None
    ip: str | None = None
    user_agent: str | None = None


async def request_id_middleware(request: Request, call_next):
    """Give every request an id, keep it on request.state and echo it in the response."""
    incoming = request.headers.get(REQUEST_ID_HEADER)
    request_id = incoming if incoming and _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def clean_ip(host: str | None) -> str | None:
    """Return host if it is a real IP address, else None (audit_events.ip is INET)."""
    if not host:
        return None
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def get_request_meta(request: Request) -> RequestMeta:
    """FastAPI dependency. Behind a reverse proxy, uvicorn must run with --proxy-headers
    so request.client is the real client, not the proxy."""
    user_agent = request.headers.get("user-agent")
    return RequestMeta(
        request_id=getattr(request.state, "request_id", None),
        ip=clean_ip(request.client.host if request.client else None),
        user_agent=user_agent[:MAX_USER_AGENT_LENGTH] if user_agent else None,
    )
