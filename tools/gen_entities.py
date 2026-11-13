#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the C# entity classes from `db/schema.sql`, and audit them.

Why generate them. Twenty-four tables, 225 columns. Typing each property by
hand means a column with the wrong name or the wrong nullability causes no
compile error — it causes a runtime `MySqlException`, at an endpoint nobody may
call for weeks. Generating from the schema file itself removes that whole class
of error.

Why NOT `dotnet ef dbcontext scaffold`. That tool reads a running database, so
it requires the database to be alive at build time, and it generates an
`OnModelCreating` with every index, constraint and collation — thousands of
lines nobody reads. `db/schema.sql` is the source of authority per
`db/migrations/applied/README.md`, so generating from that file generates from
the right source, and the output is small enough to read.

TWO MODES
    (default)  audit: the existing C# must match the schema, both directions
    --write    regenerate Entities/ and AppDbContext.cs

Run:
    python tools/gen_entities.py
    python tools/gen_entities.py --write
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "db" / "schema.sql"
API = ROOT / "backend" / "Api"
ENTITIES = API / "Entities"
CONTEXT = API / "Data" / "AppDbContext.cs"
#: Not generated — only AUDITED, see `_verify_enums`.
DTOS = API / "Profile" / "ProfileDtos.cs"

NAMESPACE = "Api.Entities"

#: Keywords that begin a table-level constraint rather than a column.
TABLE_LEVEL = (
    "PRIMARY KEY", "FOREIGN KEY", "UNIQUE KEY", "UNIQUE INDEX", "UNIQUE (",
    "INDEX", "KEY ", "CONSTRAINT", "CHECK",
)

TYPE_KEYWORDS = (
    "BIGINT", "INT", "SMALLINT", "TINYINT", "MEDIUMINT", "DECIMAL", "NUMERIC",
    "FLOAT", "DOUBLE", "VARCHAR", "CHAR", "TEXT", "LONGTEXT", "MEDIUMTEXT",
    "JSON", "ENUM", "SET", "DATE", "DATETIME", "TIMESTAMP", "TIME", "YEAR",
    "BOOLEAN", "BOOL", "BLOB", "BINARY",
)

#: MySQL type family -> C# type. ENUM and SET become `string`: mapping them to
#: a C# `enum` sounds tidier, but when the database gains a value the code does
#: not know about, EF throws on READ, and a perfectly valid row becomes
#: unreadable. Keep `string`, and let the validation layer check against the
#: lists in §5 of the API specification.
CS_TYPE = {
    "CHAR": "string", "VARCHAR": "string", "TEXT": "string",
    "LONGTEXT": "string", "MEDIUMTEXT": "string", "JSON": "string",
    "ENUM": "string", "SET": "string",
    "TINYINT": "byte", "SMALLINT": "ushort", "MEDIUMINT": "int",
    "INT": "uint", "BIGINT": "ulong",
    "DECIMAL": "decimal", "NUMERIC": "decimal",
    "FLOAT": "float", "DOUBLE": "double",
    "DATE": "DateOnly", "DATETIME": "DateTime", "TIMESTAMP": "DateTime",
    "TIME": "TimeOnly", "YEAR": "int",
}

#: `TINYINT(1)` in MySQL is the convention for a boolean, not a 0..255 number.
#: The schema uses it for `is_active`, `is_hard`, `was_selected`.


def _split_definitions(body: str) -> list[str]:
    """Split a CREATE TABLE body on commas OUTSIDE parentheses and quotes.

    Splitting by line would cut an `ENUM(...)` spanning several lines into
    pieces, and the first piece would not contain the `NOT NULL` sitting on a
    later line.
    """
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    in_string = False
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        if in_string:
            buf.append(c)
            if c == "\\" and i + 1 < n:
                buf.append(body[i + 1])
                i += 2
                continue
            if c == "'":
                in_string = False
        elif c == "'":
            in_string = True
            buf.append(c)
        elif c == "(":
            depth += 1
            buf.append(c)
        elif c == ")":
            depth -= 1
            buf.append(c)
        elif c == "," and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(c)
        i += 1
    if "".join(buf).strip():
        out.append("".join(buf))
    return [" ".join(d.split()) for d in out if d.strip()]


