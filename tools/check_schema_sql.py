#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Đối chiếu `db/schema.sql` với CSDL thật, từng cột một.

Khoảng trống này tồn tại khá lâu mà không ai thấy. `tools/check_docs_sync.py`
so CSDL với **ba** nguồn — `database_erd.html`, `DATABASE_DESIGN.md`,
`ERD_REVIEW.md` — nhưng **không so với chính `db/schema.sql`**, dù đó là tệp
dựng lại CSDL. `tools/test_schema_build.py` thì dựng schema.sql vào CSDL nháp
và đếm tổng (22 bảng / 29 khóa ngoại / 15 CHECK / 211 cột), nên nó bắt được
lệch về **số lượng** nhưng không bắt được lệch về **nội dung**: đổi
`VARCHAR(100)` thành `VARCHAR(200)`, bỏ một `NOT NULL`, thêm một giá trị
ENUM — mọi con số vẫn đúng y nguyên.

Tệp này so bốn thứ, mỗi thứ theo cả hai chiều:

    tập cột · cho phép NULL · họ kiểu và tham số · tập giá trị ENUM/SET

Bài học về phép đo, ghi lại vì đã tự sa vào: bản thử đầu tiên tách định nghĩa
cột **theo dòng** và báo 29 lỗi NULL + 25 lỗi ENUM. Cả 54 đều là ảo.

  · `ENUM(...)` trong schema.sql trải nhiều dòng, nên tách theo dòng thì
    `dish_role` chỉ còn phần `ENUM('main','side_protein',` — không thấy
    `NOT NULL` nằm ở dòng dưới.
  · Cột khóa chính viết `PRIMARY KEY AUTO_INCREMENT` mà không ghi `NOT NULL`;
    MySQL tự thêm. Không biết luật đó thì mọi khóa chính đều thành "lệch".
  · Phép so ENUM viết hoa cả chuỗi trước khi bóc giá trị trong dấu nháy, nên
    `'mild'` thành `'MILD'` và không bao giờ khớp.

Nên ở đây định nghĩa cột được tách bằng cách **duyệt ký tự, đếm độ sâu ngoặc**,
và giá trị ENUM bóc từ chuỗi gốc chưa đổi hoa thường.

Chạy:
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

