#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Đối chiếu ba tài liệu thiết kế với CSDL thật.

Lược đồ được mô tả ở bốn nơi, và chúng rất dễ lệch nhau:

    db/schema.sql           nguồn để dựng CSDL
    docs/DATABASE_DESIGN.md khối DDL + bảng mô tả từng cột
    docs/database_erd.html  sơ đồ quan hệ
    docs/ERD_REVIEW.md      bản rà soát để nộp bài tập

Phép kiểm trước đây chỉ đối chiếu hai tệp giữa, nên `ERD_REVIEW.md` lệch mà
không ai biết: nó nêu quy mô ở HAI chỗ, một chỗ được cập nhật còn chỗ kia vẫn
ghi `21 bảng · 27 khóa ngoại · 14 ràng buộc CHECK` sau khi lược đồ đã thành
22/30/15. Bộ này kiểm cả bốn.

Kiểm bốn nhóm:

    1. Số bảng, khóa ngoại, ràng buộc CHECK — mọi chỗ phát biểu trong tài liệu
    2. Cột của từng bảng — CSDL ⊆ ERD HTML, và CSDL ⊆ khối DDL trong tài liệu
    3. Cột đã bỏ mà tài liệu còn nhắc như cột đang tồn tại
    4. Dấu tiếng Việt trong định danh — yêu cầu của bài tập ERD

Chạy:
    python tools/check_docs_sync.py
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

# Cột đã bỏ khỏi lược đồ. Tài liệu được phép NHẮC chúng trong các mục giải
# thích "vì sao không có cột này", nhưng không được liệt kê như cột đang có.
DROPPED = ("origin", "suitable_meals", "cooking_method", "computed_at")

# Từ khóa cho thấy một lần nhắc là phần giải thích lịch sử, không phải liệt kê.
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

            # Giá trị của từng ENUM. Cần riêng vì `data_type` chỉ trả về
            # chuỗi 'enum', không kèm danh sách giá trị — nên phép so họ
            # kiểu ở mục 2b coi ENUM('a','b') và ENUM('a','b','c') là giống
            # nhau. Đúng khoảng trống đó đã để tài liệu giữ `tag_type
            # ENUM(...,'taste')` sau khi nhóm nhãn vị bị bỏ khỏi CSDL.
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
            # Giữ nguyên THỨ TỰ khai báo, dùng cho mục 2e. Tách khỏi `enums`
            # (là tập hợp) vì mục 2d chỉ cần so tập, còn 2e cần so cả thứ tự.
            enum_order = {
                (t, col): re.findall(r"'([^']*)'", ctype)
                for t, col, ctype in rows
            }

            # Danh sách khóa ngoại, không chỉ số lượng. Mục 1b chỉ so
            # **tổng** quan hệ trong tiêu đề sơ đồ, nên hai quan hệ cùng lúc
            # một sai một đúng sẽ triệt tiêu nhau và không ai thấy.
            cur.execute(
                "SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, "
                "       REFERENCED_COLUMN_NAME "
                "FROM information_schema.KEY_COLUMN_USAGE "
                "WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL",
                (database,),
            )
            foreign_keys = {tuple(r) for r in cur.fetchall()}

            # Chỉ mục UNIQUE chỉ gồm MỘT cột. Dùng để suy bản số quan hệ:
            # khóa ngoại nằm trên một cột UNIQUE thì quan hệ là 1:1, không
            # phải N:1.
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


# Từ khóa mở đầu một khai báo kiểu, dùng để phân biệt dòng khai báo cột với
# dòng nối tiếp của ENUM nhiều dòng hoặc biểu thức CHECK.
TYPE_KEYWORDS = (
    "BIGINT", "INT", "SMALLINT", "TINYINT", "DECIMAL", "VARCHAR", "CHAR",
    "TEXT", "JSON", "ENUM", "SET", "DATE", "DATETIME", "TIMESTAMP", "BOOLEAN",
)


