# -*- coding: utf-8 -*-
"""Open a connection to the `nutrition_rec` database.

Reuses `tools/_env.py` rather than reading `.env` a second time, so that
exactly **one** place knows how the password is obtained. The password is
never printed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import _env  # noqa: E402

import pymysql  # noqa: E402
from pymysql.cursors import DictCursor  # noqa: E402

DATABASE_NAME = "nutrition_rec"


def connect(database: str | None = None, *, dict_cursor: bool = True):
    """Return an open pymysql connection.

    Leaving `database` empty uses the real database. Pass another name to
    run against a scratch database without touching existing data.
    """
    _env.load_env()
    missing = [k for k in ("MYSQL_USER", "MYSQL_PASSWORD") if not os.environ.get(k)]
    if missing:
        raise SystemExit(
            "Missing environment variables: " + ", ".join(missing) + "\n"
            "Copy .env.example to .env and fill in the values."
        )

    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=database or DATABASE_NAME,
        charset="utf8mb4",
        cursorclass=DictCursor if dict_cursor else pymysql.cursors.Cursor,
        autocommit=False,
    )


def use_utf8() -> None:
    """Make stdout accept non-ASCII text on Windows (it defaults to cp1252).

    Still needed after the English refactor: the **data** stays Vietnamese.
    Food names, condition names and rule notes are printed verbatim, so a
    report line such as `Phở bò chín` dies with `UnicodeEncodeError` without
    this — and it dies only when output is redirected to a file or a pipe,
    which is to say only in CI.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover - unusual console
            pass
