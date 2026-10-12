###################################################################################################
# Time zones people can pick for themselves (IANA names). Validated against the zone database so a
# bad value can never reach the browser's formatter.
###################################################################################################
from zoneinfo import ZoneInfo, available_timezones

from fastapi import HTTPException


def clean_timezone(tz: str | None) -> str | None:
    """A valid IANA zone name, or None for "use the account's". Raises 400 otherwise."""
    tz = (tz or "").strip()
    if not tz:
        return None
    if tz not in available_timezones():
        raise HTTPException(400, f"Unknown time zone: {tz}")
    ZoneInfo(tz)
    return tz
