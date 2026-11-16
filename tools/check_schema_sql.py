#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare `db/schema.sql` against the live database, column by column.

This gap existed for a long time without anyone noticing.
`tools/check_docs_sync.py` compares the database against **three** sources —
`database_erd.html`, `DATABASE_DESIGN.md`, `ERD_REVIEW.md` — but **not against
`db/schema.sql` itself**, even though that is the file which builds the
database. `tools/test_schema_build.py` does build schema.sql into a scratch
database and count totals (22 tables / 29 foreign keys / 16 CHECKs / 212
columns), so it catches drift in **quantity** but not drift in **content**:
changing `VARCHAR(100)` to `VARCHAR(200)`, dropping a `NOT NULL`, adding an
ENUM value — every count stays exactly the same.

This file compares four things, each in both directions:

    column set · nullability · type family and parameters · ENUM/SET values

A lesson about measurement, recorded because I walked into it myself: the first
attempt split column definitions **by line** and reported 29 nullability errors
and 25 ENUM errors. All 54 were phantoms.

  - An `ENUM(...)` in schema.sql spans several lines, so splitting by line left
    `dish_role` as just `ENUM('main','side_protein',` — with the `NOT NULL` on
    a later line unseen.
  - Primary-key columns are written `PRIMARY KEY AUTO_INCREMENT` without
    `NOT NULL`; MySQL adds it. Not knowing that rule makes every primary key
    look like drift.
  - The ENUM comparison upper-cased the whole string before extracting the
    quoted values, so `'mild'` became `'MILD'` and never matched.

So here a column definition is split by **walking the characters and tracking
parenthesis depth**, and ENUM values are extracted from the original string
with its case intact.

Run:
    python tools/check_schema_sql.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "db" / "schema.sql"

# Keywords that begin a table-level constraint rather than a column.
TABLE_LEVEL = (
    "PRIMARY KEY",
    "FOREIGN KEY",
    "UNIQUE KEY",
    "UNIQUE INDEX",
    "UNIQUE (",
    "INDEX",
    "KEY ",
    "CONSTRAINT",
    "CHECK",
)

TYPE_KEYWORDS = (
    "BIGINT", "INT", "SMALLINT", "TINYINT", "MEDIUMINT",
    "VARCHAR", "CHAR", "TEXT", "LONGTEXT", "MEDIUMTEXT",
    "DECIMAL", "NUMERIC", "FLOAT", "DOUBLE",
    "DATETIME", "DATE", "TIMESTAMP", "TIME", "YEAR",
    "ENUM", "SET", "JSON", "BOOLEAN", "BOOL", "BLOB", "BINARY",
)


