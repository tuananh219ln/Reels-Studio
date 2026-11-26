from datetime import UTC, datetime

import pytest

from reels_api import schedule_tz
from reels_api.schedule_tz import slots_between

NY = "America/New_York"


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_vietnam_has_no_dst():
    got = slots_between(["20:00"], "Asia/Ho_Chi_Minh", utc(2027, 3, 13, 0), utc(2027, 3, 15, 0))
    assert got == [utc(2027, 3, 13, 13), utc(2027, 3, 14, 13)]


def test_new_york_keeps_its_wall_time_across_the_spring_change():
    # 14/3/2027: 20:00 is 01:00 UTC (EST) the day before the change and 00:00 UTC (EDT) after it.
    got = slots_between(["20:00"], NY, utc(2027, 3, 13, 2), utc(2027, 3, 16, 0))
    assert got == [utc(2027, 3, 14, 1), utc(2027, 3, 15, 0), utc(2027, 3, 16, 0)]


def test_new_york_keeps_its_wall_time_across_the_autumn_change():
    # 7/11/2027: back to EST.
    got = slots_between(["20:00"], NY, utc(2027, 11, 6, 1), utc(2027, 11, 9, 0))
    assert got == [utc(2027, 11, 7, 0), utc(2027, 11, 8, 1), utc(2027, 11, 9, 1)]


def test_a_time_that_does_not_exist_moves_after_the_jump():
    # 02:30 on 14/3/2027 does not exist in New York; it is 03:30 EDT (07:30 UTC), still one slot.
    got = slots_between(["02:30"], NY, utc(2027, 3, 14, 0), utc(2027, 3, 14, 23))
    assert got == [utc(2027, 3, 14, 7, 30)]


def test_a_time_that_happens_twice_takes_the_first_and_one_slot():
    # 01:30 on 7/11/2027 is 05:30 UTC (EDT) and again 06:30 UTC (EST): only the first.
    got = slots_between(["01:30"], NY, utc(2027, 11, 7, 0), utc(2027, 11, 7, 23))
    assert got == [utc(2027, 11, 7, 5, 30)]


def test_two_wall_times_on_one_moment_make_one_slot(caplog):
    # 02:30 (does not exist) and 03:30 are both 07:30 UTC on the day of the jump.
    got = slots_between(["02:30", "03:30"], NY, utc(2027, 3, 14, 0), utc(2027, 3, 14, 23))
    assert got == [utc(2027, 3, 14, 7, 30)]
    assert "same moment" in caplog.text


def test_days_are_the_zones_own():
    # 22:00 on 10/11 in Los Angeles is 06:00 UTC on the 11th: a window that starts on the 11th UTC still finds it.
    got = slots_between(["22:00"], "America/Los_Angeles", utc(2026, 11, 11, 5), utc(2026, 11, 11, 7))
    assert got == [utc(2026, 11, 11, 6)]


def test_only_listed_zones_are_allowed():
    assert schedule_tz.check_zone(NY) == NY
    with pytest.raises(schedule_tz.ZoneError):
        schedule_tz.check_zone("Europe/London")


def test_convert_reads_the_same_moments_in_the_other_zone():
    from datetime import date

    # 20:00 and 21:30 New York on a winter day are 08:00 and 09:30 in Vietnam the next morning.
    got = schedule_tz.convert_times(["20:00", "21:30"], NY, "Asia/Ho_Chi_Minh", date(2027, 1, 15))
    assert got == ["08:00", "09:30"]
    # In summer (EDT) the same wall times are an hour earlier in Vietnam.
    assert schedule_tz.convert_times(["20:00"], NY, "Asia/Ho_Chi_Minh", date(2027, 7, 15)) == ["07:00"]
    # Times that land on one wall time make one.
    assert schedule_tz.convert_times(["20:00", "20:00"], NY, NY, date(2027, 1, 15)) == ["20:00"]
