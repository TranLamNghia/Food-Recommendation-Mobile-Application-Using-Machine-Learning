#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nạp tập dữ liệu món ăn từ CSV vào MySQL.

Một dòng CSV không nạp thẳng vào một bảng mà tách ra ba nơi:

    foods           ← định danh, phân loại, vai trò trong bữa
    food_nutrition  ← 15 cột dinh dưỡng, quan hệ một-một với foods
    food_tags       ← mỗi nhãn một dòng, nối qua bảng tags

Vì vậy `LOAD DATA INFILE` không dùng được: cần tra `category_id` và `tag_id`
qua mã, và cần chèn theo đúng thứ tự phụ thuộc trong một giao dịch.

Hai chế độ:

    python tools/load_foods.py               → sinh db/seed_foods.sql để xem trước
    python tools/load_foods.py --apply       → kết nối và chèn thật

Chế độ sinh SQL là mặc định có chủ đích. Lần nạp đầu tiên nên đọc bằng mắt
trước khi chạy, và tệp SQL cũng chạy được trên máy khác không có Python.

Yêu cầu trước khi chạy:
    db/migrations/001_dataset_readiness.sql
    db/migrations/002_food_name_unique.sql
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FOODS_DIR = ROOT / "data" / "foods"
SCHEMA = ROOT / "db" / "schema.sql"
MIGRATION_001 = ROOT / "db" / "migrations" / "001_dataset_readiness.sql"
OUT_SQL = ROOT / "db" / "seed_foods.sql"


def required_nutrition_columns() -> set[str]:
    """Cột NOT NULL của `food_nutrition`, đã trừ phần migration 001 nới ra.

    Đọc từ schema thay vì liệt kê cứng: lược đồ còn đổi, mà một danh sách
    chép tay sẽ lệch đi lúc nào không biết, và hậu quả là trình nạp để lọt
    dòng thiếu dữ liệu rồi cả giao dịch đổ ở giữa chừng.
    """
    body = re.search(
        r"CREATE TABLE food_nutrition\s*\((.*?)\n\) ENGINE",
        SCHEMA.read_text(encoding="utf-8"),
        re.S,
    )
    if not body:
        return set()

    required = set()
    for line in body.group(1).split("\n"):
        line = line.split("--")[0].strip().rstrip(",")
        if not line or line.upper().startswith(
            ("PRIMARY", "FOREIGN", "UNIQUE", "INDEX", "KEY", "CONSTRAINT")
        ):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2 and "NOT NULL" in parts[1].upper():
            required.add(parts[0])

    # Migration 001 chuyển bốn cột này sang NULL được.
    if MIGRATION_001.exists():
        text = MIGRATION_001.read_text(encoding="utf-8")
        for column in re.findall(r"MODIFY (\w+)\s+DECIMAL\([\d, ]+\) NULL", text):
            required.discard(column)

    return required - {"food_id", "updated_at"}

FOOD_COLUMNS = [
    "name", "description",
    "spice_level", "dish_role",
]

# Món nạp từ CSV luôn thuộc DANH MỤC CHUNG nên `owner_id` để NULL.
#
# Phải nêu tường minh trong câu INSERT: `uq_food_name` là khóa trên cặp
# (owner_id, name); bỏ sót cột này thì ON DUPLICATE KEY UPDATE không khớp
# được dòng cũ và nạp lại lần hai sẽ nhân đôi toàn bộ món.
#
# Mọi truy vấn con tra `food_id` cũng phải kèm `owner_id IS NULL`, nếu không
# sẽ có ngày vớ phải món riêng của một người dùng trùng tên với món chung.
PUBLIC_CATALOG = "NULL"

NUTRITION_COLUMNS = [
    "serving_size_g", "calories_kcal", "protein_g", "carbs_g", "fat_g",
    "fiber_g", "sugar_g", "sodium_mg", "cholesterol_mg", "purine_mg",
    "calcium_mg", "iron_mg", "zinc_mg", "vitamin_a_mcg", "vitamin_c_mg",
]

