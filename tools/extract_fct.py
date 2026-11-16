#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract the Vietnamese Food Composition Table 2007 into JSON.

The source is a 567-page PDF, one food per A4 page, 526 foods across 14
groups. Opening the PDF and looking things up by hand is not viable when
building a dataset of 300-500 dishes, so this step turns it into a JSON file
a script can query.

A note on the Vietnamese names: the PDF uses the legacy TCVN3 (ABC) font, so
the extracted Vietnamese names come out mis-encoded — "Mắm tép chua" becomes
"M¾m tÐp chua". The English names are clean ASCII, so **lookups go by the
English name**; the Vietnamese name is kept in its raw form for eyeball
comparison when needed.

Source: National Institute of Nutrition (2007), the PDF archived by FAO.
https://www.fao.org/fileadmin/templates/food_composition/documents/pdf/VTN_FCT_2007.pdf

Run:
    python tools/extract_fct.py <pdf-path> [-o data/reference/fct2007.json]

Note on language: the regular expressions below and the group names stay
Vietnamese because they **match the Vietnamese text inside the PDF** and
become data in the output JSON. Only the code around them is English.
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
    sys.exit("pymupdf is required:  pip install pymupdf")

# The nutrients to pull out. The key is the column name in the food CSV, the
# value is the pattern to find in the PDF's text. Only the nutrients the
# dataset actually uses — the source table has 86, most of them irrelevant
# to this problem.
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

    # The four components of vitamin A activity. The source table publishes
    # **no "total vitamin A" column** — it prints retinol and the carotenoids
    # separately and leaves the conversion to the reader. Each component is
    # taken separately, converted in `vitamin_a_rae`, and all four raw figures
    # are kept in the JSON so the result can be traced back.
    #
    # The unit is microgram, printed with the character μ (U+03BC) on some
    # pages and µ (U+00B5) on others — both have to be matched, otherwise
    # figures are silently lost on exactly the pages using the other one.
    "retinol_mcg": r"Vitamin A \(Retinol\)\s*[μµ]g\s+([\d.]+|-)",
    "beta_carotene_mcg": r"Beta-caroten\s+[μµ]g\s+([\d.]+|-)",
    "alpha_carotene_mcg": r"Alpha-caroten\s+[μµ]g\s+([\d.]+|-)",
    "beta_cryptoxanthin_mcg": r"Beta-cryptoxanthin\s+[μµ]g\s+([\d.]+|-)",
}

# Convert vitamin A activity to RAE (Retinol Activity Equivalent).
#
# Why convert rather than take the retinol column directly: **retinol is 0 in
# every plant food** — measured over the source table, 84 of 373 entries have
# non-zero retinol, almost all of them meat, egg, milk or liver. Taking
# retinol directly would give carrot, pumpkin and Vietnamese bitterleaf 0 mg
# of vitamin A, which is nutritionally wrong rather than merely missing.
#
# The factors are IOM (2001), the same ones USDA uses for its Vitamin A RAE
# column:
#   1 ug RAE = 1 ug retinol
#            = 12 ug beta-carotene from food
#            = 24 ug alpha-carotene or beta-cryptoxanthin
# These are smaller than the 1:6 and 1:12 RE factors of FAO/WHO 1967, because
# later measurements found carotenoid absorption from food to be lower than
# the old estimate. Using RAE means **choosing the lower number**, so it does
# not flatter the data.
RAE_FACTORS = {
    "retinol_mcg": 1.0,
    "beta_carotene_mcg": 1 / 12,
    "alpha_carotene_mcg": 1 / 24,
    "beta_cryptoxanthin_mcg": 1 / 24,
}

# Food names have to be read by **coordinate**, not from plain text.
#
# At the top of each page the label and the name are two separate text
# objects on the same line but in different columns:
#
#     x=75                              x=223
#     "Tªn thùc phÈm (Vietnamese):"     "C¸ bèng"
#     "Tªn tiÕng Anh (English):"        "Goby, gudgeon"
#
# Extracting from plain text gives an unstable object order: some pages
# return the name, some return the label itself, some return the caption
# "Thành phần dinh dưỡng trong 100g phần ăn được" sitting just below. The
# only reliable approach is to find the label and take the object at the same
# height, offset to the right.
RE_STT = re.compile(r"STT:\s*(\d+)")
RE_CODE = re.compile(r"M·\s*sè:\s*(\d+)")
RE_WASTE = re.compile(r"Th¶i bá \(%\):\s*([\d.]+)")

