"""The time zone a posting schedule is written in (docs/decisions/2026-11-26-schedule-timezone.md).

A schedule is wall-clock times ("20:00") plus an IANA zone, never a fixed offset, so a post for a US audience keeps
its New York wall time when the US changes its clocks. `scheduled_at` stays a UTC moment.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

VIETNAM_ZONE = "Asia/Ho_Chi_Minh"
DEFAULT_ZONE = VIETNAM_ZONE
# What a member can choose: Vietnam, or one of the three US zones the Pages' audience lives in.
ZONES = {
    "Asia/Ho_Chi_Minh": "VN",
    "America/New_York": "US ET",
    "America/Chicago": "US CT",
    "America/Los_Angeles": "US PT",
}


class ZoneError(ValueError):
    """The message is shown to members."""


def check_zone(name: str) -> str:
    if name not in ZONES:
        raise ZoneError("Múi giờ lịch đăng chỉ có thể là VN hoặc US (ET, CT, PT)")
    return name


def slots_between(times: list[str], zone: str, start: datetime, until: datetime) -> list[datetime]:
    """Every moment (UTC, sorted) a wall-clock time of `times` falls in `zone` between the two moments, ends included.

    The days are the zone's own. A wall time that does not exist (02:30 on the day the clocks jump) is the moment
    the same offset as just before the jump gives (03:30 after it); one that happens twice takes its first time.
    Two wall times that land on one moment make one slot."""
    tz = ZoneInfo(zone)
    day, last = start.astimezone(tz).date(), until.astimezone(tz).date()
    found: dict[datetime, str] = {}
    while day <= last:
        for value in times:
            hour, minute = (int(part) for part in value.split(":"))
            at = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz, fold=0).astimezone(UTC)
            if start <= at <= until:
                if at in found:
                    log.warning("Posting times %s and %s are the same moment in %s on %s", found[at], value, zone, day)
                found[at] = value
        day += timedelta(days=1)
    return sorted(found)


def convert_times(times: list[str], old: str, new: str, on: date) -> list[str]:
    """The same moments of day `on`, read in the other zone ("Quy đổi"): 20:00 in New York is 08:00 in Vietnam next
    morning in winter. Times that become the same wall time make one; the result is in order of the day. Daylight
    saving makes the answer depend on the day, so the caller passes today."""
    old_tz, new_tz = ZoneInfo(old), ZoneInfo(new)
    out = set()
    for value in times:
        hour, minute = (int(part) for part in value.split(":"))
        at = datetime(on.year, on.month, on.day, hour, minute, tzinfo=old_tz, fold=0).astimezone(new_tz)
        out.add(f"{at.hour:02d}:{at.minute:02d}")
    return sorted(out)
