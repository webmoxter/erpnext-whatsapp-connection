from __future__ import annotations

from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo


def provider_datetime(value, timezone_name: str | tzinfo) -> datetime | None:
    """Convert an ISO provider timestamp into Frappe's naive site datetime."""
    if value in (None, ""):
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed
    target_timezone = ZoneInfo(timezone_name) if isinstance(timezone_name, str) else timezone_name
    return parsed.astimezone(target_timezone).replace(tzinfo=None)