# Height tolerance when pairing a label with a name. Two objects on the same
# line still differ by a point or two because of differing fonts and sizes.
Y_TOLERANCE = 6.0


def name_beside(spans, marker):
    """The name on the same line as the `marker` label, offset to the right."""
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


# The group is derived from the first digits of the code, following the
# layout stated at the front of the table. Vietnamese because these strings
# become data in the output.
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
    """A `-` in the table means no measurement, which is not the value 0."""
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

        # Flatten onto one line: the label-value pairs in the PDF are often
        # broken across lines because the page is laid out in two columns.
        flat = " ".join(text.split())
        for key, pattern in NUTRIENTS.items():
            m = re.search(pattern, flat)
            entry[key] = parse_value(m.group(1)) if m else None

        # A missing component counts as 0, but if **all four** are missing
        # leave it empty rather than writing 0: a 0 could not be told apart
        # from "this food contains no vitamin A" versus "the source table did
        # not measure it".
        present = [k for k in RAE_FACTORS if entry.get(k) is not None]
        entry["vitamin_a_mcg"] = (
            round(sum(entry[k] * RAE_FACTORS[k] for k in present), 2)
            if present else None
        )
        entry["vitamin_a_parts_missing"] = [
            k for k in RAE_FACTORS if entry.get(k) is None
        ]

        foods.append(entry)

    return foods


def _use_utf8() -> None:
    """Make stdout accept non-ASCII output on Windows (it defaults to cp1252).

    Without it the script dies mid-run with `UnicodeEncodeError` as soon as
    output is redirected through a pipe or into a file — which is to say
    exactly when running in CI. A copy of `tools/_env.use_utf8`, kept here
    because this script is run standalone with a PDF path and does not need
    the rest of `_env`.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover
            pass


def main() -> int:
    _use_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="path to VTN_FCT_2007.pdf")
    parser.add_argument(
        "-o", "--out", type=Path,
        default=Path(__file__).resolve().parent.parent
        / "data" / "reference" / "fct2007.json",
    )
    args = parser.parse_args()

    if not args.pdf.exists():
        sys.exit(f"File not found: {args.pdf}")

    foods = extract(args.pdf)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(foods, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    print(f"Extracted {len(foods)} foods -> {args.out}")

    missing = [f["name_en"] for f in foods if f["calories_kcal"] is None]
    if missing:
        print(
            f"No energy figure for {len(missing)} entries: "
            f"{', '.join(missing[:5])}..."
        )

    # Name quality check. Mandatory, because when the PDF layout is not as
    # expected the extraction still returns *some string* — its own label, or
    # the caption below it — rather than raising. Without this scan a whole
    # food group could carry junk names with nobody noticing.
    JUNK = ("STT:", "(English)", "(Vietnamese)", "Thμnh phÇn", "edible portion")
    bad = [
        f for f in foods
        if not f["name_en"] or any(j in f["name_en"] for j in JUNK)
        or len(f["name_en"]) < 3
    ]
    if bad:
        print(f"\n! {len(bad)}/{len(foods)} entries have a suspicious name:")
        for f in bad[:8]:
            print(f"   [{f['code']}] page {f['page']}: {f['name_en']!r}")
    else:
        print(f"English names: {len(foods)}/{len(foods)} valid.")

    coverage = {
        key: sum(1 for f in foods if f[key] is not None)
        for key in list(NUTRIENTS) + ["vitamin_a_mcg"]
    }
    print("\nCoverage per nutrient:")
    for key, n in sorted(coverage.items(), key=lambda kv: -kv[1]):
        print(f"  {key:<16} {n:>4}/{len(foods)}  {n / len(foods) * 100:>5.1f} %")

    return 0


if __name__ == "__main__":
    sys.exit(main())
