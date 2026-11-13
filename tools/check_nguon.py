#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Every source cited in the system must appear in the bibliography.

Why it is needed. The nutrient thresholds in `condition_rules` record their
provenance in the `note` column, and `rda_reference` records it in `source`.
Adding a medical condition with a new guideline adds a source — and nothing
prompts anyone to add it to the bibliography. The consequence is not a runtime
error: the report still prints perfectly, it simply cites a guideline the
bibliography does not list. When an examiner asks "where does this number come
from", the report itself cannot answer.

The check runs **from the database to the document**, not the other way. The
reverse cannot be automated: the body text names sources in prose rather than
with `[n]` citation markers, so a bibliography entry nobody uses is something
only a reader notices.

`DB_MARKERS` is a hand-written table: each source in the database maps to a
marker that identifies it in the bibliography. Hand-written because the string
in `note` is Vietnamese prose ("Hướng dẫn tăng acid uric máu và gút của Nhật
Bản") while the bibliography entry is the original English title ("Japanese
Society of Gout and Uric & Nucleic Acids") — no string comparison connects the
two.

Run:
    python tools/check_nguon.py

Note on language: the marker strings below stay as they are, because they are
matched against **database content and the Vietnamese bibliography**.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

CONTENT_DATA = ROOT / "tools" / "baocao" / "noidung_data.py"

#: A marker in `condition_rules.note` / `rda_reference.source` -> the marker
#: that identifies that source inside `TAI_LIEU`.
#:
#: The key is the string as it appears in the database; the value is the
#: string that must be present in the bibliography.
DB_MARKERS: dict[str, str] = {
    "WHO": "World Health Organization",
    "KDIGO": "Kidney Disease: Improving Global Outcomes",
    "ADA": "American Diabetes Association",
    "Dietary Guidelines for Americans 2015": "Dietary Guidelines for Americans",
    "AHA/ACC 2019": "2019 ACC/AHA Guideline",
    "gút của Nhật Bản": "Japanese Society of Gout",
    "NIN Vietnamese RDAs 2016": "Nhu cầu dinh dưỡng khuyến nghị cho người Việt Nam",
    "WHO carbohydrate guideline 2023": "Carbohydrate intake for adults and children",
}

#: Sources cited in the code or in the design documents, not in the database.
#:
#: They still have to be listed, because the body text or a code comment names
#: them.
CODE_SOURCES: dict[str, str] = {
    "Mifflin-St Jeor": "Mifflin",
    "WHO Expert Consultation (2004)": "Appropriate body-mass index for Asian",
    "Bảng thành phần thực phẩm Việt Nam 2007": "Bảng thành phần thực phẩm Việt Nam",
    "USDA FoodData Central": "FoodData Central",
    "Rocchio": "Rocchio",
    "scikit-learn": "Scikit-learn",
    "chặn dưới Wilson": "Wilson",
    "nDCG": "Cumulated gain-based evaluation",
}

#: Entries still awaiting a version or a year. Not treated as an error, but
#: reported on every run — so it does not sit quietly in the submitted copy.
PLACEHOLDER_MARK = "[bổ sung"


def load_bibliography() -> list[str]:
    spec = importlib.util.spec_from_file_location("noidung_data", CONTENT_DATA)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # `TAI_LIEU` and the `"tl"` kind are names inside `noidung_data.py`, which
    # holds report content and stays Vietnamese.
    return [body for kind, body in module.TAI_LIEU if kind == "tl"]


def sources_in_database() -> set[str]:
    import pymysql

    cn = pymysql.connect(
        host=_env.get("MYSQL_HOST", "localhost"),
        port=int(_env.get("MYSQL_PORT", "3306")),
        user=_env.require("MYSQL_USER"),
        password=_env.require("MYSQL_PASSWORD"),
        database="nutrition_rec",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with cn.cursor() as cur:
            cur.execute(
                "SELECT note FROM condition_rules WHERE note IS NOT NULL"
            )
            notes = [d["note"] for d in cur.fetchall()]
            cur.execute(
                "SELECT DISTINCT source FROM rda_reference "
                "WHERE source IS NOT NULL"
            )
            notes += [d["source"] for d in cur.fetchall()]
    finally:
        cn.close()

    found = set()
    for text in notes:
        for marker in DB_MARKERS:
            if marker in text:
                found.add(marker)
    return found


def main() -> int:
    _env.use_utf8()
    print("Source audit: database and code -> bibliography")
    print("=" * 72)

    entries = load_bibliography()
    joined = "\n".join(entries)
    print(f"{len(entries)} entries in TAI_LIEU\n")

    errors: list[str] = []
    passed = 0

    print("1. Sources cited in the database")
    in_database = sources_in_database()
    for marker in sorted(in_database):
        needed = DB_MARKERS[marker]
        if needed in joined:
            passed += 1
            print(f"   ok   {marker:38s} -> {needed[:36]}")
        else:
            errors.append(
                f"the database cites {marker!r} but the bibliography has no "
                f"{needed!r}"
            )
            print(f"   BAD  {marker:38s} -> MISSING {needed!r}")

    unused = sorted(set(DB_MARKERS) - in_database)
    if unused:
        print(
            f"\n   ~ {len(unused)} markers declared in DB_MARKERS that the "
            f"database no longer cites:"
        )
        for marker in unused:
            print(f"       {marker}")
        print("     If the rule was dropped, remove its row from DB_MARKERS.")

    print("\n2. Sources cited in the code and the design documents")
    for name, needed in sorted(CODE_SOURCES.items()):
        if needed in joined:
            passed += 1
            print(f"   ok   {name:38s} -> {needed[:36]}")
        else:
            errors.append(
                f"the code cites {name!r} but the bibliography has no "
                f"{needed!r}"
            )
            print(f"   BAD  {name:38s} -> MISSING {needed!r}")

    print("\n3. Entries still awaiting details")
    pending = [e for e in entries if PLACEHOLDER_MARK in e]
    if pending:
        for entry in pending:
            print(f"   !  {entry[:92]}")
        print(
            f"   {len(pending)} entries need a version or a year before "
            f"submission."
        )
    else:
        print("   ok   no entry has a blank left")

    print("\n" + "=" * 72)
    if errors:
        print(f"{passed} checks passed, {len(errors)} FAILED:")
        for x in errors:
            print("  -", x)
        return 1
    print(f"All {passed} cited sources are present in the bibliography.")
    if pending:
        print(f"{len(pending)} entries still awaiting details — see section 3.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