def _strip_comments(text: str) -> str:
    """Remove `--` comments while leaving quoted content untouched."""
    out: list[str] = []
    in_string = False
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == "'":
                in_string = False
        elif c == "'":
            in_string = True
            out.append(c)
        elif text.startswith("--", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def pascal(name: str) -> str:
    return "".join(p.capitalize() for p in name.split("_"))


def read_schema(text: str) -> dict[str, list[dict]]:
    """{table name: [columns...]} with the C# type inferred, in declaration
    order."""
    clean = _strip_comments(text)
    tables: dict[str, list[dict]] = {}

    for m in re.finditer(r"CREATE TABLE\s+(\w+)\s*\((.*?)\)\s*ENGINE",
                         clean, re.S):
        name, body = m.group(1), m.group(2)
        columns: list[dict] = []

        # A primary key may be declared at TABLE LEVEL:
        # `PRIMARY KEY (food_id, tag_id)`. Missing that makes EF throw
        # `requires a primary key to be defined` while building the model —
        # which means EVERY endpoint returns 500, not just the ones touching
        # that table, because the model is built once for the whole DbContext.
        table_level_key: list[str] = []
        for definition in _split_definitions(body):
            pk_match = re.match(
                r"PRIMARY KEY\s*\((.+?)\)", definition.strip(), re.I
            )
            if pk_match:
                table_level_key = [
                    c.strip().strip("`") for c in pk_match.group(1).split(",")
                ]

        for definition in _split_definitions(body):
            if definition.upper().startswith(TABLE_LEVEL):
                continue
            parts = definition.split(None, 1)
            if len(parts) < 2:
                continue
<<<<<<< HEAD
            column_name, remaining = parts[0], parts[1]
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", column_name):
                continue
            upper = remaining.upper()
            if not upper.startswith(TYPE_KEYWORDS):
                continue

            type_match = re.match(
                r"([A-Za-z]+)\s*(?:\((.*?)\))?", remaining, re.S
            )
            family = type_match.group(1).upper() if type_match else ""
            argument = (type_match.group(2) or "").strip() if type_match else ""
=======
            ten_cot, remaining = phan[0], phan[1]
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", ten_cot):
                continue
            hoa = remaining.upper()
            if not hoa.startswith(TU_KHOA_KIEU):
                continue

            km = re.match(r"([A-Za-z]+)\s*(?:\((.*?)\))?", remaining, re.S)
            ho = km.group(1).upper() if km else ""
            doi_so = (km.group(2) or "").strip() if km else ""
>>>>>>> 57de08cb4d1bf75662c388cd72fd064d2816daba

            # A primary key is implicitly NOT NULL even when unwritten.
            is_pk = "PRIMARY KEY" in upper
            nullable = "NOT NULL" not in upper and not is_pk

            cs = CS_TYPE.get(family, "string")
            if family == "TINYINT" and argument.strip() == "1":
                cs = "bool"

            # The ENUM/SET value set, kept in DECLARATION ORDER: MySQL stores
            # an ENUM by ordinal, so reordering the values changes existing
            # data.
            values = (
                re.findall(r"'([^']*)'", argument)
                if family in ("ENUM", "SET") else []
            )

            columns.append({
                "db": column_name,
                "cs": pascal(column_name),
                "type": cs,
                "null": nullable,
                # A GENERATED column is computed by the database; EF must read
                # it without writing it.
                "generated": "GENERATED" in upper,
                "pk": is_pk,
                "values": values,
            })

        if table_level_key:
            for c in columns:
                if c["db"] in table_level_key:
                    c["pk"] = True

        tables[name] = columns
    return tables


# -- Code generation ------------------------------------------------------

HEADER = """// <auto-generated>
//     GENERATED from db/schema.sql by tools/gen_entities.py — DO NOT EDIT.
//     After a schema change, run:  python tools/gen_entities.py --write
//     To audit:                    python tools/gen_entities.py
// </auto-generated>

// The `<auto-generated>` header above makes the compiler TURN OFF the nullable
// context for the whole file, so every generated `string?` warns CS8669.
// Turn it back on explicitly.
#nullable enable
"""


def _cs_type(column: dict) -> str:
    t = column["type"]
    if column["null"]:
        return t + "?"
    return t


def _initializer(column: dict) -> str:
    """An initial value, so `Nullable` does not warn about an unassigned
    property."""
    if column["null"]:
        return ""
    if column["type"] == "string":
        return " = string.Empty;"
    return ""


def render_entity(table: str, columns: list[dict]) -> str:
    class_name = pascal(table)
    lines = [HEADER, "", f"namespace {NAMESPACE};", "",
             f"/// <summary>Table <c>{table}</c>.</summary>",
             f"public class {class_name}", "{"]
    for column in columns:
        notes = []
        if column["pk"]:
            notes.append("primary key")
        if column["generated"]:
            notes.append("computed by the database — read only")
        suffix = f"  // {', '.join(notes)}" if notes else ""
        lines.append(f"    public {_cs_type(column)} {column['cs']} "
                     f"{{ get; set; }}{_initializer(column)}{suffix}")
    lines += ["}", ""]
    return "\n".join(lines)


def render_context(tables: dict[str, list[dict]]) -> str:
    lines = [
        HEADER, "",
        "using Api.Entities;",
        "using Microsoft.EntityFrameworkCore;", "",
        "namespace Api.Data;", "",
        "/// <summary>",
        "/// Maps the 24 tables of <c>db/schema.sql</c>.",
        "///",
        "/// <para><b>EF Migrations are NOT used.</b> Per",
        "/// <c>db/migrations/applied/README.md</c>, <c>db/schema.sql</c> is",
        "/// the schema's current state. Enabling Migrations would create a",
        "/// second source of authority for one schema, and the two would",
        "/// drift — <c>tools/check_schema_sql.py</c> catches that, but only",
        "/// <i>after</i> the drift. To change the schema, write a file in",
        "/// <c>db/migrations/</c>, run it, fold it into <c>schema.sql</c>,",
        "/// then run <c>python tools/gen_entities.py --write</c>.</para>",
        "/// </summary>",
        "public class AppDbContext(DbContextOptions<AppDbContext> options)",
        "    : DbContext(options)",
        "{",
    ]
    for table in tables:
        lines.append(f"    public DbSet<{pascal(table)}> {pascal(table)} "
                     "=> Set<" + pascal(table) + ">();")
    lines += ["", "    protected override void OnModelCreating("
                  "ModelBuilder b)", "    {"]
    for table, columns in tables.items():
        class_name = pascal(table)
        lines.append(f"        b.Entity<{class_name}>(e =>")
        lines.append("        {")
        lines.append(f'            e.ToTable("{table}");')
        keys = [c for c in columns if c["pk"]]
        if len(keys) == 1:
            lines.append(f"            e.HasKey(x => x.{keys[0]['cs']});")
        elif len(keys) > 1:
            # A composite key: `food_tags (food_id, tag_id)`.
            tuple_body = ", ".join(f"x.{c['cs']}" for c in keys)
            lines.append(f"            e.HasKey(x => new {{ {tuple_body} }});")
        else:
            raise AssertionError(
                f"no primary key could be extracted for table `{table}` — EF "
                "will throw `requires a primary key to be defined` while "
                "building the model"
            )
        for column in columns:
            lines.append(f'            e.Property(x => x.{column["cs"]})'
                         f'.HasColumnName("{column["db"]}");')
            if column["generated"]:
                lines.append(f"            e.Property(x => x.{column['cs']})"
                             ".ValueGeneratedOnAddOrUpdate();")
        lines.append("        });")
    lines += ["    }", "}", ""]
    return "\n".join(lines)


# -- Audit ----------------------------------------------------------------

RE_PROPERTY = re.compile(
    r'e\.Property\(x => x\.(\w+)\)\.HasColumnName\("(\w+)"\);')


def verify(tables: dict[str, list[dict]]) -> list[str]:
    """The existing C# must match the schema, in both directions."""
    errors: list[str] = []

    if not CONTEXT.exists():
        return [f"{CONTEXT.relative_to(ROOT)} does not exist — run with --write"]

    # -- 1. One entity file per table --
    on_disk = {p.stem for p in ENTITIES.glob("*.cs")}
    needed = {pascal(t) for t in tables}
    for t in sorted(needed - on_disk):
        errors.append(f"entity class {t}.cs is missing")
    for t in sorted(on_disk - needed):
        errors.append(f"{t}.cs corresponds to no table in schema.sql")

    # -- 2. One property per column, right name and right type --
    for table, columns in tables.items():
        path = ENTITIES / f"{pascal(table)}.cs"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for column in columns:
            expected = (
                f"public {_cs_type(column)} {column['cs']} {{ get; set; }}"
            )
            if expected not in text:
                errors.append(
                    f"{pascal(table)}.{column['cs']}: expected "
                    f"`{_cs_type(column)}`, not found in {path.name}"
                )

    # -- 3. A primary key must be declared for EVERY table --
    #
    # A missing `HasKey` is not thrown at compile time, it is thrown while
    # building the model — that is, on the FIRST API call, and then EVERY
    # endpoint returns 500, not just the ones touching the table without a
    # key. Exactly that happened with `food_tags`, the one table declaring
    # its `PRIMARY KEY` at table level.
    context_text = CONTEXT.read_text(encoding="utf-8")
    for table, columns in tables.items():
        keys = [c["cs"] for c in columns if c["pk"]]
        if not keys:
            errors.append(f"no primary key could be extracted for `{table}`")
            continue
        expected = (f"e.HasKey(x => x.{keys[0]});" if len(keys) == 1
                    else "e.HasKey(x => new { "
                         + ", ".join(f"x.{k}" for k in keys) + " });")
        if expected not in context_text:
            errors.append(
                f"AppDbContext is missing `{expected}` for table `{table}`"
            )

    # -- 4. The column-name mapping in DbContext must be complete and right --
    mapped = set(RE_PROPERTY.findall(context_text))
    required = {(c["cs"], c["db"]) for cols in tables.values() for c in cols}
    for cs, db in sorted(required - mapped):
        errors.append(f"AppDbContext is missing the mapping {cs} -> `{db}`")

    # -- 5. The ENUM lists in ProfileDtos.cs must match the schema --
    errors += _verify_enums(tables)

    return errors


#: {field name in Api.Profile.Enums: (table, column)}.
#:
#: Declared explicitly rather than matched by name, because the schema has TWO
#: ENUMs named `gender` with DIFFERENT value sets: `health_profiles.gender` is
#: ('male','female','other'), while `rda_reference.gender` is
#: ('male','female','all'). Matching by column name would pick the wrong one of
#: the two.
ENUM_CS = {
    "Gender": ("health_profiles", "gender"),
    "ActivityLevel": ("health_profiles", "activity_level"),
    "Goal": ("health_profiles", "goal"),
    "Severity": ("user_conditions", "severity"),
}

RE_ENUM_ARRAY = re.compile(
    r"public static readonly string\[\]\s+(\w+)\s*=\s*\[(.*?)\]\s*;", re.S)


def _verify_enums(tables: dict[str, list[dict]]) -> list[str]:
    """The four arrays in `Api.Profile.Enums` must match the schema's ENUMs.

    Those four arrays are the ONLY layer returning `400 VALIDATION_FAILED`
    with a field name for a value outside the ENUM. Without this check, adding
    a value to `db/schema.sql` would make the API reject exactly what the
    database allows — and nothing would report it, because each side stays
    self-consistent.
    """
    errors: list[str] = []
    if not DTOS.exists():
        return [f"{DTOS.relative_to(ROOT)} does not exist"]

    on_disk = {
        m.group(1): re.findall(r'"([^"]*)"', m.group(2))
        for m in RE_ENUM_ARRAY.finditer(DTOS.read_text(encoding="utf-8"))
    }

    # Both directions: a newly added array not declared in ENUM_CS is drift
    # too — it looks audited while in fact it is not.
    for name in sorted(set(on_disk) - set(ENUM_CS)):
        errors.append(
            f"Enums.{name} is not in gen_entities.py's ENUM_CS — nobody is "
            f"comparing it against the schema"
        )

    for name, (table, column_name) in ENUM_CS.items():
        if name not in on_disk:
            errors.append(f"ProfileDtos.cs is missing `string[] {name}`")
            continue
        column = next(
            (c for c in tables.get(table, []) if c["db"] == column_name), None
        )
        if column is None:
            errors.append(f"schema.sql has no column `{table}.{column_name}`")
            continue
        if column["values"] != on_disk[name]:
            errors.append(
                f"Enums.{name} = {on_disk[name]} but "
                f"{table}.{column_name} is ENUM{tuple(column['values'])}")
    return errors


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="regenerate Entities/ and AppDbContext.cs")
    args = parser.parse_args(argv)

    tables = read_schema(SCHEMA.read_text(encoding="utf-8"))
    column_count = sum(len(c) for c in tables.values())
    print(f"db/schema.sql: {len(tables)} tables · {column_count} columns")

    if args.write:
        ENTITIES.mkdir(parents=True, exist_ok=True)
        CONTEXT.parent.mkdir(parents=True, exist_ok=True)
        # Delete the class of a dropped table; otherwise it still compiles and
        # still looks like part of the schema.
        keep = {pascal(t) + ".cs" for t in tables}
        for path in ENTITIES.glob("*.cs"):
            if path.name not in keep:
                path.unlink()
                print(f"  - deleted {path.name} (table no longer exists)")
        for table, columns in tables.items():
            (ENTITIES / f"{pascal(table)}.cs").write_text(
                render_entity(table, columns), encoding="utf-8")
        CONTEXT.write_text(render_context(tables), encoding="utf-8")
        print(f"  wrote {len(tables)} classes + AppDbContext.cs")

    errors = verify(tables)
    print()
    if errors:
        print(f"{len(errors)} DIVERGENCES:")
        for x in errors:
            print("  -", x)
        return 1
    print("The C# code describes the schema correctly — column by column, "
          "in both directions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
