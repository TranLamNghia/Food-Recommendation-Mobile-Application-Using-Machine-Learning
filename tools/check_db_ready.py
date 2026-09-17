#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Đối chiếu CSV món ăn với ràng buộc thật của db/schema.sql.

Khác với `validate_foods.py` — vốn kiểm tính hợp lý của **nội dung** (Atwater,
nhãn, khoảng giá trị). Bộ này kiểm tính hợp lệ về **cấu trúc**: cột nào đi
vào bảng nào, giá trị có nằm trong enum không, chuỗi có vượt độ dài không,
số có tràn kiểu DECIMAL không.

Một dòng CSV không nạp thẳng vào một bảng. Nó tách ra ba nơi:

    foods            ← định danh và phân loại
    food_nutrition   ← 15 cột dinh dưỡng
    food_tags        ← mỗi nhãn một dòng, nối qua bảng tags

Chạy:
    python tools/check_db_ready.py
"""

from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Cho phép trỏ sang tệp schema khác qua biến môi trường SCHEMA_FILE. Dùng để
# thử trước một bản vá lược đồ mà chưa phải chạy nó lên CSDL thật:
#
#     SCHEMA_FILE=db/schema_sau_migration.sql python tools/check_db_ready.py
SCHEMA = Path(os.environ.get("SCHEMA_FILE", ROOT / "db" / "schema.sql"))
SEED = ROOT / "db" / "seed.sql"
FOODS_DIR = ROOT / "data" / "foods"

# Cột CSV → (bảng đích, cột đích). `None` nghĩa là chưa có chỗ chứa.
COLUMN_MAP = {
    "name": ("foods", "name"),
    # CSV giữ **mã** danh mục, trình nạp tra ra `category_id` bằng JOIN với
    # `food_categories`. Đánh dấu là tra cứu để không kiểm kiểu như cột thường.
    "category": ("foods", "category_id", "lookup"),
    "dish_role": ("foods", "dish_role"),
    "cooking_method": ("foods", "cooking_method"),
    "spice_level": ("foods", "spice_level"),
    "suitable_meals": ("foods", "suitable_meals"),
    "origin": ("foods", "origin"),
    "note": ("foods", "description"),
    "serving_size_g": ("food_nutrition", "serving_size_g"),
    "calories_kcal": ("food_nutrition", "calories_kcal"),
    "protein_g": ("food_nutrition", "protein_g"),
    "carbs_g": ("food_nutrition", "carbs_g"),
    "fat_g": ("food_nutrition", "fat_g"),
    "fiber_g": ("food_nutrition", "fiber_g"),
    "sugar_g": ("food_nutrition", "sugar_g"),
    "sodium_mg": ("food_nutrition", "sodium_mg"),
    "cholesterol_mg": ("food_nutrition", "cholesterol_mg"),
    "purine_mg": ("food_nutrition", "purine_mg"),
    "calcium_mg": ("food_nutrition", "calcium_mg"),
    "iron_mg": ("food_nutrition", "iron_mg"),
    "zinc_mg": ("food_nutrition", "zinc_mg"),
    "vitamin_a_mcg": ("food_nutrition", "vitamin_a_mcg"),
    "vitamin_c_mg": ("food_nutrition", "vitamin_c_mg"),
    "data_source": ("food_nutrition", "data_source"),
    "tags": ("food_tags", "tag_id", "lookup"),
    "source_url": ("food_nutrition", "source_url"),
}


def read_schema(text: str) -> dict[str, dict]:
    """Bóc định nghĩa cột của từng bảng ra khỏi tệp schema."""
    tables: dict[str, dict] = {}
    for m in re.finditer(
        r"CREATE TABLE (\w+)\s*\((.*?)\n\) ENGINE", text, re.S
    ):
        name, body = m.group(1), m.group(2)
        columns: dict[str, dict] = {}
        for line in body.split("\n"):
            line = line.split("--")[0].strip().rstrip(",")
            if not line or line.upper().startswith(
                ("PRIMARY", "FOREIGN", "UNIQUE", "INDEX", "KEY", "CONSTRAINT")
            ):
                continue
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            col, rest = parts[0], parts[1]
            info: dict = {"raw": rest, "nullable": "NOT NULL" not in rest.upper()}

            enum = re.match(r"(ENUM|SET)\s*\((.*?)\)", rest, re.S | re.I)
            if enum:
                info["kind"] = enum.group(1).upper()
                info["values"] = set(re.findall(r"'([^']*)'", enum.group(2)))

            varchar = re.match(r"VARCHAR\((\d+)\)", rest, re.I)
            if varchar:
                info["kind"] = "VARCHAR"
                info["max_len"] = int(varchar.group(1))

            dec = re.match(r"DECIMAL\((\d+),\s*(\d+)\)", rest, re.I)
            if dec:
                info["kind"] = "DECIMAL"
                info["precision"] = int(dec.group(1))
                info["scale"] = int(dec.group(2))

            if re.match(r"(SMALLINT|TINYINT|INT|BIGINT)", rest, re.I):
                info.setdefault("kind", "INT")
                info["unsigned"] = "UNSIGNED" in rest.upper()

            columns[col] = info
        tables[name] = columns
    return tables


def main() -> int:
    schema = read_schema(SCHEMA.read_text(encoding="utf-8"))
    seed = SEED.read_text(encoding="utf-8")

    categories = set(
        re.findall(r"^\('(\w+)',\s*'[^']*',\s*'[^']*'\),?$", seed, re.M)
    )
    tags = set(re.findall(r"^\('(\w+)',\s*'[^']*',\s*'\w+',", seed, re.M))

    blockers: list[str] = []
    errors: list[str] = []
    notes: list[str] = []

    print("═" * 72)
    print("KIỂM TRA SẴN SÀNG NẠP CSDL")
    print("═" * 72)

    # ── 1. Cột CSV có chỗ chứa không ──
    print("\n1. Ánh xạ cột CSV → bảng")
    homeless = [c for c, spec in COLUMN_MAP.items() if spec[0] is None]
    for col, spec in COLUMN_MAP.items():
        table, target = spec[0], spec[1]
        if table is None:
            continue
        if table not in schema:
            blockers.append(f"bảng `{table}` không có trong schema")
        elif target not in schema[table] and table != "food_tags":
            blockers.append(f"`{table}.{target}` không tồn tại (cột CSV `{col}`)")
    if homeless:
        notes.append(
            f"{len(homeless)} cột CSV chưa có chỗ chứa: {', '.join(homeless)}"
        )
    print(f"   {len(COLUMN_MAP) - len(homeless)}/{len(COLUMN_MAP)} cột có đích đến")

    # ── 2. Đọc dữ liệu ──
    rows = []
    for path in sorted(FOODS_DIR.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for lineno, row in enumerate(csv.DictReader(handle), start=2):
                if any(v.strip() for v in row.values()):
                    rows.append((path.name, lineno, row))

    print(f"\n2. Dữ liệu: {len(rows)} dòng")

    # ── 3. Enum và khóa ngoại ──
    print("\n3. Enum, SET và khóa ngoại")
    foods = schema.get("foods", {})

    def check_enum(row, where, csv_col, schema_col, multi=False):
        raw = row.get(csv_col, "").strip()
        if not raw:
            return
        info = foods.get(schema_col, {})
        allowed = info.get("values")
        if not allowed:
            return
        values = raw.split("|") if multi else [raw]
        for v in values:
            if v not in allowed:
                errors.append(
                    f"{where}: `{schema_col}` = {v!r} không có trong "
                    f"ENUM({', '.join(sorted(allowed))})"
                )

    bad_roles = set()
    for fname, lineno, row in rows:
        where = f"{fname}:{lineno}"
        check_enum(row, where, "cooking_method", "cooking_method")
        check_enum(row, where, "suitable_meals", "suitable_meals", multi=True)

        role = row.get("dish_role", "").strip()
        allowed_roles = foods.get("dish_role", {}).get("values", set())
        if role and allowed_roles and role not in allowed_roles:
            bad_roles.add(role)

        cat = row.get("category", "").strip()
        if cat and categories and cat not in categories:
            errors.append(f"{where}: `category` = {cat!r} không có trong food_categories")

        for tag in [t.strip() for t in row.get("tags", "").split("|") if t.strip()]:
            if tags and tag not in tags:
                errors.append(f"{where}: nhãn {tag!r} không có trong bảng tags")

    if bad_roles:
        allowed = foods.get("dish_role", {}).get("values", set())
        blockers.append(
            f"`foods.dish_role` hiện là ENUM({', '.join(sorted(allowed))}) "
            f"nhưng CSV dùng thêm: {', '.join(sorted(bad_roles))}"
        )

    print(f"   {len(errors)} lỗi enum/khóa ngoại")

    # ── 4. Độ dài chuỗi và tràn số ──
    print("\n4. Độ dài chuỗi và kiểu số")
    overflow = 0
    for fname, lineno, row in rows:
        where = f"{fname}:{lineno}"
        for csv_col, spec in COLUMN_MAP.items():
            table, target = spec[0], spec[1]
            # Cột tra cứu đã được kiểm ở mục 3, không kiểm kiểu ở đây.
            if table is None or len(spec) > 2:
                continue
            info = schema.get(table, {}).get(target, {})
            raw = row.get(csv_col, "").strip()
            if not raw:
                if not info.get("nullable", True) and csv_col != "note":
                    errors.append(f"{where}: `{table}.{target}` NOT NULL nhưng trống")
                continue

            if info.get("kind") == "VARCHAR" and len(raw) > info["max_len"]:
                errors.append(
                    f"{where}: `{target}` dài {len(raw)} ký tự, "
                    f"vượt VARCHAR({info['max_len']})"
                )
                overflow += 1

            if info.get("kind") == "DECIMAL":
                try:
                    value = float(raw)
                except ValueError:
                    errors.append(f"{where}: `{target}` = {raw!r} không phải số")
                    continue
                limit = 10 ** (info["precision"] - info["scale"])
                if abs(value) >= limit:
                    errors.append(
                        f"{where}: `{target}` = {value} tràn "
                        f"DECIMAL({info['precision']},{info['scale']})"
                    )
                    overflow += 1

            if info.get("kind") == "INT" and info.get("unsigned"):
                try:
                    if float(raw) < 0:
                        errors.append(f"{where}: `{target}` âm nhưng cột UNSIGNED")
                except ValueError:
                    errors.append(f"{where}: `{target}` = {raw!r} không phải số")

    print(f"   {overflow} trường hợp vượt kích thước")

    # ── 5. Kết luận ──
    print("\n" + "═" * 72)
    if blockers:
        print(f"CHẶN NẠP — {len(blockers)} vấn đề cấu trúc:\n")
        for b in blockers:
            print(f"  ✗ {b}")
    if errors:
        # Gom theo tệp: tập dữ liệu đang được xây từng nhóm một, nên biết
        # nhóm nào đã sạch quan trọng hơn là đọc 129 dòng lỗi giống nhau.
        by_file: dict[str, list[str]] = {}
        for e in errors:
            by_file.setdefault(e.split(":")[0], []).append(e)

        print(f"\n{len(errors)} lỗi dữ liệu, theo tệp:\n")
        for fname in sorted(by_file):
            print(f"  {fname:<20} {len(by_file[fname]):>4} lỗi")

        clean = sorted({f for f, _, _ in rows} - set(by_file))
        if clean:
            print(f"\n  Tệp sạch: {', '.join(clean)}")

        print("\n  Ví dụ:")
        for e in errors[:5]:
            print(f"    · {e}")
    if notes:
        print("\nGhi chú:")
        for n in notes:
            print(f"  ! {n}")

    if not blockers and not errors:
        print("SẴN SÀNG NẠP — không có vấn đề nào.")

    print("═" * 72)
    return 1 if blockers or errors else 0


if __name__ == "__main__":
    sys.exit(main())