# Từ khóa mở đầu một ràng buộc ở cấp bảng, không phải một cột.
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
    """Bỏ chú thích `--` nhưng giữ nguyên nội dung trong dấu nháy.

    Không được bỏ thô bằng `split('--')`: một chuỗi mặc định hay một COMMENT
    hoàn toàn có thể chứa hai dấu gạch.
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
    """Tách thân CREATE TABLE thành từng định nghĩa, theo dấu phẩy **ngoài
    ngoặc** và ngoài dấu nháy.

    Đây là chỗ bản thử đầu tiên sai: tách theo dòng thì một `ENUM(...)` trải
    nhiều dòng bị cắt làm nhiều mảnh, và mảnh đầu không chứa `NOT NULL`.
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
    """Bóc từng cột của từng bảng ra khỏi schema.sql."""
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

            # Khóa chính ngầm định NOT NULL dù không viết ra — MySQL tự thêm.
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
                # Bóc từ chuỗi GỐC, chưa đổi hoa thường.
                inner = type_match.group(3) if type_match else ""
                info["values"] = set(re.findall(r"'([^']*)'", inner or ""))
            elif kind in ("VARCHAR", "CHAR", "BINARY"):
                arg = (type_match.group(3) or "").strip()
                info["length"] = int(arg) if arg.isdigit() else None
            elif kind in ("DECIMAL", "NUMERIC"):
                arg = (type_match.group(3) or "")
                nums = [int(x) for x in re.findall(r"\d+", arg)]
                if len(nums) == 2:
                    info["precision"], info["scale"] = nums

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
    database = _env.require("MYSQL_DATABASE")
    sql = parse_schema(SCHEMA.read_text(encoding="utf-8"))
    db = read_db(database)

    problems: list[str] = []

    print("═" * 74)
    print("ĐỐI CHIẾU db/schema.sql VỚI CSDL THẬT")
    print("═" * 74)

    # ── 1. Tập bảng ──
    print("\n1. Tập bảng")
    only_sql = sorted(set(sql) - set(db))
    only_db = sorted(set(db) - set(sql))
    for t in only_sql:
        print(f"   ✗ `{t}` có trong schema.sql, không có trong CSDL")
        problems.append(f"bảng `{t}` chỉ có trong schema.sql")
    for t in only_db:
        print(f"   ✗ `{t}` có trong CSDL, không có trong schema.sql")
        problems.append(f"bảng `{t}` chỉ có trong CSDL")
    if not only_sql and not only_db:
        print(f"   ✓ {len(db)} bảng, khớp hai chiều")

    shared = sorted(set(sql) & set(db))

    # ── 2. Tập cột ──
    print("\n2. Tập cột của từng bảng")
    missing = extra = 0
    for t in shared:
        for c in sorted(set(db[t]) - set(sql[t])):
            print(f"   ✗ {t}.{c} có trong CSDL, thiếu trong schema.sql")
            problems.append(f"`{t}.{c}` thiếu trong schema.sql")
            missing += 1
        for c in sorted(set(sql[t]) - set(db[t])):
            print(f"   ✗ {t}.{c} có trong schema.sql, không có trong CSDL")
            problems.append(f"`{t}.{c}` chỉ có trong schema.sql")
            extra += 1
    total_cols = sum(len(v) for v in db.values())
    if not missing and not extra:
        print(f"   ✓ {total_cols} cột, khớp hai chiều")

    # ── 3. Cho phép NULL ──
    print("\n3. Cho phép NULL")
    off = 0
    for t in shared:
        for c in sorted(set(sql[t]) & set(db[t])):
            a, b = sql[t][c]["nullable"], db[t][c]["nullable"]
            if a != b:
                print(
                    f"   ✗ {t}.{c}: schema.sql="
                    f"{'NULL' if a else 'NOT NULL'}, CSDL="
                    f"{'NULL' if b else 'NOT NULL'}"
                )
                problems.append(f"`{t}.{c}` lệch NULL/NOT NULL")
                off += 1
    if not off:
        print(f"   ✓ {total_cols} cột, tính cho phép NULL khớp hết")

    # ── 4. Kiểu và tham số ──
    print("\n4. Kiểu dữ liệu và tham số")
    off = 0
    checked = 0
    for t in shared:
        for c in sorted(set(sql[t]) & set(db[t])):
            s_, d_ = sql[t][c], db[t][c]
            checked += 1
            if s_["kind"] != d_["kind"]:
                print(f"   ✗ {t}.{c}: schema={s_['kind']}, CSDL={d_['kind']}")
                problems.append(f"`{t}.{c}` lệch kiểu")
                off += 1
                continue
            if "length" in s_ and s_["length"] != d_.get("length"):
                print(
                    f"   ✗ {t}.{c}: schema độ dài {s_['length']}, "
                    f"CSDL {d_.get('length')}"
                )
                problems.append(f"`{t}.{c}` lệch độ dài")
                off += 1
            if "precision" in s_ and (
                s_.get("precision") != d_.get("precision")
                or s_.get("scale") != d_.get("scale")
            ):
                print(
                    f"   ✗ {t}.{c}: schema "
                    f"({s_.get('precision')},{s_.get('scale')}), CSDL "
                    f"({d_.get('precision')},{d_.get('scale')})"
                )
                problems.append(f"`{t}.{c}` lệch độ chính xác DECIMAL")
                off += 1
    if not off:
        print(f"   ✓ {checked} cột, kiểu và tham số khớp hết")

    # ── 5. Giá trị ENUM / SET ──
    print("\n5. Tập giá trị ENUM và SET")
    off = 0
    checked = 0
    for t in shared:
        for c in sorted(set(sql[t]) & set(db[t])):
            s_, d_ = sql[t][c], db[t][c]
            if "values" not in s_ or "values" not in d_:
                continue
            checked += 1
            if s_["values"] != d_["values"]:
                extra_v = ", ".join(sorted(s_["values"] - d_["values"])) or "—"
                miss_v = ", ".join(sorted(d_["values"] - s_["values"])) or "—"
                print(f"   ✗ {t}.{c}: schema thừa {extra_v} · thiếu {miss_v}")
                problems.append(f"`{t}.{c}` lệch tập giá trị ENUM")
                off += 1
    if not off:
        print(f"   ✓ {checked} cột ENUM/SET, tập giá trị khớp hết")

    print("\n" + "═" * 74)
    if problems:
        print(f"{len(problems)} vấn đề:\n")
        for item in problems:
            print(f"  ✗ {item}")
    else:
        print("db/schema.sql MÔ TẢ ĐÚNG CSDL — từng cột, cả hai chiều.")
    print("═" * 74)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