# Cột CSV → cột bảng, khi tên không trùng nhau.
RENAME = {"note": "description"}

TEXT_COLUMNS = {
    "name", "description", "dish_role",
}


def quote(value: str) -> str:
    """Chuỗi cho MySQL. Thoát dấu nháy và dấu chéo ngược."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def sql_value(column: str, raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return "NULL"
    if column in TEXT_COLUMNS:
        return quote(raw)
    return raw


def read_rows() -> list[dict]:
    rows = []
    for path in sorted(FOODS_DIR.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for lineno, row in enumerate(csv.DictReader(handle), start=2):
                if not any(v.strip() for v in row.values()):
                    continue
                if not row.get("name", "").strip():
                    continue
                row["_origin"] = f"{path.name}:{lineno}"
                rows.append(row)
    return rows


def statements_for(row: dict) -> list[str]:
    """Sinh các câu lệnh cho một món."""
    name = row["name"].strip()
    out = []

    # ── foods ──
    # `category_id` tra bằng truy vấn con thay vì nhúng số cứng: id do
    # AUTO_INCREMENT sinh ra nên khác nhau giữa các lần dựng lại CSDL, còn mã
    # danh mục thì cố định.
    values = []
    for column in FOOD_COLUMNS:
        csv_col = next((k for k, v in RENAME.items() if v == column), column)
        values.append(sql_value(column, row.get(csv_col, "")))

    out.append(
        "INSERT INTO foods (category_id, owner_id, {cols})\n"
        "VALUES ((SELECT id FROM food_categories WHERE name = {cat}), "
        "{owner}, {vals})\n"
        "ON DUPLICATE KEY UPDATE\n"
        "    category_id = VALUES(category_id),\n"
        "    {updates};".format(
            cols=", ".join(FOOD_COLUMNS),
            cat=quote(row["category"].strip()),
            owner=PUBLIC_CATALOG,
            vals=", ".join(values),
            updates=",\n    ".join(
                f"{c} = VALUES({c})" for c in FOOD_COLUMNS if c != "name"
            ),
        )
    )

    # ── food_nutrition ──
    # `food_id` có UNIQUE nên ON DUPLICATE KEY UPDATE cập nhật đúng dòng cũ.
    nut_values = [sql_value(c, row.get(c, "")) for c in NUTRITION_COLUMNS]
    out.append(
        "INSERT INTO food_nutrition (food_id, {cols})\n"
        "VALUES ((SELECT id FROM foods WHERE name = {name} "
        "AND owner_id IS NULL), {vals})\n"
        "ON DUPLICATE KEY UPDATE\n"
        "    {updates};".format(
            cols=", ".join(NUTRITION_COLUMNS),
            name=quote(name),
            vals=", ".join(nut_values),
            updates=",\n    ".join(f"{c} = VALUES({c})" for c in NUTRITION_COLUMNS),
        )
    )

    # ── food_tags ──
    # Xóa hết rồi chèn lại: nhãn của một món là một tập hợp, và bỏ bớt nhãn
    # cũng là một thay đổi hợp lệ. Chỉ chèn thêm thì nhãn gỡ ra vẫn còn lại —
    # với nhãn dị nguyên thì đó là lỗi an toàn.
    tags = [t.strip() for t in row.get("tags", "").split("|") if t.strip()]
    out.append(
        "DELETE FROM food_tags "
        f"WHERE food_id = (SELECT id FROM foods WHERE name = {quote(name)} "
        "AND owner_id IS NULL);"
    )
    for tag in tags:
        out.append(
            "INSERT INTO food_tags (food_id, tag_id) VALUES ("
            f"(SELECT id FROM foods WHERE name = {quote(name)} "
            "AND owner_id IS NULL), "
            f"(SELECT id FROM tags WHERE name_vi = {quote(tag)}));"
        )

    return out


def build_script(rows: list[dict]) -> str:
    lines = [
        "-- Sinh tự động bởi tools/load_foods.py — ĐỪNG SỬA TAY.",
        "-- Nguồn: data/foods/*.csv",
        "--",
        "-- Cần chạy trước:",
        "--   db/migrations/001_dataset_readiness.sql",
        "--   db/migrations/002_food_name_unique.sql",
        "",
        "SET NAMES utf8mb4;",
        "START TRANSACTION;",
        "",
    ]
    for row in rows:
        lines.append(f"-- {row['_origin']}  {row['name']}")
        lines.extend(statements_for(row))
        lines.append("")
    lines.append("COMMIT;")
    return "\n".join(lines)


def apply(rows: list[dict]) -> int:
    try:
        import pymysql
    except ImportError:
        sys.exit("Cần cài pymysql:  pip install pymysql")

    config = {
        "host": _env.get("MYSQL_HOST", "localhost"),
        "port": int(_env.get("MYSQL_PORT", "3306")),
        "user": _env.require("MYSQL_USER"),
        "password": _env.require("MYSQL_PASSWORD"),
        "database": _env.require("MYSQL_DATABASE"),
        "charset": "utf8mb4",
    }

    print(f"Kết nối {config['user']}@{config['host']}:{config['port']}"
          f"/{config['database']}")

    connection = pymysql.connect(**config, autocommit=False)
    done = 0
    try:
        with connection.cursor() as cursor:
            for row in rows:
                for statement in statements_for(row):
                    cursor.execute(statement)
                done += 1
        connection.commit()
        print(f"Đã nạp {done} món.")
    except Exception as exc:
        connection.rollback()
        # Cả lô bị hoàn tác: nạp một nửa còn tệ hơn không nạp gì, vì thực đơn
        # sinh ra từ tập món khuyết trông vẫn bình thường.
        sys.exit(f"LỖI ở món thứ {done + 1} — đã hoàn tác toàn bộ.\n{exc}")
    finally:
        connection.close()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="kết nối MySQL và chèn thật, thay vì chỉ sinh tệp SQL",
    )
    args = parser.parse_args()

    rows = read_rows()
    if not rows:
        sys.exit("Không có dòng nào trong data/foods/*.csv")

    # Bỏ qua dòng chưa đủ cột bắt buộc. Chèn NULL vào cột NOT NULL sẽ làm cả
    # giao dịch đổ, kéo theo những món hợp lệ cũng không vào được — nên lọc ở
    # đây, và nói rõ đã bỏ những gì thay vì im lặng.
    required = required_nutrition_columns()
    skipped = []
    keep = []
    for row in rows:
        missing = [c for c in sorted(required) if not row.get(c, "").strip()]
        if missing:
            skipped.append((row["_origin"], row["name"], missing))
        else:
            keep.append(row)

    if skipped:
        print(f"Bỏ qua {len(skipped)} món chưa đủ cột bắt buộc "
              f"({', '.join(sorted(required))}):")
        by_file: dict[str, int] = {}
        for origin, _, _ in skipped:
            f = origin.split(":")[0]
            by_file[f] = by_file.get(f, 0) + 1
        for f in sorted(by_file):
            print(f"  {f:<18} {by_file[f]:>3}")
        print()

    rows = keep
    if not rows:
        sys.exit("Không còn dòng nào hợp lệ để nạp.")

    by_category: dict[str, int] = {}
    for row in rows:
        by_category[row["category"]] = by_category.get(row["category"], 0) + 1

    print(f"{len(rows)} món:")
    for code in sorted(by_category):
        print(f"  {code:<14} {by_category[code]:>3}")
    print()

    if args.apply:
        return apply(rows)

    OUT_SQL.write_text(build_script(rows), encoding="utf-8")
    size = OUT_SQL.stat().st_size / 1024
    print(f"Đã sinh {OUT_SQL}  ({size:.0f} KB)")
    print("\nXem lại rồi chạy:")
    print(f"  mysql -u <user> -p <database> < {OUT_SQL.relative_to(ROOT)}")
    print("hoặc nạp thẳng:")
    print("  python tools/load_foods.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