def strip_comments(text: str) -> str:
    """Remove `--` comments while leaving quoted content untouched.

    It cannot be done crudely with `split('--')`: a default value or a COMMENT
    may perfectly well contain two dashes.
    """
    out: list[str] = []
    in_string = False
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == "'":
                in_string = False
        elif ch == "'":
            in_string = True
            out.append(ch)
        elif text.startswith("--", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def split_definitions(body: str) -> list[str]:
    """Split a CREATE TABLE body into definitions, on commas **outside
    parentheses** and outside quotes.

    This is where the first attempt went wrong: splitting by line cuts an
    `ENUM(...)` spanning several lines into pieces, and the first piece does
    not contain the `NOT NULL`.
    """
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    in_string = False
    i, n = 0, len(body)

    while i < n:
        ch = body[i]
        if in_string:
            buf.append(ch)
            if ch == "\\" and i + 1 < n:
                buf.append(body[i + 1])
                i += 2
                continue
            if ch == "'":
                in_string = False
        elif ch == "'":
            in_string = True
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1

    if "".join(buf).strip():
        out.append("".join(buf))

    return [" ".join(d.split()) for d in out if d.strip()]


def parse_schema(text: str) -> dict[str, dict[str, dict]]:
    """Extract every column of every table out of schema.sql."""
    clean = strip_comments(text)
    tables: dict[str, dict[str, dict]] = {}

    for m in re.finditer(
        r"CREATE TABLE\s+(\w+)\s*\((.*?)\)\s*ENGINE", clean, re.S
    ):
        name, body = m.group(1), m.group(2)
        columns: dict[str, dict] = {}

        for definition in split_definitions(body):
            upper = definition.upper()
            if upper.startswith(TABLE_LEVEL):
                continue

            parts = definition.split(None, 1)
            if len(parts) < 2:
                continue
            column, rest = parts[0], parts[1]
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", column):
                continue
            if not rest.upper().startswith(TYPE_KEYWORDS):
                continue

            rest_upper = rest.upper()

            # A primary key is implicitly NOT NULL even when unwritten —
            # MySQL adds it.
            is_pk = "PRIMARY KEY" in rest_upper
            nullable = "NOT NULL" not in rest_upper and not is_pk

            type_match = re.match(r"([A-Za-z]+)\s*(\((.*?)\))?", rest, re.S)
            kind = type_match.group(1).upper() if type_match else ""

            info: dict = {
                "kind": kind,
                "nullable": nullable,
                "raw": rest,
            }

            if kind in ("ENUM", "SET"):
                # Extract from the ORIGINAL string, with its case intact.
                inner = type_match.group(3) if type_match else ""
                info["values"] = set(re.findall(r"'([^']*)'", inner or ""))
            elif kind in ("VARCHAR", "CHAR", "BINARY"):
                arg = (type_match.group(3) or "").strip()
                info["length"] = int(arg) if arg.isdigit() else None
            elif kind in ("DECIMAL", "NUMERIC"):
                arg = (type_match.group(3) or "")
                numbers = [int(x) for x in re.findall(r"\d+", arg)]
                if len(numbers) == 2:
                    info["precision"], info["scale"] = numbers

            columns[column] = info

        tables[name] = columns

    return tables


def read_db(database: str) -> dict[str, dict[str, dict]]:
    import pymysql

    conn = pymysql.connect(
        host=_env.get("MYSQL_HOST", "localhost"),
        port=int(_env.get("MYSQL_PORT", "3306")),
        user=_env.require("MYSQL_USER"),
        password=_env.require("MYSQL_PASSWORD"),
        database=database,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, "
                "       COLUMN_TYPE, CHARACTER_MAXIMUM_LENGTH, "
                "       NUMERIC_PRECISION, NUMERIC_SCALE "
                "FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s",
                (database,),
            )
            tables: dict[str, dict[str, dict]] = {}
            for (
                table, column, data_type, is_nullable,
                column_type, char_len, precision, scale,
            ) in cur.fetchall():
                info: dict = {
                    "kind": data_type.upper(),
                    "nullable": is_nullable == "YES",
                    "raw": column_type,
                }
                if data_type.upper() in ("ENUM", "SET"):
                    info["values"] = set(re.findall(r"'([^']*)'", column_type))
                elif data_type.upper() in ("VARCHAR", "CHAR", "BINARY"):
                    info["length"] = char_len
                elif data_type.upper() in ("DECIMAL", "NUMERIC"):
                    info["precision"], info["scale"] = precision, scale
                tables.setdefault(table, {})[column] = info
            return tables
    finally:
        conn.close()


def main() -> int:
    _env.use_utf8()
    database = _env.require("MYSQL_DATABASE")
    sql = parse_schema(SCHEMA.read_text(encoding="utf-8"))
    db = read_db(database)

    problems: list[str] = []

    print("=" * 74)
    print("COMPARING db/schema.sql AGAINST THE LIVE DATABASE")
    print("=" * 74)

    # -- 1. The set of tables --
    print("\n1. The set of tables")
    only_sql = sorted(set(sql) - set(db))
    only_db = sorted(set(db) - set(sql))
    for t in only_sql:
        print(f"   BAD  `{t}` is in schema.sql but not in the database")
        problems.append(f"table `{t}` is only in schema.sql")
    for t in only_db:
        print(f"   BAD  `{t}` is in the database but not in schema.sql")
        problems.append(f"table `{t}` is only in the database")
    if not only_sql and not only_db:
        print(f"   ok   {len(db)} tables, matching in both directions")

    shared = sorted(set(sql) & set(db))

    # -- 2. Each table's set of columns --
    print("\n2. Each table's set of columns")
    missing = extra = 0
    for t in shared:
        for c in sorted(set(db[t]) - set(sql[t])):
            print(f"   BAD  {t}.{c} is in the database, absent from schema.sql")
            problems.append(f"`{t}.{c}` is absent from schema.sql")
            missing += 1
        for c in sorted(set(sql[t]) - set(db[t])):
            print(f"   BAD  {t}.{c} is in schema.sql, absent from the database")
            problems.append(f"`{t}.{c}` is only in schema.sql")
            extra += 1
    total_cols = sum(len(v) for v in db.values())
    if not missing and not extra:
        print(f"   ok   {total_cols} columns, matching in both directions")

    # -- 3. Nullability --
    print("\n3. Nullability")
    mismatches = 0
    for t in shared:
        for c in sorted(set(sql[t]) & set(db[t])):
            a, b = sql[t][c]["nullable"], db[t][c]["nullable"]
            if a != b:
                print(
                    f"   BAD  {t}.{c}: schema.sql="
                    f"{'NULL' if a else 'NOT NULL'}, database="
                    f"{'NULL' if b else 'NOT NULL'}"
                )
                problems.append(f"`{t}.{c}` differs on NULL/NOT NULL")
                mismatches += 1
    if not mismatches:
        print(f"   ok   {total_cols} columns, nullability matches throughout")

    # -- 4. Types and parameters --
    print("\n4. Data types and parameters")
    mismatches = 0
    checked = 0
    for t in shared:
        for c in sorted(set(sql[t]) & set(db[t])):
            in_sql, in_db = sql[t][c], db[t][c]
            checked += 1
            if in_sql["kind"] != in_db["kind"]:
                print(
                    f"   BAD  {t}.{c}: schema={in_sql['kind']}, "
                    f"database={in_db['kind']}"
                )
                problems.append(f"`{t}.{c}` differs on type")
                mismatches += 1
                continue
            if "length" in in_sql and in_sql["length"] != in_db.get("length"):
                print(
                    f"   BAD  {t}.{c}: schema length {in_sql['length']}, "
                    f"database {in_db.get('length')}"
                )
                problems.append(f"`{t}.{c}` differs on length")
                mismatches += 1
            if "precision" in in_sql and (
                in_sql.get("precision") != in_db.get("precision")
                or in_sql.get("scale") != in_db.get("scale")
            ):
                print(
                    f"   BAD  {t}.{c}: schema "
                    f"({in_sql.get('precision')},{in_sql.get('scale')}), "
                    f"database "
                    f"({in_db.get('precision')},{in_db.get('scale')})"
                )
                problems.append(f"`{t}.{c}` differs on DECIMAL precision")
                mismatches += 1
    if not mismatches:
        print(f"   ok   {checked} columns, types and parameters match throughout")

    # -- 5. ENUM / SET values --
    print("\n5. ENUM and SET value sets")
    mismatches = 0
    checked = 0
    for t in shared:
        for c in sorted(set(sql[t]) & set(db[t])):
            in_sql, in_db = sql[t][c], db[t][c]
            if "values" not in in_sql or "values" not in in_db:
                continue
            checked += 1
            if in_sql["values"] != in_db["values"]:
                surplus = (
                    ", ".join(sorted(in_sql["values"] - in_db["values"])) or "-"
                )
                absent = (
                    ", ".join(sorted(in_db["values"] - in_sql["values"])) or "-"
                )
                print(
                    f"   BAD  {t}.{c}: schema has extra {surplus} · "
                    f"missing {absent}"
                )
                problems.append(f"`{t}.{c}` differs on its ENUM value set")
                mismatches += 1
    if not mismatches:
        print(f"   ok   {checked} ENUM/SET columns, value sets match throughout")

    print("\n" + "=" * 74)
    if problems:
        print(f"{len(problems)} problems:\n")
        for item in problems:
            print(f"  BAD  {item}")
    else:
        print(
            "db/schema.sql DESCRIBES THE DATABASE CORRECTLY — column by "
            "column, in both directions."
        )
    print("=" * 74)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