def ddl_columns(markdown: str) -> dict[str, set[str]]:
    """Bóc tên cột ra khỏi các khối CREATE TABLE trong tài liệu."""
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
            # Chỉ nhận dòng THỰC SỰ khai báo cột: tên hợp lệ, theo sau là một
            # kiểu dữ liệu. Thiếu điều kiện thứ hai thì dòng nối tiếp của một
            # ENUM nhiều dòng hay một biểu thức CHECK cũng bị đếm thành cột,
            # cho ra những "cột" như `ON`, `NOT`, `(100`, `'gradient_boosting')`.
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
    """Bóc tập giá trị của mỗi cột ENUM trong các khối CREATE TABLE.

    ENUM trong tài liệu hay trải nhiều dòng, nên phải gộp cả khối lại rồi mới
    tìm — bắt từng dòng một sẽ chỉ lấy được phần giá trị nằm ở dòng đầu.
    """
    out: dict[tuple[str, str], set[str]] = {}
    for m in re.finditer(
        r"CREATE TABLE (\w+)\s*\((.*?)\n\) ENGINE", markdown, re.S
    ):
        table, body = m.group(1), m.group(2)
        # Gỡ chú thích cuối dòng trước khi gộp, để một ví dụ viết trong chú
        # thích không bị đọc nhầm thành giá trị của ENUM.
        clean = "\n".join(line.split("--")[0] for line in body.split("\n"))
        for col in re.finditer(
            r"([a-z_][a-z0-9_]*)\s+ENUM\s*\((.*?)\)", clean, re.S | re.I
        ):
            out[(table, col.group(1))] = set(
                re.findall(r"'([^']*)'", col.group(2))
            )
    return out


