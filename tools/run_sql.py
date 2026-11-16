#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run a .sql file against MySQL through pymysql.

It exists because the development machine has no `mysql` CLI on PATH, and
splitting statements with `split(';')` is wrong: a semicolon inside a string
or inside a comment would cut a statement in half. The splitter here walks
character by character and tracks quoting state, so it only cuts at a
semicolon that genuinely ends a statement.

Run:
    python tools/run_sql.py db/schema.sql
    python tools/run_sql.py db/seed.sql --database nutrition_rec
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402


def split_statements(sql: str) -> list[str]:
    """Split into statements, ignoring any `;` inside a string or comment."""
    out: list[str] = []
    buf: list[str] = []
    i, n = 0, len(sql)
    quote: str | None = None

    while i < n:
        ch = sql[i]

        if quote:
            buf.append(ch)
            if ch == "\\" and i + 1 < n:          # escape character
                buf.append(sql[i + 1])
                i += 2
                continue
            if ch == quote:
                # Two adjacent quotes are one quote inside the string.
                if i + 1 < n and sql[i + 1] == quote:
                    buf.append(sql[i + 1])
                    i += 2
                    continue
                quote = None
            i += 1
            continue

        # Line comment: skip to end of line.
        if sql.startswith("--", i) or sql.startswith("#", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j
            continue

        # Block comment.
        if sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue

        if ch in ("'", '"', "`"):
            quote = ch
            buf.append(ch)
            i += 1
            continue

        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def main() -> int:
    _env.use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument(
        "--database", default=None,
        help="select this database first; omit if the file does CREATE/USE itself",
    )
    args = parser.parse_args()

    try:
        import pymysql
    except ImportError:
        sys.exit("pymysql is required:  pip install pymysql")

    conn = pymysql.connect(
        host=_env.get("MYSQL_HOST", "localhost"),
        port=int(_env.get("MYSQL_PORT", "3306")),
        user=_env.require("MYSQL_USER"),
        password=_env.require("MYSQL_PASSWORD"),
        charset="utf8mb4",
        autocommit=False,
    )

    try:
        with conn.cursor() as cur:
            if args.database:
                cur.execute(f"USE `{args.database}`")

            for path in args.files:
                statements = split_statements(path.read_text(encoding="utf-8"))
                print(f"\n{path}  —  {len(statements)} statements")

                for idx, stmt in enumerate(statements, start=1):
                    try:
                        cur.execute(stmt)
                    except Exception as exc:
                        conn.rollback()
                        head = " ".join(stmt.split())[:160]
                        sys.exit(
                            f"\nFAILED at statement {idx}/{len(statements)} "
                            f"of {path}\n  {head}...\n\n{exc}\n\nRolled back."
                        )
                print("  -> done")

        conn.commit()
        print("\nCommitted.")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
