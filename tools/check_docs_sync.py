#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compare the four design documents against the live database.

The schema is described in five places, and they drift apart very easily:

    db/schema.sql               the source that builds the database
    docs/DATABASE_DESIGN.md     the DDL blocks plus a per-column table
    docs/database_erd.html      the relationship diagram
    docs/ERD_REVIEW.md          the review write-up for the assignment
    docs/API_SPECIFICATION.md   the JSON fields the API returns

The earlier check compared only the two middle files, so `ERD_REVIEW.md`
drifted without anyone knowing: it states the scale in TWO places, one of which
was updated while the other still said `21 bảng · 27 khóa ngoại · 14 ràng buộc
CHECK` after the schema had become 22/30/15. The same kind of defect repeated
with `API_SPECIFICATION.md`: it was still returning `origin` and `cookingMethod`
more than a month after both columns left the schema, because the file was not
in the scanned list. This checker covers all five.

It checks four groups:

    1. Table, foreign-key and CHECK counts — every claim stated in the docs
    2. Each table's columns — database ⊆ ERD HTML, and database ⊆ the doc DDL
    3. Dropped columns that the docs still list as if they existed
    4. Vietnamese diacritics in identifiers — an ERD assignment requirement

Run:
    python tools/check_docs_sync.py

Note on language: the patterns below match Vietnamese sentences inside
`docs/*.md` and `docs/database_erd.html`, so they stay exactly as written.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ERD = ROOT / "docs" / "database_erd.html"
DESIGN = ROOT / "docs" / "DATABASE_DESIGN.md"
REVIEW = ROOT / "docs" / "ERD_REVIEW.md"
APISPEC = ROOT / "docs" / "API_SPECIFICATION.md"

# Columns dropped from the schema. The documents may MENTION them in sections
# explaining "why this column is absent", but must not list them as existing.
DROPPED = ("origin", "suitable_meals", "cooking_method", "computed_at")


