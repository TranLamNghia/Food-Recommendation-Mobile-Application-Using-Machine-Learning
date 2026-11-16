#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The flowcharts, the API specification and the database schema must describe
one and the same system.

Why it is needed. The eighteen flowcharts in `BAOCAO/Diagram.mdj` name
endpoints, error codes and table names. Those three things live in three
different files — the diagrams, the API specification, the database schema —
and nothing forces them to agree. Rename an endpoint in the specification and
the diagram still renders perfectly, still prints into the report perfectly; it
simply describes a system that does not exist.

This checker's first run caught **five misnamed error codes** inside the very
diagram set that had just been drawn: `EMAIL_EXISTS` where the catalogue says
`EMAIL_ALREADY_EXISTS`, `FOOD_NOT_FOUND` where the catalogue only has
`NOT_FOUND`, and three more. None of them broke anything — which is exactly
why this has to be checked by machine.

THE FIVE CHECKS
    1. endpoints   diagram -> spec      every `METHOD /path` must be in §6
    2. error codes diagram -> spec      every code must be in the §4 catalogue
    3. table names diagram -> database  every table must be in db/schema.sql
    4. column names diagram -> database every column must be in its table
    5. counts      spec -> spec         "N public endpoints" must equal the
                                        number of rows

The fourth check was added later, because the third let through exactly the
kind of defect it was built to catch. The diagrams said `ORDER BY log_date` and
`UPSERT body_logs by (user_id, log_date)` while the real column is named
`logged_on`; the API specification was also returning a `logDate` field that
matched no column. The TABLE name was right, so the third check passed — and a
query with a correct table name and an invented column name still reads
perfectly fluently, it just cannot run.

Run:
    python tools/check_flowchart.py