def type_family(declared: str) -> str:
    """Rút kiểu về họ để so sánh được.

    ERD HTML viết kiểu rút gọn — `ENUM` không kèm danh sách giá trị, `BIGINT`
    không kèm UNSIGNED — nên không so khớp từng ký tự được. Nhưng **họ** kiểu
    thì phải khớp: một cột là ENUM trong CSDL mà ghi VARCHAR trên sơ đồ là
    lệch thật, và đó đúng là lỗi đã xảy ra với `rda_reference.nutrient`.
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
    db = read_db("nutrition_rec")
    n_tables = len(db["tables"])
    problems: list[str] = []

    print("═" * 72)
    print("ĐỐI CHIẾU TÀI LIỆU VỚI CSDL")
    print("═" * 72)
    print(
        f"\nCSDL: {n_tables} bảng · {db['fk']} khóa ngoại · "
        f"{db['check']} ràng buộc CHECK"
    )

    # ── 1. Mọi phát biểu về quy mô ──
    print("\n1. Phát biểu về quy mô trong tài liệu")
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
            mark = "✓" if claim == actual else "✗"
            print(
                f"   {mark} {path.name}:{lineno}  "
                f"{claim[0]} bảng · {claim[1]} FK · {claim[2]} CHECK"
            )
            if claim != actual:
                problems.append(
                    f"{path.name}:{lineno} nêu {claim[0]}/{claim[1]}/{claim[2]}, "
                    f"thực tế {actual[0]}/{actual[1]}/{actual[2]}"
                )
    print(f"   {found} chỗ phát biểu")

    # ── 1c. Danh sách quan hệ trên sơ đồ, và bản số của từng quan hệ ──
    #
    # Mục 1b chỉ so **tổng** số quan hệ ghi ở tiêu đề. Tổng khớp mà danh sách
    # sai vẫn hoàn toàn có thể: thêm một quan hệ không tồn tại rồi bỏ một
    # quan hệ có thật thì tổng không đổi. Đây là thứ người đọc ERD nhìn vào
    # đầu tiên, nên phải so từng quan hệ.
    #
    # Bản số suy từ CSDL chứ không chép tay: khóa ngoại đặt trên một cột có
    # chỉ mục UNIQUE **một cột** thì quan hệ là 1:1 — mỗi dòng bảng cha ứng
    # với nhiều nhất một dòng bảng con. Ngược lại là N:1.
    print("\n1c. Danh sách quan hệ trên sơ đồ")
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
        print(f"   ✗ sơ đồ vẽ `{a}.{b}` → `{c}.{d}` nhưng CSDL không có")
        problems.append(f"ERD HTML: quan hệ `{a}.{b}` → `{c}.{d}` không tồn tại")
    for a, b, c, d in only_db:
        print(f"   ✗ CSDL có `{a}.{b}` → `{c}.{d}` nhưng sơ đồ thiếu")
        problems.append(f"ERD HTML: thiếu quan hệ `{a}.{b}` → `{c}.{d}`")

    wrong_card = 0
    for key in sorted(set(erd_relations) & db_fk):
        table, column = key[0], key[1]
        expected = "1:1" if (table, column) in db["single_unique"] else "N:1"
        stated = erd_relations[key]
        if stated != expected:
            wrong_card += 1
            print(
                f"   ✗ {key[0]}.{key[1]} → {key[2]}.{key[3]}: sơ đồ ghi "
                f"{stated}, phải là {expected}"
            )
            problems.append(
                f"ERD HTML: bản số `{key[0]}.{key[1]}` ghi {stated}, "
                f"phải là {expected}"
            )

    if not only_erd and not only_db and not wrong_card:
        ones = sum(
            1 for k in db_fk if (k[0], k[1]) in db["single_unique"]
        )
        print(
            f"   ✓ {len(db_fk)} quan hệ khớp hai chiều, bản số đúng "
            f"({ones} quan hệ 1:1, {len(db_fk) - ones} quan hệ N:1)"
        )

    # ── 2. Cột của từng bảng ──
    print("\n2. Cột của từng bảng")
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
                    f"{label}: `{table}` thiếu {', '.join(sorted(gap))}"
                )
            # Chiều ngược lại: cột tài liệu còn liệt kê mà CSDL đã bỏ.
            # Thiếu phép kiểm này thì `code` vẫn nằm trên sơ đồ nhiều ngày
            # sau khi đã gỡ khỏi lược đồ, vì phép so một chiều không thấy.
            over = source.get(table, set()) - db["columns"][table]
            if over:
                extra_cols += len(over)
                problems.append(
                    f"{label}: `{table}` còn thừa {', '.join(sorted(over))} "
                    f"— CSDL không có cột này"
                )
        mark = "✓" if not missing_tables and not missing_cols and not extra_cols else "✗"
        print(
            f"   {mark} {label:<18} {len(source)}/{n_tables} bảng, "
            f"{missing_cols} cột thiếu, {extra_cols} cột thừa"
        )
        if missing_tables:
            problems.append(f"{label}: thiếu bảng {', '.join(missing_tables)}")

    # ── 1b. Tiêu đề trong sơ đồ ──
    #
    # Sơ đồ nêu quy mô bằng CÂU KHÁC các tài liệu markdown: "22 bảng · 29
    # quan hệ" thay vì "… khóa ngoại · … ràng buộc CHECK". Phép kiểm ở mục 1
    # không bắt được dạng này, nên tiêu đề đã lạc hậu một thời gian mà không
    # ai thấy — nó ghi 30 quan hệ sau khi `foods.updated_by` bị bỏ.
    print("\n1b. Tiêu đề trong sơ đồ")
    html_head = ERD.read_text(encoding="utf-8")
    hm = re.search(r"<span>(\d+) bảng · (\d+) quan hệ</span>", html_head)
    if hm is None:
        problems.append("ERD HTML: không tìm thấy tiêu đề nêu quy mô")
        print("   ✗ không tìm thấy tiêu đề")
    else:
        claim = (int(hm.group(1)), int(hm.group(2)))
        actual = (n_tables, db["fk"])
        mark = "✓" if claim == actual else "✗"
        print(f"   {mark} {claim[0]} bảng · {claim[1]} quan hệ")
        if claim != actual:
            problems.append(
                f"ERD HTML tiêu đề nêu {claim[0]} bảng · {claim[1]} quan hệ, "
                f"thực tế {actual[0]} · {actual[1]}"
            )

    # ── 2b. Họ kiểu dữ liệu của từng cột trên sơ đồ ──
    print("\n2b. Họ kiểu dữ liệu trên sơ đồ")
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
                f"ERD HTML: `{table}.{column}` ghi {declared}, CSDL là {actual}"
            )
            print(f"   ✗ {table}.{column}  ERD={declared}  CSDL={actual}")
    if not mismatched:
        print(f"   ✓ {len(erd_types)} cột, họ kiểu khớp hết")

    # ── 2d. Giá trị ENUM trong DATABASE_DESIGN.md ──
    #
    # Mục 2b chỉ so HỌ kiểu, nên ENUM('a','b') và ENUM('a','b','c') với nó là
    # một. Khoảng trống đó đã để tài liệu giữ `tags.tag_type` với giá trị
    # 'taste' rất lâu sau khi nhóm nhãn vị bị bỏ khỏi CSDL — không mục kiểm
    # nào kêu, vì cả hai bên đều "là ENUM".
    print("\n2d. Giá trị ENUM trong DATABASE_DESIGN.md")
    doc_enums = ddl_enums(DESIGN.read_text(encoding="utf-8"))
    checked = off = 0
    for (table, column), stated in sorted(doc_enums.items()):
        actual = db["enums"].get((table, column))
        if actual is None:
            continue
        checked += 1
        if stated != actual:
            off += 1
            extra = ", ".join(sorted(stated - actual)) or "—"
            missing = ", ".join(sorted(actual - stated)) or "—"
            print(f"   ✗ {table}.{column}  thừa: {extra}  ·  thiếu: {missing}")
            problems.append(
                f"DATABASE_DESIGN: `{table}.{column}` ENUM lệch CSDL "
                f"(thừa: {extra}, thiếu: {missing})"
            )
    if not off:
        print(f"   ✓ {checked} cột ENUM, tập giá trị khớp hết")

    # ── 2e. Giá trị ENUM hiển thị trên sơ đồ ──
    #
    # Sơ đồ in ra giá trị của từng cột ENUM để người đọc không phải mở lược
    # đồ, nên danh sách đó phải khớp CSDL **cả về thứ tự**: thứ tự của ENUM
    # là ngữ nghĩa, không phải trang trí — `severity_min` đi từ `mild` tới
    # `severe` và MySQL so sánh theo đúng thứ tự khai báo. Sắp lại rồi so
    # theo tập hợp sẽ bỏ qua một sơ đồ in sai chiều nặng nhẹ.
    print("\n2e. Giá trị ENUM hiển thị trên sơ đồ")
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

    off = 0
    for key in sorted(set(erd_enum_values) | set(db_enum_order)):
        stated = erd_enum_values.get(key)
        actual = db_enum_order.get(key)
        if stated == actual:
            continue
        off += 1
        if actual is None:
            print(f"   ✗ {key[0]}.{key[1]}: sơ đồ in giá trị nhưng CSDL không "
                  f"phải ENUM")
            problems.append(
                f"ERD HTML: `{key[0]}.{key[1]}` in giá trị ENUM nhưng cột "
                f"không phải ENUM"
            )
        elif stated is None:
            print(f"   ✗ {key[0]}.{key[1]}: thiếu danh sách giá trị")
            problems.append(
                f"ERD HTML: `{key[0]}.{key[1]}` thiếu danh sách giá trị ENUM"
            )
        else:
            print(f"   ✗ {key[0]}.{key[1]}:")
            print(f"       sơ đồ: {stated}")
            print(f"       CSDL : {actual}")
            problems.append(
                f"ERD HTML: `{key[0]}.{key[1]}` danh sách giá trị ENUM lệch "
                f"CSDL"
            )
    if not off:
        total = sum(len(v) for v in db["enum_order"].values())
        print(f"   ✓ {len(db_enum_order)} cột ENUM/SET, {total} giá trị, "
              f"khớp cả thứ tự")

    # ── 2c. Mảng cột trên sơ đồ có hỏng không ──
    #
    # Hai phần tử mảng đứng cạnh nhau mà THIẾU DẤU PHẨY vẫn là JavaScript hợp
    # lệ — nó thành phép lập chỉ mục và cho `undefined`:
    #
    #     ['vitamin_c_mg','DECIMAL(6,2)','']      ← thiếu dấu phẩy
    #     ['updated_at','DATETIME','']
    #
    # Khi đó vòng lặp vẽ thẻ ném lỗi ở đúng bảng ấy và DỪNG HẲN — sơ đồ chỉ
    # hiện các bảng trước nó và không vẽ đường quan hệ nào. `node --check` không
    # bắt được vì cú pháp vẫn đúng, và phép so tên cột cũng không bắt được vì
    # tên vẫn nằm trong văn bản.
    print("\n2c. Mảng cột trên sơ đồ")
    gaps = []
    for m in re.finditer(r"\]\s*\n\s*\[", html):
        gaps.append(html[: m.start()].count("\n") + 1)
    if gaps:
        for line in gaps:
            problems.append(
                f"ERD HTML dòng {line}: thiếu dấu phẩy giữa hai phần tử mảng "
                f"— sơ đồ sẽ ngừng vẽ từ bảng này trở đi"
            )
            print(f"   ✗ dòng {line}: thiếu dấu phẩy giữa hai phần tử mảng")
    else:
        print("   ✓ không có chỗ nào thiếu dấu phẩy giữa hai phần tử")

    # ── 3. Cột đã bỏ mà tài liệu còn liệt kê ──
    print("\n3. Cột đã bỏ khỏi lược đồ")
    live = {c for cols in db["columns"].values() for c in cols}
    for path in (DESIGN, REVIEW, ERD):
        text = path.read_text(encoding="utf-8")
        for col in DROPPED:
            if col in live:
                continue
            for m in re.finditer(rf"`{col}`|\['{col}'", text):
                lineno = text[: m.start()].count("\n") + 1
                line = text.split("\n")[lineno - 1]
                # Nhắc trong mục giải thích lịch sử thì bỏ qua
                context = "\n".join(
                    text.split("\n")[max(0, lineno - 16): lineno + 1]
                )
                if any(h in context for h in HISTORICAL):
                    continue
                problems.append(
                    f"{path.name}:{lineno} còn liệt kê `{col}` — đã bỏ khỏi lược đồ"
                )
                print(f"   ✗ {path.name}:{lineno}  {line.strip()[:60]}")
    print("   ✓ không có chỗ nào liệt kê cột đã bỏ"
          if not any("đã bỏ khỏi lược đồ" in p for p in problems) else "")

    # ── 4. Dấu tiếng Việt trong định danh ──
    print("\n4. Dấu tiếng Việt trong định danh (yêu cầu bài tập ERD)")
    distinct = set(db["tables"]) | {
        c for cols in db["columns"].values() for c in cols
    }
    bad = sorted(x for x in distinct if has_diacritics(x))
    n_positions = sum(len(v) for v in db["columns"].values())
    print(
        f"   {len(distinct)} định danh phân biệt "
        f"({n_tables} tên bảng + {len(distinct) - n_tables} tên cột), "
        f"{n_positions} vị trí cột"
    )
    if bad:
        print(f"   ✗ {len(bad)} định danh có dấu: {', '.join(bad)}")
        problems.extend(f"định danh có dấu: {x}" for x in bad)
    else:
        print("   ✓ không có định danh nào chứa dấu hay ký tự ngoài ASCII")

    # ── 4b. Câu phát biểu về số định danh trong ERD_REVIEW.md ──
    #
    # Mục 4 ở trên chỉ ĐO rồi in ra; nó không đối chiếu với con số viết trong
    # tài liệu. Khoảng trống đó đã để một câu sai nằm im: ERD_REVIEW.md ghi
    # "161 định danh phân biệt — 22 tên bảng cộng 139 tên cột phân biệt, trên
    # tổng 216 vị trí cột" trong khi CSDL đo được 160 / 138 / 213. Sai từ
    # trước, và không mục kiểm nào bắt được vì không ai so hai bên.
    #
    # Cùng một loại lỗi với "hai chỗ phát biểu quy mô mà chỉ sửa một chỗ" ở
    # mục 1 — nên chữa cùng một cách: đọc con số trong câu văn rồi so với số đo.
    print("\n4b. Con số định danh viết trong ERD_REVIEW.md")
    review = REVIEW.read_text(encoding="utf-8")
    sentence = re.search(
        r"\*\*(\d+) định danh phân biệt\*\*\s*—\s*(\d+) tên bảng cộng\s+"
        r"(\d+) tên cột phân biệt,\s+trên tổng (\d+) vị trí cột",
        review,
    )
    if not sentence:
        print("   ✗ không tìm thấy câu phát biểu — mẫu tìm kiếm đã lạc hậu?")
        problems.append(
            "ERD_REVIEW.md: không tìm thấy câu phát biểu số định danh"
        )
    else:
        stated = [int(g) for g in sentence.groups()]
        measured = [
            len(distinct), n_tables, len(distinct) - n_tables, n_positions
        ]
        labels = ("định danh phân biệt", "tên bảng", "tên cột", "vị trí cột")
        line = review[: sentence.start()].count("\n") + 1
        wrong = [
            (lab, say, got)
            for lab, say, got in zip(labels, stated, measured)
            if say != got
        ]
        for lab, say, got in wrong:
            print(f"   ✗ ERD_REVIEW.md:{line}  {lab}: ghi {say}, đo {got}")
            problems.append(
                f"ERD_REVIEW.md:{line} {lab}: ghi {say}, CSDL có {got}"
            )
        if not wrong:
            print(
                f"   ✓ ERD_REVIEW.md:{line}  "
                f"{stated[0]} định danh · {stated[1]} bảng · "
                f"{stated[2]} cột · {stated[3]} vị trí"
            )

    # ── Kết luận ──
    print("\n" + "═" * 72)
    if problems:
        print(f"{len(problems)} vấn đề:\n")
        for p in problems:
            print(f"  ✗ {p}")
    else:
        print("TẤT CẢ KHỚP — bốn nguồn mô tả cùng một lược đồ.")
    print("═" * 72)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