# API_SPECIFICATION.md writes field names in camelCase, so the check has to
# look for both forms. That very gap left `cookingMethod` and `origin` in the
# API document more than a month after both columns were dropped: the file was
# not in the scanned list, and even if it had been, a pattern looking for
# `cooking_method` could not match the `cookingMethod` in a JSON block.
def camel(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(part.capitalize() for part in rest)


# Keywords showing that a mention is historical explanation rather than a
# listing. They match Vietnamese document text, so they stay as they are.
HISTORICAL = (
    "không có cột", "KHÔNG có cột", "đã bỏ", "Bản thiết kế trước",
    "trước đây", "Trước đây", "bỏ `", "Bỏ `",
)


def read_db(database: str) -> dict:
    import pymysql

    conn = pymysql.connect(
        host=_env.get("MYSQL_HOST", "localhost"),
        port=int(_env.get("MYSQL_PORT", "3306")),
        user=_env.require("MYSQL_USER"),
        password=_env.require("MYSQL_PASSWORD"),
        database=database, charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s", (database,)
            )
            tables = sorted(r[0] for r in cur.fetchall())

            cur.execute(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = %s", (database,)
            )
            columns: dict[str, set[str]] = {}
            for table, column in cur.fetchall():
                columns.setdefault(table, set()).add(column)

            cur.execute(
                "SELECT table_name, column_name, data_type "
                "FROM information_schema.columns WHERE table_schema = %s",
                (database,)
            )
            types = {(t, col): dt.upper() for t, col, dt in cur.fetchall()}

            # Each ENUM's values. Needed separately because `data_type` only
            # returns the string 'enum' without the value list — so the type
            # family comparison in section 2b treats ENUM('a','b') and
            # ENUM('a','b','c') as identical. That very gap let the docs keep
            # `tag_type ENUM(...,'taste')` after the taste tag group was
            # dropped from the database.
            cur.execute(
                "SELECT table_name, column_name, column_type "
                "FROM information_schema.columns "
                "WHERE table_schema = %s AND data_type = 'enum'",
                (database,)
            )
            rows = cur.fetchall()
            enums = {
                (t, col): set(re.findall(r"'([^']*)'", ctype))
                for t, col, ctype in rows
            }
            # Keeps the DECLARATION ORDER, used by section 2e. Separate from
            # `enums` (a set) because 2d only needs set comparison while 2e
            # needs the order too.
            enum_order = {
                (t, col): re.findall(r"'([^']*)'", ctype)
                for t, col, ctype in rows
            }

            # The list of foreign keys, not just the count. Section 1b compares
            # only the **total** stated in the diagram's header, so two
            # relationships wrong at once — one added, one missing — cancel out
            # and nobody sees it.
            cur.execute(
                "SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, "
                "       REFERENCED_COLUMN_NAME "
                "FROM information_schema.KEY_COLUMN_USAGE "
                "WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL",
                (database,),
            )
            foreign_keys = {tuple(r) for r in cur.fetchall()}

            # UNIQUE indexes over exactly ONE column. Used to derive a
            # relationship's cardinality: a foreign key sitting on a UNIQUE
            # column makes the relationship 1:1, not N:1.
            cur.execute(
                "SELECT TABLE_NAME, MIN(COLUMN_NAME) "
                "FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = %s AND NON_UNIQUE = 0 "
                "GROUP BY TABLE_NAME, INDEX_NAME HAVING COUNT(*) = 1",
                (database,),
            )
            single_unique = {tuple(r) for r in cur.fetchall()}

            counts = {}
            for kind, key in (("FOREIGN KEY", "fk"), ("CHECK", "check")):
                cur.execute(
                    "SELECT COUNT(*) FROM information_schema.table_constraints "
                    "WHERE table_schema = %s AND constraint_type = %s",
                    (database, kind),
                )
                counts[key] = cur.fetchone()[0]
    finally:
        conn.close()

    return {
        "tables": tables, "columns": columns, "types": types,
        "enums": enums, "enum_order": enum_order,
        "foreign_keys": foreign_keys,
        "single_unique": single_unique, **counts
    }


def erd_columns(html: str) -> dict[str, set[str]]:
    return {
        m.group(1): set(re.findall(r"\['(\w+)'", m.group(2)))
        for m in re.finditer(r"\{ id:'(\w+)'.*?cols:\[(.*?)\]\s*\}", html, re.S)
    }


# Keywords that begin a type declaration, used to tell a column-declaration
# line from a continuation line of a multi-line ENUM or a CHECK expression.
TYPE_KEYWORDS = (
    "BIGINT", "INT", "SMALLINT", "TINYINT", "DECIMAL", "VARCHAR", "CHAR",
    "TEXT", "JSON", "ENUM", "SET", "DATE", "DATETIME", "TIMESTAMP", "BOOLEAN",
)


def ddl_columns(markdown: str) -> dict[str, set[str]]:
    """Extract the column names out of the CREATE TABLE blocks in a document."""
    out: dict[str, set[str]] = {}
    for m in re.finditer(
        r"CREATE TABLE (\w+)\s*\((.*?)\n\) ENGINE", markdown, re.S
    ):
        cols = set()
        for line in m.group(2).split("\n"):
            line = line.split("--")[0].strip()
            if not line or line.upper().startswith(
                ("PRIMARY", "FOREIGN", "UNIQUE", "INDEX", "KEY", "CONSTRAINT")
            ):
                continue
            # Accept only lines that REALLY declare a column: a valid name
            # followed by a data type. Without the second condition, the
            # continuation line of a multi-line ENUM or of a CHECK expression
            # is counted as a column too, yielding "columns" like `ON`, `NOT`,
            # `(100` and `'gradient_boosting')`.
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            name, rest = parts[0], parts[1].upper()
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
                continue
            if not rest.startswith(TYPE_KEYWORDS):
                continue
            cols.add(name)
        out[m.group(1)] = cols
    return out


def ddl_enums(markdown: str) -> dict[tuple[str, str], set[str]]:
    """Extract each ENUM column's value set from the CREATE TABLE blocks.

    An ENUM in the documents often spans several lines, so the whole block has
    to be joined before searching — matching line by line would only pick up
    the values on the first line.
    """
    out: dict[tuple[str, str], set[str]] = {}
    for m in re.finditer(
        r"CREATE TABLE (\w+)\s*\((.*?)\n\) ENGINE", markdown, re.S
    ):
        table, body = m.group(1), m.group(2)
        # Strip end-of-line comments before joining, so an example written in
        # a comment is not read as one of the ENUM's values.
        clean = "\n".join(line.split("--")[0] for line in body.split("\n"))
        for col in re.finditer(
            r"([a-z_][a-z0-9_]*)\s+ENUM\s*\((.*?)\)", clean, re.S | re.I
        ):
            out[(table, col.group(1))] = set(
                re.findall(r"'([^']*)'", col.group(2))
            )
    return out


def type_family(declared: str) -> str:
    """Reduce a type to its family so it can be compared.

    The ERD HTML writes types in short form — `ENUM` without its value list,
    `BIGINT` without UNSIGNED — so a character-by-character comparison is
    impossible. But the **family** must match: a column that is ENUM in the
    database and written VARCHAR on the diagram is real drift, and that is
    exactly the defect that occurred with `rda_reference.nutrient`.
    """
    declared = declared.upper()
    for family in (
        "ENUM", "SET", "JSON", "VARCHAR", "CHAR", "DECIMAL",
        "DATETIME", "DATE", "TEXT", "BIGINT", "SMALLINT", "TINYINT", "INT",
    ):
        if declared.startswith(family):
            return family
    return declared


def has_diacritics(text: str) -> bool:
    if any(ord(ch) > 127 for ch in text):
        return True
    return any(
        unicodedata.combining(ch) for ch in unicodedata.normalize("NFD", text)
    )


def main() -> int:
    _env.use_utf8()
    db = read_db("nutrition_rec")
    n_tables = len(db["tables"])
    problems: list[str] = []

    print("=" * 72)
    print("COMPARING THE DOCUMENTS AGAINST THE DATABASE")
    print("=" * 72)
    print(
        f"\nDatabase: {n_tables} tables · {db['fk']} foreign keys · "
        f"{db['check']} CHECK constraints"
    )

    # -- 1. Every claim about the scale --
    print("\n1. Scale claims in the documents")
    pattern = re.compile(
        r"(\d+)\s*bảng\s*·\s*(\d+)\s*khóa ngoại\s*·\s*(\d+)\s*ràng buộc CHECK"
    )
    found = 0
    for path in (DESIGN, REVIEW, ROOT / "db" / "schema.sql"):
        text = path.read_text(encoding="utf-8")
        for m in pattern.finditer(text):
            found += 1
            lineno = text[: m.start()].count("\n") + 1
            claim = tuple(int(g) for g in m.groups())
            actual = (n_tables, db["fk"], db["check"])
            mark = "ok " if claim == actual else "BAD"
            print(
                f"   {mark} {path.name}:{lineno}  "
                f"{claim[0]} tables · {claim[1]} FK · {claim[2]} CHECK"
            )
            if claim != actual:
                problems.append(
                    f"{path.name}:{lineno} claims "
                    f"{claim[0]}/{claim[1]}/{claim[2]}, actually "
                    f"{actual[0]}/{actual[1]}/{actual[2]}"
                )
    print(f"   {found} places make the claim")

    # -- 1c. The diagram's relationship list, and each one's cardinality --
    #
    # Section 1b compares only the **total** stated in the header. The total
    # matching while the list is wrong is perfectly possible: add one
    # relationship that does not exist and drop one that does, and the total is
    # unchanged. This is the first thing a reader of an ERD looks at, so each
    # relationship has to be compared.
    #
    # Cardinality is derived from the database rather than copied by hand: a
    # foreign key placed on a column with a **single-column** UNIQUE index
    # makes the relationship 1:1 — each parent row matches at most one child
    # row. Otherwise it is N:1.
    print("\n1c. The diagram's relationship list")
    erd_relations = {
        (a, b, c, d): card
        for a, b, c, d, card in re.findall(
            r"\['(\w+)','(\w+)','(\w+)','(\w+)','([^']*)'\]",
            ERD.read_text(encoding="utf-8"),
        )
    }
    db_fk = db["foreign_keys"]

    only_erd = sorted(set(erd_relations) - db_fk)
    only_db = sorted(db_fk - set(erd_relations))
    for a, b, c, d in only_erd:
        print(
            f"   BAD  the diagram draws `{a}.{b}` -> `{c}.{d}` which the "
            f"database does not have"
        )
        problems.append(
            f"ERD HTML: relationship `{a}.{b}` -> `{c}.{d}` does not exist"
        )
    for a, b, c, d in only_db:
        print(
            f"   BAD  the database has `{a}.{b}` -> `{c}.{d}` which the "
            f"diagram is missing"
        )
        problems.append(
            f"ERD HTML: relationship `{a}.{b}` -> `{c}.{d}` is missing"
        )

    wrong_card = 0
    for key in sorted(set(erd_relations) & db_fk):
        table, column = key[0], key[1]
        expected = "1:1" if (table, column) in db["single_unique"] else "N:1"
        stated = erd_relations[key]
        if stated != expected:
            wrong_card += 1
            print(
                f"   BAD  {key[0]}.{key[1]} -> {key[2]}.{key[3]}: the diagram "
                f"says {stated}, it must be {expected}"
            )
            problems.append(
                f"ERD HTML: cardinality of `{key[0]}.{key[1]}` says {stated}, "
                f"it must be {expected}"
            )

    if not only_erd and not only_db and not wrong_card:
        ones = sum(
            1 for k in db_fk if (k[0], k[1]) in db["single_unique"]
        )
        print(
            f"   ok   {len(db_fk)} relationships match in both directions, "
            f"cardinality correct ({ones} are 1:1, {len(db_fk) - ones} are N:1)"
        )

    # -- 2. Each table's columns --
    print("\n2. Each table's columns")
    erd = erd_columns(ERD.read_text(encoding="utf-8"))
    ddl = ddl_columns(DESIGN.read_text(encoding="utf-8"))

    for label, source in (("ERD HTML", erd), ("DATABASE_DESIGN", ddl)):
        missing_tables = sorted(set(db["tables"]) - set(source))
        missing_cols = extra_cols = 0
        for table in db["tables"]:
            gap = db["columns"][table] - source.get(table, set())
            if gap:
                missing_cols += len(gap)
                problems.append(
                    f"{label}: `{table}` is missing {', '.join(sorted(gap))}"
                )
            # The reverse direction: a column the documents still list which
            # the database has dropped. Without this check, `code` stayed on
            # the diagram for days after being removed from the schema,
            # because a one-way comparison cannot see it.
            over = source.get(table, set()) - db["columns"][table]
            if over:
                extra_cols += len(over)
                problems.append(
                    f"{label}: `{table}` still lists "
                    f"{', '.join(sorted(over))} — the database has no such "
                    f"column"
                )
        mark = (
            "ok " if not missing_tables and not missing_cols and not extra_cols
            else "BAD"
        )
        print(
            f"   {mark} {label:<18} {len(source)}/{n_tables} tables, "
            f"{missing_cols} columns missing, {extra_cols} surplus"
        )
        if missing_tables:
            problems.append(
                f"{label}: missing tables {', '.join(missing_tables)}"
            )

    # -- 1b. The diagram's header --
    #
    # The diagram states the scale in a DIFFERENT SENTENCE from the markdown
    # documents: "22 bảng · 29 quan hệ" instead of "… khóa ngoại · … ràng buộc
    # CHECK". The check in section 1 cannot match that form, so the header was
    # out of date for a while without anyone noticing — it said 30
    # relationships after `foods.updated_by` was dropped.
    print("\n1b. The diagram's header")
    html_head = ERD.read_text(encoding="utf-8")
    header_match = re.search(r"<span>(\d+) bảng · (\d+) quan hệ</span>", html_head)
    if header_match is None:
        problems.append("ERD HTML: no header stating the scale was found")
        print("   BAD  no header found")
    else:
        claim = (int(header_match.group(1)), int(header_match.group(2)))
        actual = (n_tables, db["fk"])
        mark = "ok " if claim == actual else "BAD"
        print(f"   {mark} {claim[0]} tables · {claim[1]} relationships")
        if claim != actual:
            problems.append(
                f"the ERD HTML header states {claim[0]} tables · {claim[1]} "
                f"relationships, actually {actual[0]} · {actual[1]}"
            )

    # -- 2b. Each column's type family on the diagram --
    print("\n2b. Type families on the diagram")
    erd_types: dict[tuple[str, str], str] = {}
    html = ERD.read_text(encoding="utf-8")
    for m in re.finditer(r"\{ id:'(\w+)'.*?cols:\[(.*?)\]\s*\}", html, re.S):
        for cm in re.finditer(r"\['(\w+)','([^']*)'", m.group(2)):
            erd_types[(m.group(1), cm.group(1))] = cm.group(2)

    mismatched = 0
    for (table, column), declared in sorted(erd_types.items()):
        actual = db["types"].get((table, column))
        if actual is None:
            continue
        if type_family(declared) != type_family(actual):
            mismatched += 1
            problems.append(
                f"ERD HTML: `{table}.{column}` says {declared}, the database "
                f"has {actual}"
            )
            print(
                f"   BAD  {table}.{column}  ERD={declared}  database={actual}"
            )
    if not mismatched:
        print(f"   ok   {len(erd_types)} columns, type families all match")

    # -- 2d. ENUM values in DATABASE_DESIGN.md --
    #
    # Section 2b compares only the type FAMILY, so to it ENUM('a','b') and
    # ENUM('a','b','c') are one and the same. That gap let the documents keep
    # `tags.tag_type` with the value 'taste' long after the taste tag group was
    # dropped from the database — no check complained, because both sides
    # "are an ENUM".
    print("\n2d. ENUM values in DATABASE_DESIGN.md")
    doc_enums = ddl_enums(DESIGN.read_text(encoding="utf-8"))
    checked = mismatches = 0
    for (table, column), stated in sorted(doc_enums.items()):
        actual = db["enums"].get((table, column))
        if actual is None:
            continue
        checked += 1
        if stated != actual:
            mismatches += 1
            surplus = ", ".join(sorted(stated - actual)) or "-"
            missing = ", ".join(sorted(actual - stated)) or "-"
            print(
                f"   BAD  {table}.{column}  surplus: {surplus}  ·  "
                f"missing: {missing}"
            )
            problems.append(
                f"DATABASE_DESIGN: `{table}.{column}` ENUM differs from the "
                f"database (surplus: {surplus}, missing: {missing})"
            )
    if not mismatches:
        print(f"   ok   {checked} ENUM columns, value sets all match")

    # -- 2e. ENUM values displayed on the diagram --
    #
    # The diagram prints each ENUM column's values so a reader need not open
    # the schema, so that list must match the database **including its order**:
    # an ENUM's order is meaning, not decoration — `severity_min` runs from
    # `mild` to `severe` and MySQL compares by declaration order. Sorting both
    # sides and comparing as sets would let a diagram printing the severity
    # scale backwards pass.
    print("\n2e. ENUM values displayed on the diagram")
    erd_enum_values: dict[tuple[str, str], str] = {}
    for m in re.finditer(r"\{ id:'(\w+)'.*?cols:\[(.*?)\]\s*\}", html, re.S):
        table = m.group(1)
        for cm in re.finditer(
            r"\['(\w+)','([^']*)','([^']*)','([^']*)'\]", m.group(2)
        ):
            erd_enum_values[(table, cm.group(1))] = cm.group(4)

    db_enum_order = {}
    for (table, column), values in db["enum_order"].items():
        db_enum_order[(table, column)] = "|".join(values)

    mismatches = 0
    for key in sorted(set(erd_enum_values) | set(db_enum_order)):
        stated = erd_enum_values.get(key)
        actual = db_enum_order.get(key)
        if stated == actual:
            continue
        mismatches += 1
        if actual is None:
            print(
                f"   BAD  {key[0]}.{key[1]}: the diagram prints values but the "
                f"database column is not an ENUM"
            )
            problems.append(
                f"ERD HTML: `{key[0]}.{key[1]}` prints ENUM values but the "
                f"column is not an ENUM"
            )
        elif stated is None:
            print(f"   BAD  {key[0]}.{key[1]}: the value list is missing")
            problems.append(
                f"ERD HTML: `{key[0]}.{key[1]}` is missing its ENUM value list"
            )
        else:
            print(f"   BAD  {key[0]}.{key[1]}:")
            print(f"       diagram:  {stated}")
            print(f"       database: {actual}")
            problems.append(
                f"ERD HTML: `{key[0]}.{key[1]}` ENUM value list differs from "
                f"the database"
            )
    if not mismatches:
        total = sum(len(v) for v in db["enum_order"].values())
        print(
            f"   ok   {len(db_enum_order)} ENUM/SET columns, {total} values, "
            f"matching including order"
        )

    # -- 2c. Is the diagram's column array broken --
    #
    # Two array elements next to each other with a MISSING COMMA are still
    # valid JavaScript — it becomes an indexing operation and yields
    # `undefined`:
    #
    #     ['vitamin_c_mg','DECIMAL(6,2)','']      <- missing comma
    #     ['updated_at','DATETIME','']
    #
    # The card-drawing loop then throws at exactly that table and STOPS DEAD —
    # the diagram shows only the tables before it and draws no relationship
    # lines at all. `node --check` cannot catch it because the syntax is
    # valid, and the column-name comparison cannot catch it either because the
    # names are still in the text.
    print("\n2c. The diagram's column array")
    gaps = []
    for m in re.finditer(r"\]\s*\n\s*\[", html):
        gaps.append(html[: m.start()].count("\n") + 1)
    if gaps:
        for line in gaps:
            problems.append(
                f"ERD HTML line {line}: missing comma between two array "
                f"elements — the diagram will stop drawing from this table on"
            )
            print(
                f"   BAD  line {line}: missing comma between two array elements"
            )
    else:
        print("   ok   no missing comma between elements anywhere")

    # -- 3. Dropped columns the documents still list --
    print("\n3. Columns dropped from the schema")
    live = {c for cols in db["columns"].values() for c in cols}
    # A flag rather than a substring search over `problems`: the earlier
    # version decided whether to print the all-clear line by looking for a
    # phrase inside its own messages, so rewording a message silently
    # disabled the conclusion.
    found_dropped = False
    for path in (DESIGN, REVIEW, ERD, APISPEC):
        text = path.read_text(encoding="utf-8")
        for col in DROPPED:
            if col in live:
                continue
            # The quotes/backticks on both sides are deliberate: `origin` must
            # match while `originalItem` must not, and the latter really does
            # occur in the API document.
            names = {col, camel(col)}
            pattern = "|".join(
                [rf"`{t}`" for t in sorted(names)]
                + [rf'"{t}"\s*:' for t in sorted(names)]
                + [rf"\['{col}'"]
            )
            for m in re.finditer(pattern, text):
                lineno = text[: m.start()].count("\n") + 1
                line = text.split("\n")[lineno - 1]
                # A mention inside a historical explanation is skipped.
                context = "\n".join(
                    text.split("\n")[max(0, lineno - 16): lineno + 1]
                )
                if any(h in context for h in HISTORICAL):
                    continue
                found_dropped = True
                problems.append(
                    f"{path.name}:{lineno} still lists `{col}` — it was "
                    f"dropped from the schema"
                )
                print(f"   BAD  {path.name}:{lineno}  {line.strip()[:60]}")
    if not found_dropped:
        print("   ok   nowhere lists a dropped column")

    # -- 4. Vietnamese diacritics in identifiers --
    print("\n4. Vietnamese diacritics in identifiers (ERD assignment rule)")
    distinct = set(db["tables"]) | {
        c for cols in db["columns"].values() for c in cols
    }
    bad = sorted(x for x in distinct if has_diacritics(x))
    n_positions = sum(len(v) for v in db["columns"].values())
    print(
        f"   {len(distinct)} distinct identifiers "
        f"({n_tables} table names + {len(distinct) - n_tables} column names), "
        f"{n_positions} column positions"
    )
    if bad:
        print(
            f"   BAD  {len(bad)} identifiers carry diacritics: {', '.join(bad)}"
        )
        problems.extend(f"identifier with diacritics: {x}" for x in bad)
    else:
        print("   ok   no identifier contains a diacritic or a non-ASCII char")

    # -- 4b. The identifier-count sentence in ERD_REVIEW.md --
    #
    # Section 4 above only MEASURES and prints; it does not compare against the
    # number written in the document. That gap let a wrong sentence sit
    # undisturbed: ERD_REVIEW.md said "161 định danh phân biệt — 22 tên bảng
    # cộng 139 tên cột phân biệt, trên tổng 216 vị trí cột" while the database
    # measured 160 / 138 / 213. Wrong from the start, and caught by no check
    # because nobody compared the two sides.
    #
    # The same kind of defect as "two places state the scale and only one was
    # updated" in section 1 — so it is cured the same way: read the number out
    # of the sentence and compare it with the measurement.
    print("\n4b. The identifier counts written in ERD_REVIEW.md")
    review = REVIEW.read_text(encoding="utf-8")
    sentence = re.search(
        r"\*\*(\d+) định danh phân biệt\*\*\s*—\s*(\d+) tên bảng cộng\s+"
        r"(\d+) tên cột phân biệt,\s+trên tổng (\d+) vị trí cột",
        review,
    )
    if not sentence:
        print("   BAD  sentence not found — has the search pattern gone stale?")
        problems.append(
            "ERD_REVIEW.md: the identifier-count sentence was not found"
        )
    else:
        stated_counts = [int(g) for g in sentence.groups()]
        measured = [
            len(distinct), n_tables, len(distinct) - n_tables, n_positions
        ]
        labels = (
            "distinct identifiers", "table names", "column names",
            "column positions",
        )
        line = review[: sentence.start()].count("\n") + 1
        wrong = [
            (label, says, got)
            for label, says, got in zip(labels, stated_counts, measured)
            if says != got
        ]
        for label, says, got in wrong:
            print(
                f"   BAD  ERD_REVIEW.md:{line}  {label}: says {says}, "
                f"measured {got}"
            )
            problems.append(
                f"ERD_REVIEW.md:{line} {label}: says {says}, the database has "
                f"{got}"
            )
        if not wrong:
            print(
                f"   ok   ERD_REVIEW.md:{line}  "
                f"{stated_counts[0]} identifiers · {stated_counts[1]} tables · "
                f"{stated_counts[2]} columns · {stated_counts[3]} positions"
            )

    # -- Conclusion --
    print("\n" + "=" * 72)
    if problems:
        print(f"{len(problems)} problems:\n")
        for p in problems:
            print(f"  BAD  {p}")
    else:
        print("EVERYTHING MATCHES — five sources describe one schema.")
    print("=" * 72)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
