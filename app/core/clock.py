"""The current time, as a FastAPI dependency (testing-strategy.md §3).

Routes take `now: datetime = Depends(get_now)` and pass it to services, which never
read the clock themselves. In the app this is simply the real time at the moment the
request arrives (folio opened, button clicked). Tests override get_now with a FakeClock,
so posting rules (period boundaries, grace) can be checked at exact moments.
"""
from datetime import datetime

from app.core.security import utcnow


def get_now() -> datetime:
    return utcnow()
