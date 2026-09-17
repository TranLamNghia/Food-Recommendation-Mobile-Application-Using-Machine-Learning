#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trích số liệu từ Bảng thành phần thực phẩm Việt Nam 2007 ra JSON.

Bảng gốc là PDF 567 trang, mỗi thực phẩm một trang A4, 526 thực phẩm chia
14 nhóm. Mở PDF tra tay từng lần là không khả thi khi phải dựng tập dữ liệu
300–500 món, nên bước này biến nó thành một tệp JSON tra được bằng script.

Lưu ý về tên tiếng Việt: PDF dùng phông TCVN3 (ABC) đời cũ nên tên tiếng
Việt trích ra bị sai mã — "Mắm tép chua" thành "M¾m tÐp chua". Tên tiếng Anh
là ASCII sạch nên **tra cứu đi theo tên tiếng Anh**; tên tiếng Việt giữ
nguyên dạng thô để đối chiếu bằng mắt khi cần.

Nguồn: Viện Dinh dưỡng Quốc gia (2007), bản PDF do FAO lưu trữ.
https://www.fao.org/fileadmin/templates/food_composition/documents/pdf/VTN_FCT_2007.pdf

Chạy:
    python tools/extract_fct.py <đường-dẫn-pdf> [-o data/reference/fct2007.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import pymupdf
except ImportError:
    sys.exit("Cần cài pymupdf:  pip install pymupdf")

# Các chất cần lấy. Khóa là tên cột trong CSV món ăn, giá trị là mẫu tìm
# trong dòng văn bản của PDF. Chỉ lấy những chất tập dữ liệu thật sự dùng —
# bảng gốc có 86 chất, phần lớn không liên quan tới bài toán này.
NUTRIENTS = {
    "water_g": r"Nước \(Water\s*\)\s*g\s+([\d.]+|-)",
    "calories_kcal": r"Năng lượng \(Energy\s*\)\s*KCal\s+([\d.]+|-)",
    "protein_g": r"Protein\s+g\s+([\d.]+|-)",
    "fat_g": r"Lipid \(Fat\)\s*g\s+([\d.]+|-)",
    "carbs_g": r"Glucid \(Carbohydrate\)\s*g\s+([\d.]+|-)",
    "fiber_g": r"Celluloza \(Fiber\)\s*g\s+([\d.]+|-)",
    "sugar_g": r"Đường tổng số \(Sugar\)\s*g\s+([\d.]+|-)",
    "calcium_mg": r"Calci \(Calcium\)\s*mg\s+([\d.]+|-)",
    "iron_mg": r"Sắt \(Iron\)\s*mg\s+([\d.]+|-)",
    "sodium_mg": r"Natri \(Sodium\)\s*mg\s+([\d.]+|-)",
    "zinc_mg": r"Kẽm \(Zinc\)\s*mg\s+([\d.]+|-)",
    "vitamin_c_mg": r"Vitamin C \(Ascorbic acid\)\s*mg\s+([\d.]+|-)",
    "cholesterol_mg": r"Cholesterol\s+mg\s+([\d.]+|-)",
    "purine_mg": r"Purin\s+mg\s+([\d.]+|-)",
}

# Tên thực phẩm phải lấy theo **tọa độ**, không lấy theo văn bản thuần.
#
# Đầu mỗi trang, nhãn và tên là hai đối tượng văn bản rời nhau nằm cùng một
# dòng nhưng khác cột:
#
#     x=75                              x=223
#     "Tªn thùc phÈm (Vietnamese):"     "C¸ bèng"
#     "Tªn tiÕng Anh (English):"        "Goby, gudgeon"
#
# Trích theo văn bản thuần thì thứ tự các đối tượng không ổn định: có trang
# trả về tên, có trang trả về chính cái nhãn, có trang trả về dòng chú thích
# "Thành phần dinh dưỡng trong 100g phần ăn được" nằm ngay dưới. Cách duy
# nhất đáng tin là tìm nhãn rồi lấy đối tượng nằm cùng cao độ, lệch sang phải.
RE_STT = re.compile(r"STT:\s*(\d+)")
RE_CODE = re.compile(r"M·\s*sè:\s*(\d+)")
RE_WASTE = re.compile(r"Th¶i bá \(%\):\s*([\d.]+)")

# Dung sai cao độ khi ghép nhãn với tên. Hai đối tượng cùng dòng vẫn lệch
# nhau một hai điểm vì khác phông và khác cỡ chữ.
Y_TOLERANCE = 6.0


def name_beside(spans, marker):
    """Tên nằm cùng dòng với nhãn `marker`, lệch sang phải."""
    label = next((s for s in spans if marker in s["text"]), None)
    if label is None:
        return ""

    y = label["bbox"][1]
    x = label["bbox"][2]
    candidates = [
        s for s in spans
        if abs(s["bbox"][1] - y) < Y_TOLERANCE
        and s["bbox"][0] > x
        and s["text"].strip()
        and "STT:" not in s["text"]
        and "sè:" not in s["text"]
        and not s["text"].strip().isdigit()
    ]
    candidates.sort(key=lambda s: s["bbox"][0])
    return " ".join(s["text"].strip() for s in candidates).strip()

# Nhóm suy từ hai chữ số đầu của mã số, theo bố cục nêu ở đầu bảng.
GROUPS = {
    1: "Ngũ cốc và sản phẩm chế biến",
    2: "Khoai củ và sản phẩm chế biến",
    3: "Hạt, quả giàu protein, lipid",
    4: "Rau, quả, củ dùng làm rau",
    5: "Quả chín",
    6: "Dầu, mỡ, bơ",
    7: "Thịt và sản phẩm chế biến",
    8: "Thủy sản và sản phẩm chế biến",
    9: "Trứng và sản phẩm chế biến",
    10: "Sữa và sản phẩm chế biến",
    11: "Đồ hộp",
    12: "Đồ ngọt (đường, bánh, mứt, kẹo)",
    13: "Gia vị, nước chấm",
    14: "Nước giải khát",
}


def parse_value(raw: str):
    """`-` trong bảng nghĩa là chưa có số liệu, khác hẳn với giá trị 0."""
    if raw == "-":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def extract(pdf_path: Path) -> list[dict]:
    doc = pymupdf.open(str(pdf_path))
    foods = []

    for page_no, page in enumerate(doc, start=1):
        text = page.get_text()
        if "STT:" not in text or "Năng lượng" not in text:
            continue

        m_stt = RE_STT.search(text)
        m_code = RE_CODE.search(text)
        if not m_stt or not m_code:
            continue

        code = m_code.group(1)
        group_id = int(code[:-3]) if len(code) > 3 else 0

        spans = [
            s
            for b in page.get_text("dict")["blocks"]
            for l in b.get("lines", [])
            for s in l["spans"]
            if s["bbox"][1] < 100
        ]

        entry = {
            "stt": int(m_stt.group(1)),
            "code": code,
            "group": GROUPS.get(group_id, "?"),
            "name_en": name_beside(spans, "(English)"),
            "name_vi_raw": name_beside(spans, "(Vietnamese)"),
            "page": page_no,
        }

        m_waste = RE_WASTE.search(text)
        entry["waste_pct"] = float(m_waste.group(1)) if m_waste else None

        # Trải phẳng xuống một dòng: cặp nhãn–giá trị trong PDF hay bị ngắt
        # dòng giữa chừng vì trang chia hai cột.
        flat = " ".join(text.split())
        for key, pattern in NUTRIENTS.items():
            m = re.search(pattern, flat)
            entry[key] = parse_value(m.group(1)) if m else None

        foods.append(entry)

    return foods


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="đường dẫn tới VTN_FCT_2007.pdf")
    parser.add_argument(
        "-o", "--out", type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "reference" / "fct2007.json",
    )
    args = parser.parse_args()

    if not args.pdf.exists():
        sys.exit(f"Không thấy tệp: {args.pdf}")

    foods = extract(args.pdf)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(foods, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    print(f"Đã trích {len(foods)} thực phẩm → {args.out}")

    missing = [f["name_en"] for f in foods if f["calories_kcal"] is None]
    if missing:
        print(f"Thiếu năng lượng ở {len(missing)} mục: {', '.join(missing[:5])}…")

    # Kiểm tra chất lượng tên. Bắt buộc phải có, vì khi bố cục PDF không như
    # mong đợi thì phép trích vẫn trả về *một chuỗi gì đó* — nhãn của chính
    # nó, hay dòng chú thích bên dưới — chứ không báo lỗi. Không dò thì cả
    # một nhóm thực phẩm có thể mang tên rác mà không ai biết.
    JUNK = ("STT:", "(English)", "(Vietnamese)", "Thμnh phÇn", "edible portion")
    bad = [
        f for f in foods
        if not f["name_en"] or any(j in f["name_en"] for j in JUNK)
        or len(f["name_en"]) < 3
    ]
    if bad:
        print(f"\n⚠ {len(bad)}/{len(foods)} mục có tên đáng ngờ:")
        for f in bad[:8]:
            print(f"   [{f['code']}] trang {f['page']}: {f['name_en']!r}")
    else:
        print(f"Tên tiếng Anh: {len(foods)}/{len(foods)} hợp lệ.")

    coverage = {
        key: sum(1 for f in foods if f[key] is not None)
        for key in NUTRIENTS
    }
    print("\nĐộ phủ từng chất:")
    for key, n in sorted(coverage.items(), key=lambda kv: -kv[1]):
        print(f"  {key:<16} {n:>4}/{len(foods)}  {n / len(foods) * 100:>5.1f} %")

    return 0


if __name__ == "__main__":
    sys.exit(main())