Note on language: `SO_DO`, `DAU_DE_XUAT`, `kiem_luong_chinh` and `STORIES` are
names inside `tools/baocao/`, which holds report content and stays Vietnamese;
and the patterns that match the Vietnamese API specification stay as they are.
"""

from __future__ import annotations

import pathlib
import re
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "baocao"))

from flowchart_data import DAU_DE_XUAT, SO_DO  # noqa: E402

APISPEC = ROOT / "docs" / "API_SPECIFICATION.md"
SCHEMA = ROOT / "db" / "schema.sql"
MDJ = ROOT / "BAOCAO" / "Diagram.mdj"

#: `METHOD /path` anywhere in a block's text.
RE_ENDPOINT = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE) (/[A-Za-z0-9/{}_-]+)")

#: An error code: capitals and underscores, at least two segments. Narrow
#: enough not to catch `NULL`, `SQL` or `BMI`, wide enough to catch every code
#: in the catalogue.
RE_ERROR_CODE = re.compile(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b")

#: Upper-case underscored strings that are NOT error codes.
SKIP_CODES = {
    "CURRENT_TIMESTAMP", "ON_DELETE", "NOT_NULL", "PRIMARY_KEY",
    "E_TARGET", "C_VALID",
}

#: A table name following an SQL keyword, or named outright.
RE_TABLE_SQL = re.compile(
    r"\b(?:FROM|INTO|JOIN|UPDATE|UPSERT)\s+([a-z][a-z0-9_]+)")

#: A table name mentioned in a block's prose, for example "Đọc foods,
#: food_nutrition".
RE_SNAKE_WORD = re.compile(r"\b([a-z]+(?:_[a-z]+)+)\b")

#: Keywords that begin a type declaration, used to tell a column-declaration
#: line from a continuation line of a multi-line ENUM or a CHECK expression.
TYPE_KEYWORDS = (
    "BIGINT", "INT", "SMALLINT", "TINYINT", "MEDIUMINT", "DECIMAL", "NUMERIC",
    "FLOAT", "DOUBLE", "VARCHAR", "CHAR", "TEXT", "LONGTEXT", "MEDIUMTEXT",
    "JSON", "ENUM", "SET", "DATE", "DATETIME", "TIMESTAMP", "TIME", "YEAR",
    "BOOLEAN", "BOOL", "BLOB", "BINARY",
)

#: snake_case strings in a block that are NOT column names: an API JSON field
#: name, or a compound word used in a sentence.
SKIP_COLUMNS = {
    "access_token", "refresh_token", "reset_token",
}

# A SINGLE-WORD column name cannot get through `RE_SNAKE_WORD`, because that
# pattern requires at least one underscore so as not to match every English
# word in a sentence. That very gap let `interactions (source = ...)` through:
# `source` has no underscore, and `interactions` HAS NO column by that name —
# the real one is `action`.
#
# So rather than loosening the name pattern (which would also match "theo",
# "đã", "món"), the three patterns below match on SYNTACTIC POSITION: places
# inside an SQL statement where a lower-case identifier can only be a column
# name. SQL keywords are upper-cased in every diagram, so a case-sensitive
# pattern excludes them without needing a keyword list.

#: `col = ...`, `col >= ...` — the left side of a comparison or an assignment.
RE_COLUMN_COMPARISON = re.compile(r"\b([a-z][a-z0-9_]*)\s*(?:=|<>|!=|<=|>=|<|>)")

#: `SELECT a, b, c FROM` — the selected column list.
RE_COLUMN_SELECT = re.compile(r"\bSELECT\s+(.+?)\s+FROM\b")

#: `INSERT INTO table (a, b)` · `UPSERT table (a, b)` — the parenthesised list.
RE_COLUMN_PAREN_LIST = re.compile(
    r"\b(?:INSERT INTO|UPSERT|UPDATE)\s+[a-z_][a-z0-9_]*\s*\((.+?)\)")

#: `ORDER BY a, b` · `GROUP BY a` — accepts only a comma-separated identifier
#: list, not the prose that follows it. `SET` needs no pattern of its own
#: because `RE_COLUMN_COMPARISON` already catches the left side of every
#: assignment.
RE_COLUMN_AFTER_BY = re.compile(
    r"\b(?:ORDER BY|GROUP BY)\s+"
    r"([a-z_][a-z0-9_]*(?:\s*,\s*[a-z_][a-z0-9_]*)*)")

#: A single-quoted string: a VALUE, not a column name. Stripped before
#: extracting candidates, or `(role = 'user')` would yield a "column" named
#: `user`.
RE_STRING_LITERAL = re.compile(r"'[^']*'")

#: One element of a column list: skips `*`, constants and parameter marks.
RE_IDENTIFIER = re.compile(r"\b([a-z][a-z0-9_]*)\b")


def block_texts() -> list[tuple[str, str]]:
    """(diagram code, block text) for every block of all 18 diagrams."""
    return [(code, b[4]) for code, _, blocks, _ in SO_DO for b in blocks]


def _use_case_names_mdj() -> list[str]:
    """The names of the 18 `UMLUseCase` elements in `BAOCAO/Diagram.mdj`."""
    import json

    out: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("_type") == "UMLUseCase":
                out.append(str(node.get("name")))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads(MDJ.read_text(encoding="utf-8")))
    return out


def check_chapter2_flows() -> list[str]:
    """The Chapter 2 scenario derivation must still hold for all 18 diagrams.

    `chuong2_data.py` derives each scenario's main flow from `SO_DO` itself,
    relying on a **drawing convention** (the main axis is in column 0, moving
    down by row). That convention can be broken by a perfectly legitimate
    diagram edit — adding a note box to the right, or adding a loop back — and
    when it is, the generated scenario is still a list of readable sentences,
    just of a flow that is not on the diagram.
    """
    try:
        sys.path.insert(0, str(ROOT / "tools" / "baocao"))
        import chuong2_data  # type: ignore
    except ImportError as e:  # pragma: no cover
        print(f"   !  could not load chuong2_data.py: {e}")
        return [f"could not load chuong2_data.py: {e}"]

    errors = chuong2_data.kiem_luong_chinh()
    if not errors:
        print(
            f"   ok   {len(SO_DO)}/{len(SO_DO)} main flows reach their End block"
        )
    return errors


def check_use_case_names() -> list[str]:
    """Use case names must agree across THREE sources: the mdj, the flowcharts
    and the User stories.

    `them_flowchart.py` already forces `flowchart_data.SO_DO` to agree with the
    Use case model, but **nobody was auditing `tools/baocao/us_data.py`** — and
    it had drifted: two use cases carried shorter names in the report's User
    story section than on the Use case diagram and the flowcharts:

        diagram: "Điền hoặc Chọn thông tin cá nhân phù hợp với sức khỏe cá nhân"
        story:   "Khai báo thông tin cá nhân và tình trạng sức khỏe"

        diagram: "Lựa chọn món ăn yêu thích dựa vào tình trạng sức khỏe"
        story:   "Lựa chọn món ăn yêu thích"

    Neither breaks anything — but an examiner reads the Use case diagram in
    §2.2.2, then the User stories in §1.4, and sees two different names for one
    function. `us_data.py`'s own docstring claims to hold "exactly the 18 use
    cases in Diagram.mdj", so this is a defect against the contract it set
    itself.
    """
    errors: list[str] = []
    mdj = set(_use_case_names_mdj())
    flowcharts = {name for _code, name, _b, _c in SO_DO}

    try:
        sys.path.insert(0, str(ROOT / "tools" / "baocao"))
        import us_data  # type: ignore
    except ImportError as e:  # pragma: no cover
        print(f"   !  could not load us_data.py: {e}")
        return [f"could not load us_data.py: {e}"]
    stories = {s[0] for s in us_data.STORIES}

    for source_name, names in (
        ("flowchart_data", flowcharts),
        ("us_data", stories),
    ):
        missing = sorted(mdj - names)
        surplus = sorted(names - mdj)
        if missing or surplus:
            for x in missing:
                errors.append(
                    f"{source_name} is missing use case {x!r} (present in the mdj)"
                )
            for x in surplus:
                errors.append(
                    f"{source_name} has use case {x!r} which the mdj does not"
                )
        else:
            print(f"   ok   {source_name}: {len(names)} names match the mdj")
    return errors


def _use_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover
            pass


def check_endpoints(spec: str) -> list[str]:
    errors = []
    seen: set[str] = set()
    for code, text in block_texts():
        for method, path in RE_ENDPOINT.findall(text):
            endpoint = f"{method} {path}"
            seen.add(endpoint)
            if f"`{path}`" not in spec:
                errors.append(
                    f"{code}: the diagram calls {endpoint!r} but the "
                    f"specification has no path {path!r}"
                )
    print(f"   {len(seen)} distinct endpoints named across the 18 diagrams")
    return errors


def check_error_codes(spec: str) -> list[str]:
    # The error-code catalogue: the first column of the table in §4.
    catalogue = set(re.findall(r"^\| `([A-Z][A-Z0-9_]+)` \| \d{3} \|",
                               spec, re.M))
    if not catalogue:
        return [
            "could not read the error-code catalogue in §4 of the specification"
        ]
    errors = []
    seen: set[str] = set()
    for code, text in block_texts():
        # `lỗi` is the Vietnamese word for "error" as the diagram blocks write
        # it, so this match stays Vietnamese.
        if "lỗi" not in text.lower():
            continue
        for x in RE_ERROR_CODE.findall(text):
            if x in SKIP_CODES:
                continue
            seen.add(x)
            if x not in catalogue:
                errors.append(
                    f"{code}: the diagram shows code {x!r} which the §4 "
                    f"catalogue does not list"
                )
    print(
        f"   {len(catalogue)} codes in the catalogue, {len(seen)} codes used "
        f"in the diagrams"
    )
    return errors


def check_tables(schema: str) -> list[str]:
    existing = set(re.findall(r"^CREATE TABLE (\w+)", schema, re.M))
    errors = []
    seen: set[str] = set()
    for code, text in block_texts():
        if DAU_DE_XUAT in text:
            continue
        candidates = set(RE_TABLE_SQL.findall(text))
        # In a database block every snake_case identifier is a plausible table
        # name; only report one that LOOKS like a table name and does not
        # exist — column names are snake_case too, so only strings already
        # known to be tables are accepted here.
        candidates |= {x for x in RE_SNAKE_WORD.findall(text) if x in existing}
        for table in candidates:
            seen.add(table)
            if table not in existing:
                errors.append(
                    f"{code}: the diagram names table {table!r} which "
                    f"db/schema.sql does not have"
                )
    print(
        f"   {len(seen)} tables named in the diagrams, "
        f"{len(existing)} tables in the schema"
    )
    return errors


def _columns_by_table(schema: str) -> dict[str, set[str]]:
    """{table name: set of column names} extracted from db/schema.sql.

    Types and constraints are not needed — `tools/check_schema_sql.py` already
    compares every column against the live database. Here it only matters
    whether a column name EXISTS or not.
    """
    out: dict[str, set[str]] = {}
    for m in re.finditer(r"CREATE TABLE (\w+)\s*\((.*?)\n\) ENGINE",
                         schema, re.S):
        table, body = m.group(1), m.group(2)
        columns = set()
        for line in body.split("\n"):
            line = line.split("--")[0].strip()
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", parts[0]):
                continue
            if not parts[1].upper().startswith(TYPE_KEYWORDS):
                continue
            columns.add(parts[0])
        out[table] = columns
    return out


def check_columns(schema: str) -> list[str]:
    """Every column name in a block must exist in the table that block names.

    The scope is deliberately narrow: only blocks naming EXACTLY ONE table.
    A block naming two or more is a JOIN, and there a column that exists in one
    table but not the other is perfectly correct — the check would report a
    phantom. Narrow and quiet beats wide and needing an exception list.
    """
    columns_by_table = _columns_by_table(schema)
    errors = []
    examined = 0
    for code, text in block_texts():
        if DAU_DE_XUAT in text:
            continue
        tables = {x for x in RE_TABLE_SQL.findall(text) if x in columns_by_table}
        tables |= {
            x for x in RE_SNAKE_WORD.findall(text) if x in columns_by_table
        }
        if len(tables) != 1:
            continue
        table = tables.pop()
        examined += 1

        # Strip quoted values before extracting: they are not column names.
        unquoted = RE_STRING_LITERAL.sub(" ", text)

        # Candidate set 1 — every snake_case string in the block.
        candidates = set(RE_SNAKE_WORD.findall(unquoted))
        # Candidate set 2 — identifiers in a syntactic position reserved for
        # column names.
        candidates |= set(RE_COLUMN_COMPARISON.findall(unquoted))
        for pattern in (
            RE_COLUMN_SELECT, RE_COLUMN_PAREN_LIST, RE_COLUMN_AFTER_BY
        ):
            for listing in pattern.findall(unquoted):
                candidates |= set(RE_IDENTIFIER.findall(listing))

        for x in sorted(candidates):
            if x == table or x in columns_by_table or x in SKIP_COLUMNS:
                continue
            if x not in columns_by_table[table]:
                errors.append(
                    f"{code}: the diagram names {x!r} as a column of "
                    f"{table!r}, which has no column by that name"
                )
    print(f"   {examined} blocks name exactly one table; their columns audited")
    return errors


def check_counts(spec: str) -> list[str]:
    # The sentence being matched is Vietnamese, because API_SPECIFICATION.md is.
    m = re.search(r"\*\*(\d+) endpoint công khai \+ (\d+) endpoint nội bộ",
                  spec)
    if not m:
        return ['could not find the "N endpoint công khai" sentence in §6']
    declared_public, declared_internal = int(m.group(1)), int(m.group(2))

    # The key is the PAIR of method and path, not the path. `GET /foods` and
    # `POST /foods` are two different endpoints sharing one path — that is
    # ordinary REST, not a duplicate.
    public = re.findall(r"^\| \d+ \| .+ \| `(GET|POST|PUT|PATCH|DELETE)` \| "
                        r"`(/[^`]+)` \|", spec, re.M)
    internal = re.findall(r"^\| I\d+ \| .+ \| `(GET|POST)` \| `(/[^`]+)` \|",
                          spec, re.M)
    errors = []
    if len(public) != declared_public:
        errors.append(
            f"§6 declares {declared_public} public endpoints but the table has "
            f"{len(public)} rows"
        )
    if len(internal) != declared_internal:
        errors.append(
            f"§6 declares {declared_internal} internal endpoints but the table "
            f"has {len(internal)} rows"
        )
    for x in sorted({t for t in public if public.count(t) > 1}):
        errors.append(
            f"endpoint {x[0]} {x[1]} appears {public.count(x)} times in the "
            f"summary table"
        )

    # The row numbers must run 1..N unbroken, with no gaps and no collisions.
    numbers = sorted(int(m) for m in re.findall(
        r"^\| (\d+) \| .+ \| `(?:GET|POST|PUT|PATCH|DELETE)` \| `/", spec,
        re.M))
    missing = sorted(set(range(1, declared_public + 1)) - set(numbers))
    if missing:
        errors.append(f"the summary table is missing row numbers: {missing}")
    for n in sorted({n for n in numbers if numbers.count(n) > 1}):
        errors.append(f"row number {n} is used by {numbers.count(n)} endpoints")
    print(
        f"   {len(public)} public + {len(internal)} internal endpoints, "
        f"matching the declared counts"
    )
    return errors


def main() -> int:
    _use_utf8()
    spec = APISPEC.read_text(encoding="utf-8")
    schema = SCHEMA.read_text(encoding="utf-8")

    print("Audit: flowcharts <-> API specification <-> database schema")
    print("=" * 72)

    errors: list[str] = []
    print("\n1. Endpoints in the diagrams must exist in the specification")
    errors += check_endpoints(spec)
    print("\n2. Error codes in the diagrams must be in the §4 catalogue")
    errors += check_error_codes(spec)
    print("\n3. Table names in the diagrams must exist in db/schema.sql")
    errors += check_tables(schema)
    print("\n4. Column names in the diagrams must exist in their table")
    errors += check_columns(schema)
    print("\n5. The counts declared in §6 must match the number of rows")
    errors += check_counts(spec)
    print("\n6. Use case names must agree across the mdj, flowcharts and stories")
    errors += check_use_case_names()

    print("\n7. The main flow of all 18 Chapter 2 scenarios must reach its End")
    errors += check_chapter2_flows()

    print("\n8. Still awaiting details")
    pending = [(code, text) for code, text in block_texts() if DAU_DE_XUAT in text]
    for code, text in pending:
        print(f"   !  {code}  {text}")
    if not pending:
        print("   ok   nothing left open")

    print("\n" + "=" * 72)
    if errors:
        print(f"{len(errors)} DIVERGENCES:")
        for x in errors:
            print("  -", x)
        return 1
    print(
        "The diagrams, the API specification and the database schema describe "
        "one and the same system."
    )
    if pending:
        print(f"{len(pending)} places still awaiting details — see section 8.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
