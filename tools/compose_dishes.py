#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cộng dồn dinh dưỡng món ăn từ định lượng nguyên liệu.

Bảng thành phần thực phẩm Việt Nam 2007 liệt kê **nguyên liệu**, không liệt
kê món ăn: có "bánh phở", "thịt bò thăn", "hành lá", nhưng không có "phở bò".
Trong khi đó hệ thống cần dinh dưỡng của **một suất ăn thật**.

Bước này bắc cầu giữa hai thứ đó. Mỗi món được mô tả bằng một công thức —
danh sách nguyên liệu kèm khối lượng — rồi dinh dưỡng của món tính bằng tổng
có trọng số:

    giá_trị_món = Σ (giá_trị_nguyên_liệu_mỗi_100g × khối_lượng_gam / 100)

Cách này cho `data_source` một câu trả lời sạch: mọi con số truy ngược được
về đúng một mục trong bảng gốc, và công thức được ghi lại trong cột `note`
nên hội đồng kiểm chứng được từng bước.

Chạy:
    python tools/compose_dishes.py data/foods/recipes/mon_nuoc.json
    python tools/compose_dishes.py data/foods/recipes/*.json --write
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF_DIR = ROOT / "data" / "reference"
FCT_PATH = REF_DIR / "fct2007.json"
INGREDIENTS_PATH = REF_DIR / "ingredients.json"
FOODS_DIR = ROOT / "data" / "foods"

# Nhóm mã thực phẩm có nguồn gốc động vật, suy từ chữ số đầu của mã số:
# 7 = thịt, 8 = thủy sản, 9 = trứng, 10 = sữa. Thêm các loại mắm ở nhóm gia
# vị vì chúng làm từ cá và tôm — đây chính là cái bẫy: một món gắn nhãn chay
# mà nêm nước mắm trông hoàn toàn bình thường trong bảng CSV.
ANIMAL_GROUPS = ("7", "8", "9", "10")

# Nguyên liệu là dị nguyên: mã thực phẩm → nhãn bắt buộc phải có. Quên gắn
# nhãn ở đây là lỗi an toàn thật sự — người dị ứng đậu phộng được gợi ý món
# có đậu phộng, và không phép kiểm nào khác nhìn thấy vì bảng CSV chỉ có con
# số dinh dưỡng, không có danh sách nguyên liệu.
ALLERGEN_INGREDIENTS = {
    "3017": "Có đậu phộng",   # đậu phộng hạt khô
    "3024": "Có đậu phộng",   # bột đậu phộng
    "3007": "Có đậu nành",      # đậu tương hạt
    "3021": "Có đậu nành",
    "3022": "Có đậu nành",
    "3025": "Có đậu nành",      # đậu phụ
    "3026": "Có đậu nành",
    "3027": "Có đậu nành",
    "3032": "Có đậu nành",
    "13010": "Có đậu nành",     # nước tương
    "13022": "Có đậu nành",
    "9001": "Có trứng",
    "9002": "Có trứng",
    "9004": "Có trứng",
    "1022": "Có gluten",   # mì trứng lúa mì
    "1012": "Có gluten",   # bánh mì
    "1018": "Có gluten",   # bột mì
}
# Nguyên liệu giàu purin — cơ sở của nhãn `Giàu purin` cho người bệnh gút.
#
# Vì sao phải có danh sách này thay vì dùng cột `purine_mg`: bảng gốc chỉ công
# bố purin cho 82/526 nguyên liệu, và thiếu đúng ở nhóm quan trọng nhất — tôm,
# cua, mực, ốc, hến đều không có số. Hệ quả: chỉ 64/305 món tính được purin,
# tức quy tắc ngưỡng theo ngày chỉ phủ 21 % danh mục. Nhãn mới là cơ chế bảo
# vệ chính.
#
# Phân loại theo hướng dẫn dinh dưỡng cho bệnh gút:
#   · nội tạng, tiết      — purin rất cao, phải tránh
#   · hải sản vỏ cứng     — purin cao, phải tránh
#   · cá                  — purin cao, cần hạn chế mạnh
#
# Thịt đỏ (bò, lợn, dê) CỐ Ý không nằm trong danh sách: purin ở mức trung bình
# 130–170 mg, hướng dẫn nói *hạn chế* chứ không *tránh*. Gắn nhãn cả thịt đỏ sẽ
# loại 154/305 món và chỉ còn 8 món đạm — người bệnh gút gần như không còn gì
# để ăn, đúng kiểu thất bại của ngưỡng natri 600 mg trước đây.
HIGH_PURINE_INGREDIENTS = {
    # Nội tạng và tiết
    "7059",
    # Hải sản vỏ cứng: tôm, cua, ốc, hến, mực, hàu
    "8033", "8034", "8037", "8040", "8041", "8048", "8049", "8051",
    # Cá
    "8003", "8010", "8011", "8019", "8022", "8023", "8024", "8026",
    "8030", "8038",
}

ANIMAL_SEASONINGS = {
    "13011", "13012", "13013", "13014", "13015", "13016", "13017", "13018",
}

SOURCE_NAME = "Bảng thành phần thực phẩm Việt Nam 2007 (cộng dồn từ nguyên liệu)"
SOURCE_URL = (
    "https://www.fao.org/fileadmin/templates/food_composition/documents/pdf/"
    "VTN_FCT_2007.pdf"
)

# Các chất cộng dồn được. Chất nào thiếu số liệu ở một nguyên liệu thì nguyên
# liệu đó đóng góp 0 — nhưng số mục thiếu được đếm lại và báo ra, vì cộng dồn
# âm thầm từ dữ liệu khuyết sẽ cho ra một con số trông có vẻ đầy đủ mà thực
# tế là ước tính thiếu.
SUMMABLE = [
    "calories_kcal", "protein_g", "carbs_g", "fat_g",
    "fiber_g", "sugar_g", "sodium_mg", "cholesterol_mg",
    "purine_mg", "calcium_mg", "iron_mg", "zinc_mg",
    # `vitamin_a_mcg` là cột **suy ra** trong bảng nguyên liệu: hoạt tính RAE
    # quy từ retinol và ba carotenoid (xem `extract_fct.py`). Cộng dồn RAE là
    # hợp lệ vì RAE đã là một đơn vị hoạt tính chung — không được cộng trực
    # tiếp retinol với beta-caroten khi chưa quy đổi.
    "vitamin_a_mcg", "vitamin_c_mg",
]

CSV_COLUMNS = [
    "name", "category", "dish_role", "spice_level",
    "serving_size_g", "calories_kcal", "protein_g", "carbs_g", "fat_g",
    "fiber_g", "sugar_g", "sodium_mg", "cholesterol_mg",
    "purine_mg", "calcium_mg", "iron_mg", "zinc_mg",
    "vitamin_a_mcg", "vitamin_c_mg",
    "tags", "note",
]


def load_ingredients() -> dict[str, dict]:
    """Ưu tiên bảng nguyên liệu đã hợp nhất, lùi về bảng gốc nếu chưa có.

    `ingredients.json` là bảng gốc đã được bổ khuyết từ USDA, kèm nguồn cho
    **từng trường**. Dùng nó thay vì `fct2007.json` để món ăn hưởng luôn phần
    đã vá, và để cột `note` ghi lại được chất nào là số vay.
    """
    if not FCT_PATH.exists():
        sys.exit(
            f"Chưa có {FCT_PATH}. Chạy trước:\n"
            f"  python tools/extract_fct.py <đường-dẫn>/VTN_FCT_2007.pdf"
        )

    # Nền là **toàn bộ** 526 mục của bảng gốc.
    data = json.loads(FCT_PATH.read_text(encoding="utf-8"))
    table = {f["code"]: {**f, "_sources": {}} for f in data}

    if not INGREDIENTS_PATH.exists():
        print("⚠ Chưa có ingredients.json — dùng bảng gốc chưa bổ khuyết.\n")
        return table

    # Bảng đã bổ khuyết chỉ chứa những nguyên liệu đã ánh xạ sang USDA, tức
    # là một **tập con**. Phủ nó lên trên bảng gốc chứ không thay thế: dùng
    # thay thế thì mọi nguyên liệu chưa ánh xạ sẽ biến mất khỏi công thức mà
    # chỉ để lại một dòng cảnh báo, và món vẫn ra một con số trông như thật.
    merged = json.loads(INGREDIENTS_PATH.read_text(encoding="utf-8"))
    for code, entry in merged.items():
        table[code] = {
            **table.get(code, {}),
            **entry["values"],
            "_sources": entry["sources"],
            "name_en": entry["name_en_fct"],
        }

    return table


def compose(recipe: dict, fct: dict[str, dict]) -> tuple[dict, list[str]]:
    """Trả về (dòng CSV, danh sách cảnh báo)."""
    warnings: list[str] = []
    borrowed_fields: set[str] = set()
    totals = {key: 0.0 for key in SUMMABLE}
    gaps: dict[str, list[str]] = {key: [] for key in SUMMABLE}
    weight = 0.0
    parts = []

    for item in recipe["ingredients"]:
        code = str(item["code"])
        grams = float(item["g"])
        source = fct.get(code)

        if source is None:
            warnings.append(f"không có mã {code} trong bảng gốc")
            continue

        weight += grams
        parts.append(f"{item.get('label', source['name_en'])} {grams:g}g")

        factor = grams / 100
        for key in SUMMABLE:
            value = source.get(key)
            if value is None:
                gaps[key].append(item.get("label", code))
                continue
            totals[key] += value * factor
            if source.get("_sources", {}).get(key) == "USDA":
                borrowed_fields.add(key)

    # Chất nào thiếu ở quá nửa khối lượng công thức thì để trống hẳn, thay vì
    # ghi một con số cộng thiếu trông như thật. Trống là "chưa biết"; một số
    # cộng thiếu là "biết sai".
    row = {c: "" for c in CSV_COLUMNS}
    for key in SUMMABLE:
        if len(gaps[key]) > len(recipe["ingredients"]) / 2:
            warnings.append(f"{key}: thiếu ở {len(gaps[key])} nguyên liệu → để trống")
            continue
        row[key] = f"{totals[key]:.1f}"
        if gaps[key]:
            warnings.append(
                f"{key}: cộng thiếu {', '.join(gaps[key])}"
            )

    # Nhãn chay phải khớp với công thức. Bộ kiểm tra CSV không bắt được lỗi
    # này vì nó chỉ thấy dòng kết quả, không thấy nguyên liệu; mà đây lại là
    # lỗi an toàn — người ăn chay được gợi ý món nêm mắm cá.
    tags = set(recipe.get("tags", []))
    if tags & {"Món chay", "Món thuần chay"}:
        offenders = []
        for item in recipe["ingredients"]:
            code = str(item["code"])
            group = code[:-3] if len(code) > 3 else code
            is_dairy_or_egg = group in ("9", "10")
            if code in ANIMAL_SEASONINGS or group in ANIMAL_GROUPS:
                # Trứng và sữa vẫn hợp lệ với `vegetarian`, chỉ phạm `vegan`.
                if is_dairy_or_egg and "Món thuần chay" not in tags:
                    continue
                offenders.append(item.get("label", code))
        if offenders:
            warnings.append(
                "GẮN NHÃN SAI: món chay nhưng có nguyên liệu động vật — "
                + ", ".join(offenders)
            )

    # Dị nguyên suy từ nguyên liệu phải có mặt trong nhãn.
    missing_allergens = set()
    for item in recipe["ingredients"]:
        needed = ALLERGEN_INGREDIENTS.get(str(item["code"]))
        if needed and needed not in tags:
            missing_allergens.add(f"{needed} ({item.get('label', item['code'])})")
    if missing_allergens:
        warnings.append(
            "THIẾU NHÃN DỊ NGUYÊN: " + ", ".join(sorted(missing_allergens))
        )

    # Thủy sản trong công thức cũng phải khai báo.
    if any(str(i["code"]).startswith("8") for i in recipe["ingredients"]):
        if "Có hải sản" not in tags:
            warnings.append("THIẾU NHÃN DỊ NGUYÊN: contains_seafood")

    # Nguyên liệu giàu purin phải kéo theo nhãn cho người bệnh gút.
    purine_src = [
        i.get("label", i["code"]) for i in recipe["ingredients"]
        if str(i["code"]) in HIGH_PURINE_INGREDIENTS
    ]
    if purine_src and "Giàu purin" not in tags:
        warnings.append(
            "THIẾU NHÃN GIÀU PURIN: " + ", ".join(sorted(set(purine_src)))
        )

    row.update({
        "name": recipe["name"],
        "category": recipe["category"],
        "dish_role": recipe["dish_role"],
        "spice_level": str(recipe.get("spice_level", 0)),
        "serving_size_g": f"{weight:.0f}",
        "tags": "|".join(recipe.get("tags", [])),
        # `note` đi vào `foods.description` — trường HIỂN THỊ cho người dùng,
        # nên không chứa siêu dữ liệu xuất xứ. Trước đây nó nối thêm
        # ". Vay USDA: zinc_mg", một câu chỉ có nghĩa với người làm dữ liệu.
        # Cột truy xuất nguồn đã bỏ khỏi lược đồ, nên thông tin này cũng không
        # còn chỗ chứa trong CSDL; `borrowed_fields` giờ chỉ dùng để cảnh báo
        # khi chạy công cụ.
        "note": "Công thức: " + " + ".join(parts)
                + (". " + recipe["note"] if recipe.get("note") else ""),
    })

    return row, warnings



def _in_utf8() -> None:
    """Bắt stdout nhận tiếng Việt trên Windows (mặc định cp1252).

    Không gọi thì script chết giữa lúc chạy với UnicodeEncodeError ngay khi
    đầu ra bị chuyển hướng qua ống hoặc vào tệp — tức đúng lúc chạy trong CI.
    Bản sao của `tools/_env.use_utf8`; để ở đây vì `tools/baocao/` không chắc
    có `tools/` trên `sys.path`.
    """
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover
            pass

def main() -> int:
    _in_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recipes", nargs="+", type=Path)
    parser.add_argument(
        "--write", action="store_true",
        help="ghi đè vào data/foods/<category>.csv thay vì chỉ in ra",
    )
    args = parser.parse_args()

    fct = load_ingredients()
    by_category: dict[str, list[dict]] = {}
    total_warnings = 0

    for path in args.recipes:
        recipes = json.loads(path.read_text(encoding="utf-8"))
        for recipe in recipes:
            row, warnings = compose(recipe, fct)
            by_category.setdefault(row["category"], []).append(row)

            kcal = float(row["calories_kcal"]) if row["calories_kcal"] else 0
            check = (
                4 * float(row["protein_g"] or 0)
                + 4 * float(row["carbs_g"] or 0)
                + 9 * float(row["fat_g"] or 0)
            )
            drift = abs(check - kcal) / kcal * 100 if kcal else 0

            print(f"\n{recipe['name']}  ({row['serving_size_g']} g/suất)")
            print(
                f"  {kcal:.0f} kcal · đạm {row['protein_g']} g · "
                f"bột đường {row['carbs_g']} g · béo {row['fat_g']} g"
                f"  [Atwater lệch {drift:.1f} %]"
            )
            if row["sodium_mg"]:
                print(f"  natri {row['sodium_mg']} mg")
            for w in warnings:
                print(f"  ⚠ {w}")
                total_warnings += 1

    if args.write:
        # Tên tệp CSV lấy từ tên tệp CÔNG THỨC, không lấy từ giá trị
        # `category`. Từ khi cột `code` bị bỏ, `category` mang tên tiếng Việt
        # có dấu và có khoảng trắng — dùng nó làm tên tệp sẽ sinh ra
        # "Món luộc hấp.csv" nằm cạnh "mon_luoc_hap.csv", tức hai tệp cho
        # cùng một nhóm và dữ liệu đếm hai lần.
        stem = args.recipes[0].stem if len(args.recipes) == 1 else None
        for category, rows in by_category.items():
            path = FOODS_DIR / f"{stem or category}.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
            print(f"\nĐã ghi {len(rows)} món → {path}")
    else:
        print("\n(Chạy lại với --write để ghi vào CSV)")

    print(f"\nTổng {total_warnings} cảnh báo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
