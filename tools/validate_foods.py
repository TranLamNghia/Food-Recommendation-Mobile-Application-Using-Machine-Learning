#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm tra tập dữ liệu món ăn trong data/foods/*.csv.

Tập dữ liệu này được nhiều người và nhiều tác nhân nhập từ nhiều nguồn khác
nhau, nên sai sót là chuyện chắc chắn xảy ra chứ không phải rủi ro. Bộ kiểm
tra chạy trước mỗi lần nạp vào MySQL, và nên chạy cả trong móc tiền-commit.

Phép kiểm quan trọng nhất là **đối chiếu Atwater**: năng lượng công bố phải
xấp xỉ 4·đạm + 4·bột đường + 9·béo. Phép này bắt được gần như mọi lỗi chép
số — nhầm cột, lệch dấu thập phân, lẫn đơn vị — mà không cần biết món đó
thật sự bao nhiêu calo.

Chạy:
    python tools/validate_foods.py            # kiểm tra và in báo cáo
    python tools/validate_foods.py --strict   # cảnh báo cũng tính là lỗi
"""

from __future__ import annotations

import argparse
import csv
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "foods"

# ── Vốn từ hợp lệ, phải khớp enum trong db/schema.sql ────────────────────

CATEGORIES = {
    "Món nước", "Cơm", "Món kho",
    "Món xào", "Món canh", "Món chiên rán",
    "Món nướng", "Món luộc hấp", "Món cuốn",
    "Món gỏi / nộm", "Tráng miệng", "Đồ uống",
}

# Tên tệp CSV → tên danh mục trong CSDL.
#
# Tệp vẫn đặt tên không dấu cho dễ gõ và dễ dùng trong dòng lệnh, còn cột
# `category` trong tệp mang **tên tiếng Việt** — đúng giá trị mà
# `food_categories.name` lưu, vì cột `code` đã được bỏ khỏi lược đồ.
FILE_TO_CATEGORY = {
    "mon_nuoc": "Món nước",
    "com": "Cơm",
    "mon_kho": "Món kho",
    "mon_xao": "Món xào",
    "mon_canh": "Món canh",
    "mon_chien": "Món chiên rán",
    "mon_nuong": "Món nướng",
    "mon_luoc_hap": "Món luộc hấp",
    "mon_cuon": "Món cuốn",
    "mon_goi": "Món gỏi / nộm",
    "trang_mieng": "Tráng miệng",
    "do_uong": "Đồ uống",
}

# Vai trò món. Rộng hơn enum `foods.dish_role` hiện tại (main/side/soup/
# dessert/drink) vì thuật toán sinh thực đơn cần tách `side_protein` khỏi
# `side_veg` — mâm cơm Việt thiếu món mặn thì không còn là bữa ăn, mà enum
# hiện tại gộp cả hai vào `side` nên không diễn đạt được ràng buộc đó.
DISH_ROLES = {
    "main",          # món chính — cơm, phở, bún
    "side_protein",  # món mặn — thịt, cá, trứng, đậu phụ
    "side_veg",      # món rau — luộc, xào, nộm
    "soup",          # món canh
    "snack",         # món phụ, ăn vặt
    "dessert",       # tráng miệng
    "drink",         # đồ uống
}



TAGS = {
    "Có hải sản", "Có đậu phộng", "Có trứng",
    "Có sữa / chế phẩm sữa", "Có gluten", "Có đậu nành",
    "Món chay", "Món thuần chay", "Ít natri",
    "Ít đường", "Giàu đạm", "Giàu chất xơ",
    "Giàu purin",
    }

# ── Cột: bắt buộc, nên có, tùy chọn ─────────────────────────────────────

REQUIRED = [
    "name", "category", "dish_role", "spice_level",
    "serving_size_g", "calories_kcal",
    "protein_g", "carbs_g", "fat_g",
]

# Bộ quy tắc F1 trong db/seed.sql tham chiếu tới các cột này. Để trống thì
# quy tắc tương ứng lặng lẽ không bao giờ kích hoạt — người tăng huyết áp
# vẫn nhận món mặn mà hệ thống tưởng là đã lọc.
RULE_COLUMNS = {
    "sodium_mg": "tăng huyết áp, bệnh thận",
    "sugar_g": "đái tháo đường",
    "cholesterol_mg": "mỡ máu",
    "purine_mg": "gút",
    "calcium_mg": "loãng xương",
    "iron_mg": "thiếu máu",
    "vitamin_c_mg": "khuyến nghị vi chất",
}

NUMERIC = {
    "spice_level": (0, 3),
    "serving_size_g": (1, 2000),
    "calories_kcal": (0, 2000),
    "protein_g": (0, 200),
    "carbs_g": (0, 300),
    "fat_g": (0, 200),
    "fiber_g": (0, 100),
    "sugar_g": (0, 200),
    "sodium_mg": (0, 10000),
    "cholesterol_mg": (0, 1000),
    "purine_mg": (0, 1000),
    "calcium_mg": (0, 3000),
    "iron_mg": (0, 100),
    "zinc_mg": (0, 100),
    "vitamin_a_mcg": (0, 5000),
    "vitamin_c_mg": (0, 1000),
}

# Sai số cho phép của phép đối chiếu Atwater. Lệch thật sự có lý do tồn tại:
# chất xơ sinh ít năng lượng hơn bột đường, rượu sinh 7 kcal/g, và số liệu
# công bố thường đã làm tròn. 12 % đủ rộng để không báo động giả, đủ chặt
# để bắt lỗi lệch một chữ số thập phân.
ATWATER_TOLERANCE = 0.12


class Issue:
    __slots__ = ("level", "file", "row", "name", "message")

    def __init__(self, level, file, row, name, message):
        self.level = level
        self.file = file
        self.row = row
        self.name = name
        self.message = message

    def __str__(self):
        where = f"{self.file}:{self.row}"
        who = f" [{self.name}]" if self.name else ""
        return f"  {where}{who}  {self.message}"


def normalize(text: str) -> str:
    """Bỏ dấu và hạ chữ thường, dùng để phát hiện món trùng tên.

    "Phở bò tái" và "pho bo tai" là cùng một món; người nhập liệu khác nhau
    rất dễ gõ khác nhau.
    """
    stripped = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in stripped if unicodedata.category(c) != "Mn").strip()


def parse_number(value: str):
    """Trả về (số, lỗi). Chuỗi rỗng trả về (None, None)."""
    raw = value.strip()
    if not raw:
        return None, None
    # Người nhập quen dấu phẩy thập phân kiểu Việt Nam.
    raw = raw.replace(",", ".")
    try:
        return float(raw), None
    except ValueError:
        return None, f"không phải số: {value!r}"


def check_row(issues, filename, lineno, row, expected_category):
    name = row.get("name", "").strip()

    for column in REQUIRED:
        if not row.get(column, "").strip():
            issues.append(
                Issue("LỖI", filename, lineno, name, f"thiếu cột bắt buộc `{column}`")
            )

    if not name:
        return None

    # ── Vốn từ ──
    category = row.get("category", "").strip()
    if category and category not in CATEGORIES:
        issues.append(Issue("LỖI", filename, lineno, name, f"`category` lạ: {category!r}"))
    elif category and category != FILE_TO_CATEGORY.get(
        expected_category, expected_category
    ):
        issues.append(
            Issue(
                "LỖI", filename, lineno, name,
                f"`category` là {category!r} nhưng nằm trong tệp {expected_category}.csv",
            )
        )

    role = row.get("dish_role", "").strip()
    if role and role not in DISH_ROLES:
        issues.append(Issue("LỖI", filename, lineno, name, f"`dish_role` lạ: {role!r}"))

    for tag in [t.strip() for t in row.get("tags", "").split("|") if t.strip()]:
        if tag not in TAGS:
            issues.append(Issue("LỖI", filename, lineno, name, f"nhãn lạ: {tag!r}"))

    # ── Số ──
    values = {}
    for column, (low, high) in NUMERIC.items():
        number, error = parse_number(row.get(column, ""))
        if error:
            issues.append(Issue("LỖI", filename, lineno, name, f"`{column}` {error}"))
            continue
        if number is None:
            continue
        if not (low <= number <= high):
            issues.append(
                Issue(
                    "LỖI", filename, lineno, name,
                    f"`{column}` = {number:g} nằm ngoài khoảng hợp lý [{low}, {high}]",
                )
            )
        values[column] = number

    # ── Đối chiếu Atwater ──
    kcal = values.get("calories_kcal")
    protein = values.get("protein_g")
    carbs = values.get("carbs_g")
    fat = values.get("fat_g")

    if None not in (kcal, protein, carbs, fat):
        computed = 4 * protein + 4 * carbs + 9 * fat
        if kcal > 0:
            drift = abs(computed - kcal) / kcal
            if drift > ATWATER_TOLERANCE:
                issues.append(
                    Issue(
                        "LỖI", filename, lineno, name,
                        f"năng lượng không khớp ba chất: công bố {kcal:g} kcal, "
                        f"tính ra {computed:.0f} kcal (lệch {drift * 100:.0f} %)",
                    )
                )
        elif computed > 20:
            issues.append(
                Issue(
                    "LỖI", filename, lineno, name,
                    f"`calories_kcal` = 0 nhưng ba chất cộng lại {computed:.0f} kcal",
                )
            )

    # Đường và xơ đều là một phần của bột đường nên về lý không được vượt.
    #
    # Nhưng trong Bảng thành phần thực phẩm Việt Nam 2007, **29 trong 211 mục**
    # có đường lớn hơn bột đường — ví dụ dưa hấu ghi bột đường 2,3 g mà đường
    # 6,2 g. Đây là mâu thuẫn của CHÍNH BẢNG GỐC, không phải lỗi chép số: cột
    # "Glucid" thường tính bằng hiệu số, còn "Đường tổng số" đo trực tiếp, và
    # hai phương pháp lệch nhau ở quả nhiều nước.
    #
    # Vì vậy đây là CẢNH BÁO chứ không phải LỖI. Báo lỗi cho một thứ không sửa
    # được sẽ khiến người đọc quen bỏ qua kết quả kiểm — lúc đó lỗi thật cũng
    # trôi theo. Mã dùng tỷ lệ đường đã chặn trên ở 1,0 nên vẫn an toàn.
    for part in ("sugar_g", "fiber_g"):
        if part in values and carbs is not None and values[part] > carbs + 0.01:
            issues.append(
                Issue(
                    "CẢNH BÁO", filename, lineno, name,
                    f"`{part}` = {values[part]:g} lớn hơn `carbs_g` = {carbs:g}"
                    f" — mâu thuẫn có sẵn trong bảng gốc, giữ nguyên số nguồn",
                )
            )

    # ── Nhất quán nhãn với số liệu ──
    # Ba phép kiểm dưới đây từng tra nhãn bằng tên tiếng Anh — `vegan`,
    # `vegetarian`, `contains_seafood`, `low_sodium` — trong khi từ vựng nhãn
    # đã chuyển sang tên tiếng Việt từ lúc bỏ cột `code`. Không nhãn nào khớp
    # nữa, nên **cả ba đều không bao giờ chạy**, kể cả phép kiểm mức LỖI
    # "vừa là món chay vừa có hải sản".
    #
    # Đáng chú ý vì đúng loại lỗi này đã để hai món gắn nhãn `Món chay` mà
    # trong công thức có nước mắm đi qua được: phép kiểm vẫn nằm trong mã
    # nguồn, trông như đang bảo vệ, mà thực ra là một câu `if` chết.
    tags = {t.strip() for t in row.get("tags", "").split("|") if t.strip()}
    if "Món thuần chay" in tags and "Món chay" not in tags:
        issues.append(
            Issue("CẢNH BÁO", filename, lineno, name,
                  "có nhãn `Món thuần chay` nhưng thiếu `Món chay`")
        )
    if "Món chay" in tags and tags & {"Có hải sản"}:
        issues.append(
            Issue("LỖI", filename, lineno, name, "vừa là món chay vừa có hải sản")
        )
    if "Ít natri" in tags and values.get("sodium_mg", 0) > 400:
        issues.append(
            Issue(
                "CẢNH BÁO", filename, lineno, name,
                f"gắn `Ít natri` nhưng natri {values['sodium_mg']:g} mg",
            )
        )

    # ── Truy xuất nguồn ──

    return {"name": name, "values": values, "role": role}


def main() -> int:
    _env.use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict", action="store_true", help="coi cảnh báo là lỗi"
    )
    args = parser.parse_args()

    files = sorted(DATA_DIR.glob("*.csv"))
    if not files:
        print(f"Không tìm thấy tệp CSV nào trong {DATA_DIR}")
        return 1

    issues: list[Issue] = []
    rows = []
    seen: dict[str, tuple[str, int]] = {}
    per_file = Counter()
    per_role = Counter()
    coverage = defaultdict(int)

    for path in files:
        expected = path.stem
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for lineno, row in enumerate(csv.DictReader(handle), start=2):
                if not any(v.strip() for v in row.values()):
                    continue

                parsed = check_row(issues, path.name, lineno, row, expected)
                per_file[expected] += 1
                if parsed is None:
                    continue

                rows.append(parsed)
                per_role[parsed["role"]] += 1
                for column in RULE_COLUMNS:
                    if row.get(column, "").strip():
                        coverage[column] += 1

                key = normalize(parsed["name"])
                if key in seen:
                    first_file, first_line = seen[key]
                    issues.append(
                        Issue(
                            "LỖI", path.name, lineno, parsed["name"],
                            f"trùng tên với {first_file}:{first_line}",
                        )
                    )
                else:
                    seen[key] = (path.name, lineno)

    total = len(rows)
    errors = [i for i in issues if i.level == "LỖI"]
    warnings = [i for i in issues if i.level == "CẢNH BÁO"]

    print("═" * 72)
    print(f"TẬP DỮ LIỆU MÓN ĂN — {total} món trong {len(files)} tệp")
    print("═" * 72)

    print("\nSố món theo nhóm:")
    for code in sorted(per_file):
        bar = "█" * min(per_file[code], 40)
        print(f"  {code:<14} {per_file[code]:>4}  {bar}")

    if per_role:
        print("\nSố món theo vai trò trong bữa:")
        for role in sorted(per_role):
            print(f"  {role:<14} {per_role[role]:>4}")
        missing_roles = DISH_ROLES - set(per_role)
        if missing_roles:
            print(f"  → chưa có món nào cho: {', '.join(sorted(missing_roles))}")

    if total:
        print("\nĐộ phủ các cột mà bộ quy tắc F1 cần:")
        for column, purpose in RULE_COLUMNS.items():
            filled = coverage[column]
            pct = filled / total * 100
            flag = "" if pct >= 80 else "  ← quy tắc chưa dùng được"
            print(f"  {column:<16} {filled:>4}/{total}  {pct:>5.1f} %{flag}   ({purpose})")

    if errors:
        print(f"\n── {len(errors)} LỖI ──")
        for issue in errors:
            print(issue)

    if warnings:
        print(f"\n── {len(warnings)} CẢNH BÁO ──")
        for issue in warnings:
            print(issue)

    print()
    if not errors and not warnings:
        print("Không có vấn đề nào.")
    else:
        print(f"Tổng: {len(errors)} lỗi, {len(warnings)} cảnh báo.")

    if total < 300:
        print(f"Còn thiếu {300 - total} món để đạt mức tối thiểu 300 theo đề cương.")

    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
