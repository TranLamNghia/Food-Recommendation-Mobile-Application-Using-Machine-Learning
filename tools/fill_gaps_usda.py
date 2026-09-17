#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bổ khuyết chất ngoại vi cho nguyên liệu, lấy từ USDA FoodData Central.

Vá ở **tầng nguyên liệu**, không vá ở tầng món ăn. Mười món nước đầu tiên
dùng chung 15 nguyên liệu; chữa một nguyên liệu thì mọi món dùng nó đều được
chữa theo. Đi chữa từng món là làm lại cùng một việc hàng trăm lần và mỗi
lần lại có cơ hội sai khác đi.

Kết quả ghi ra `data/reference/ingredients.json` — bảng nguyên liệu đã hợp
nhất, trong đó **mỗi giá trị mang nguồn của riêng nó**. Ghi nguồn ở cấp mục
là ghi sai, vì một nguyên liệu có thể lấy macro từ bảng Việt Nam nhưng vay
natri từ USDA.

Chạy:
    python tools/fill_gaps_usda.py            # vá và ghi
    python tools/fill_gaps_usda.py --dry-run  # chỉ xem, không ghi
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference"
FCT_PATH = REF / "fct2007.json"
MAP_PATH = REF / "ingredient_map.json"
OUT_PATH = REF / "ingredients.json"

# Chất được phép vay. Cố ý KHÔNG có calories_kcal, protein_g, fat_g, carbs_g
# — xem SOURCING_POLICY.md mục 2. Trộn chất sinh năng lượng giữa hai bảng
# tạo ra nguyên liệu không tồn tại và phá luôn phép đối chiếu Atwater, vốn là
# phép kiểm duy nhất bắt được lỗi số liệu.
BORROWABLE = {
    "sodium_mg": ("Sodium, Na", "MG"),
    "sugar_g": ("Sugars, total including NLEA", "G"),
    "cholesterol_mg": ("Cholesterol", "MG"),
    "zinc_mg": ("Zinc, Zn", "MG"),
    "iron_mg": ("Iron, Fe", "MG"),
    "calcium_mg": ("Calcium, Ca", "MG"),
    "vitamin_c_mg": ("Vitamin C, total ascorbic acid", "MG"),
}

# Các chất giữ nguyên từ bảng Việt Nam, không bao giờ vay.
LOCKED = ["calories_kcal", "protein_g", "fat_g", "carbs_g", "fiber_g", "purine_mg"]

SRC_FCT = "FCT2007"
SRC_USDA = "USDA"


def fetch_usda(fdc_id: int, api_key: str) -> dict[str, float]:
    """Lấy các chất vay được của một mục USDA, quy về mỗi 100 g."""
    url = f"https://api.nal.usda.gov/fdc/v1/food/{fdc_id}?api_key={api_key}"
    with urllib.request.urlopen(url, timeout=45) as response:
        data = json.load(response)

    wanted = {v: k for k, v in BORROWABLE.items()}
    values: dict[str, float] = {}

    for item in data.get("foodNutrients", []):
        nutrient = item.get("nutrient", {})
        key = (nutrient.get("name"), nutrient.get("unitName", "").upper())
        amount = item.get("amount")
        if key in wanted and amount is not None:
            values[wanted[key]] = float(amount)

    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = _env.require(
        "USDA_API_KEY",
        hint="Đăng ký miễn phí tại https://api.data.gov/signup/",
    )

    fct = {f["code"]: f for f in json.loads(FCT_PATH.read_text(encoding="utf-8"))}
    mapping = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    pairs = mapping["mappings"]
    no_map = {k: v for k, v in mapping["khong_anh_xa"].items() if k != "_doc"}

    result: dict[str, dict] = {}
    filled_count = 0
    skipped: list[str] = []

    codes = list(pairs) + list(no_map)
    print(f"Xử lý {len(codes)} nguyên liệu.\n")

    for code in codes:
        source = fct.get(code)
        if source is None:
            print(f"  ⚠ mã {code} không có trong bảng gốc, bỏ qua")
            continue

        entry = {
            "code": code,
            "name_vi": pairs.get(code, {}).get("vi") or no_map.get(code, ""),
            "name_en_fct": source["name_en"],
            "values": {},
            "sources": {},
        }

        for key in LOCKED + list(BORROWABLE):
            value = source.get(key)
            if value is not None:
                entry["values"][key] = value
                entry["sources"][key] = SRC_FCT

        pair = pairs.get(code)
        if pair is None:
            result[code] = entry
            continue

        gaps = [k for k in BORROWABLE if k not in entry["values"]]
        if not gaps:
            result[code] = entry
            continue

        try:
            usda = fetch_usda(pair["fdc_id"], api_key)
        except urllib.error.HTTPError as exc:
            print(f"  ⚠ {entry['name_vi']}: gọi USDA lỗi {exc.code}")
            skipped.append(entry["name_vi"])
            result[code] = entry
            continue

        borrowed = []
        for key in gaps:
            if key in usda:
                entry["values"][key] = usda[key]
                entry["sources"][key] = SRC_USDA
                borrowed.append(key)
                filled_count += 1

        entry["usda_ref"] = {
            "fdc_id": pair["fdc_id"],
            "description": pair["usda"],
            "confidence": pair["confidence"],
        }

        flag = {"cao": " ", "trung binh": "~", "thap": "!"}.get(pair["confidence"], " ")
        still = [k for k in gaps if k not in usda]
        print(f"  {flag} {entry['name_vi']:<18} vay {len(borrowed)}: {', '.join(borrowed) or '—'}")
        if still:
            print(f"      vẫn thiếu: {', '.join(still)}")

        result[code] = entry
        # Lịch sự với máy chủ; hạn mức là 1.000 lượt/giờ nên không cần vội.
        time.sleep(0.4)

    print(f"\nĐã vay {filled_count} giá trị.")
    if skipped:
        print(f"Không gọi được: {', '.join(skipped)}")

    print("\nĐộ phủ sau khi vá:")
    total = len(result)
    for key in LOCKED + list(BORROWABLE):
        have = sum(1 for e in result.values() if key in e["values"])
        from_usda = sum(
            1 for e in result.values() if e["sources"].get(key) == SRC_USDA
        )
        tail = f"  (vay {from_usda})" if from_usda else ""
        print(f"  {key:<16} {have:>3}/{total}  {have / total * 100:>5.1f} %{tail}")

    if args.dry_run:
        print("\n(--dry-run: không ghi tệp)")
        return 0

    OUT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\nĐã ghi → {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
