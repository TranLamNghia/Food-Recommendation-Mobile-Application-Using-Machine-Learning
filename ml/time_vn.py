# -*- coding: utf-8 -*-
"""One clock for the Python side: Asia/Ho_Chi_Minh.

The Python twin of `backend/Api/Time/DongHo.cs`, and it exists for the same
reason. Three layers of this system used to read three different clocks: the
database used `CURRENT_TIMESTAMP` on 27 columns and `NOW()` in every script,
both resolving to `@@session.time_zone`, which defaults to `SYSTEM`, which is
Vietnam time; the Flutter app used `DateTime.now()`, local time; and the
backend used `DateTime.UtcNow`, **seven hours off from both**. The silent
consequence: `users.created_at` written by the backend lagged seven hours
behind rows written by a Python script, so ordering by `created_at` mixed two
clocks.

The Python side avoided this until now only because it **never read a clock
itself** — every timestamp came from MySQL via `NOW()`. `ml/api.py` is the
first place that needs an application-side timestamp (`updatedAt` in a JSON
response, the training job id), so it needs one place to read the time rather
than a `datetime.now()` in every caller.

**Why not plain `datetime.now()`:** it returns the local time of whatever
machine is running. Correct on the development machine, wrong on a server in
another timezone, and the wrongness shows up nowhere — the timestamps are
simply a few hours off from the MySQL rows written at the same moment.

**Why not UTC:** switching to UTC would mean changing 27 schema defaults,
every `NOW()` under `tools/`, and the data already written. Vietnam time is
what the database **currently** stores.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _zone() -> ZoneInfo:
    """`Asia/Ho_Chi_Minh`, or stop outright with the fix spelled out.

    On Windows, `zoneinfo` needs the `tzdata` package because the operating
    system ships no IANA timezone database. Without it `ZoneInfo` raises
    `ZoneInfoNotFoundError`, and falling back to local time here would be
    exactly the failure this module exists to prevent.
    """
    try:
        return ZoneInfo("Asia/Ho_Chi_Minh")
    except ZoneInfoNotFoundError as e:  # pragma: no cover
        raise RuntimeError(
            "Asia/Ho_Chi_Minh timezone not found. Windows needs the IANA "
            "timezone database: pip install tzdata"
        ) from e


ZONE = _zone()


def now_vn() -> datetime:
    """The current moment in Asia/Ho_Chi_Minh, timezone-aware."""
    return datetime.now(ZONE)


def today_vn() -> date:
    """The current calendar date in Asia/Ho_Chi_Minh.

    Must be derived from `now_vn()` rather than `date.today()`: `date.today()`
    reads the machine's local time, so between 00:00 and 07:00 Vietnam time a
    machine running on UTC returns **yesterday**. On someone's birthday that
    makes the computed age a year out.
    """
    return now_vn().date()
