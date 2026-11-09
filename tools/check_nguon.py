#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mọi nguồn đang dẫn trong hệ thống phải có mặt trong Tài liệu tham khảo.

Vì sao cần. Ngưỡng dinh dưỡng trong `condition_rules` ghi xuất xứ ở cột
`note`, còn `rda_reference` ghi ở cột `source`. Thêm một bệnh lý với một
hướng dẫn mới là thêm một nguồn — và không gì nhắc phải bổ sung nó vào danh
sách tài liệu tham khảo. Hậu quả không phải lỗi chạy: đồ án vẫn in ra bình
thường, chỉ là nó dẫn một hướng dẫn mà phần tài liệu tham khảo không có.
Hội đồng hỏi "số này ở đâu ra" thì không trả lời được bằng chính quyển đồ án.

Chiều kiểm là **từ CSDL sang tài liệu**, không ngược lại. Chiều ngược không
kiểm tự động được: thân bài nêu tên nguồn trong văn xuôi chứ không dùng dấu
trích dẫn `[n]`, nên một mục tài liệu tham khảo không chỗ nào dùng tới thì
chỉ người đọc nhận ra.

Bảng `DAU_HIEU` là bản khai tay: mỗi nguồn trong CSDL ứng với một dấu hiệu
nhận ra nó trong danh sách. Khai tay vì chuỗi trong `note` là văn xuôi tiếng
Việt ("Hướng dẫn tăng acid uric máu và gút của Nhật Bản") còn mục tài liệu
tham khảo là tên gốc tiếng Anh ("Japanese Society of Gout and Uric & Nucleic
Acids") — không có phép so chuỗi nào nối được hai thứ đó.

Chạy:
    python tools/check_nguon.py
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

NOIDUNG = ROOT / "tools" / "baocao" / "noidung_data.py"

#: Dấu hiệu trong `condition_rules.note` / `rda_reference.source`
#: → dấu hiệu nhận ra nguồn đó trong `TAI_LIEU`.
#:
#: Khóa là chuỗi xuất hiện trong CSDL; giá trị là chuỗi phải có trong danh
#: sách tài liệu tham khảo.
DAU_HIEU: dict[str, str] = {
    "WHO": "World Health Organization",
    "KDIGO": "Kidney Disease: Improving Global Outcomes",
    "ADA": "American Diabetes Association",
    "Dietary Guidelines for Americans 2015": "Dietary Guidelines for Americans",
    "AHA/ACC 2019": "2019 ACC/AHA Guideline",
    "gút của Nhật Bản": "Japanese Society of Gout",
    "NIN Vietnamese RDAs 2016": "Nhu cầu dinh dưỡng khuyến nghị cho người Việt Nam",
    "WHO carbohydrate guideline 2023": "Carbohydrate intake for adults and children",
}

#: Nguồn được dẫn trong mã hoặc tài liệu thiết kế, không nằm trong CSDL.
#:
#: Vẫn phải có trong danh sách, vì thân bài hoặc chú thích mã có nêu tên.
NGUON_TRONG_MA: dict[str, str] = {
    "Mifflin-St Jeor": "Mifflin",
    "WHO Expert Consultation (2004)": "Appropriate body-mass index for Asian",
    "Bảng thành phần thực phẩm Việt Nam 2007": "Bảng thành phần thực phẩm Việt Nam",
    "USDA FoodData Central": "FoodData Central",
    "Rocchio": "Rocchio",
    "scikit-learn": "Scikit-learn",
    "chặn dưới Wilson": "Wilson",
    "nDCG": "Cumulated gain-based evaluation",
}

#: Mục còn chờ bổ sung phiên bản hoặc năm. Không coi là lỗi, nhưng phải
#: nhắc mỗi lần chạy — để nó không nằm im trong bản nộp.
CHO_BO_SUNG = "[bổ sung"


def nap_tai_lieu() -> list[str]:
    spec = importlib.util.spec_from_file_location("noidung_data", NOIDUNG)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return [noi for kieu, noi in mod.TAI_LIEU if kieu == "tl"]


def nap_nguon_csdl() -> set[str]:
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
            ghi_chu = [d["note"] for d in cur.fetchall()]
            cur.execute(
                "SELECT DISTINCT source FROM rda_reference "
                "WHERE source IS NOT NULL"
            )
            ghi_chu += [d["source"] for d in cur.fetchall()]
    finally:
        cn.close()

    thay = set()
    for chuoi in ghi_chu:
        for dau in DAU_HIEU:
            if dau in chuoi:
                thay.add(dau)
    return thay


def main() -> int:
    _env.in_utf8()
    print("Soát nguồn: CSDL và mã → Tài liệu tham khảo")
    print("=" * 72)

    muc = nap_tai_lieu()
    gop = "\n".join(muc)
    print(f"{len(muc)} mục trong TAI_LIEU\n")

    loi: list[str] = []
    dat = 0

    print("1. Nguồn đang dẫn trong CSDL")
    trong_csdl = nap_nguon_csdl()
    for dau in sorted(trong_csdl):
        can = DAU_HIEU[dau]
        if can in gop:
            dat += 1
            print(f"   ✓ {dau:38s} → {can[:36]}")
        else:
            loi.append(f"CSDL dẫn {dau!r} mà Tài liệu tham khảo không có {can!r}")
            print(f"   ✗ {dau:38s} → THIẾU {can!r}")

    khong_dung = sorted(set(DAU_HIEU) - trong_csdl)
    if khong_dung:
        print(f"\n   ~ {len(khong_dung)} dấu hiệu khai trong DAU_HIEU mà CSDL "
              f"không còn dẫn:")
        for d in khong_dung:
            print(f"       {d}")
        print("     Nếu quy tắc đã bỏ thì xóa dòng tương ứng khỏi DAU_HIEU.")

    print("\n2. Nguồn dẫn trong mã và tài liệu thiết kế")
    for ten, can in sorted(NGUON_TRONG_MA.items()):
        if can in gop:
            dat += 1
            print(f"   ✓ {ten:38s} → {can[:36]}")
        else:
            loi.append(f"Mã dẫn {ten!r} mà Tài liệu tham khảo không có {can!r}")
            print(f"   ✗ {ten:38s} → THIẾU {can!r}")

    print("\n3. Mục còn chờ bổ sung")
    cho = [m for m in muc if CHO_BO_SUNG in m]
    if cho:
        for m in cho:
            print(f"   ! {m[:92]}")
        print(f"   {len(cho)} mục cần điền phiên bản hoặc năm trước khi nộp.")
    else:
        print("   ✓ không mục nào còn chỗ trống")

    print("\n" + "=" * 72)
    if loi:
        print(f"{dat} mục đạt, {len(loi)} MỤC SAI:")
        for x in loi:
            print("  -", x)
        return 1
    print(f"Tất cả {dat} nguồn đang dẫn đều có trong Tài liệu tham khảo.")
    if cho:
        print(f"Còn {len(cho)} mục chờ bổ sung — xem mục 3.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
