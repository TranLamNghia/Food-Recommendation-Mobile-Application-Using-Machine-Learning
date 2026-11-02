#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sinh tệp SQL tạo cơ sở dữ liệu TỪ mô hình ERD trong `BAOCAO/Diagram.mdj`.

Nguồn duy nhất là mô hình ERD tiếng Anh (`ERD`). Tệp `db/schema.sql` KHÔNG
được đọc tới — mục đích của bước này là chứng minh sơ đồ nộp kèm báo cáo
sinh ra được đúng lược đồ, chứ không phải chép lại lược đồ có sẵn.

ERD của StarUML chỉ ghi TÊN KIỂU, không ghi độ dài và độ chính xác, cũng
không ghi giá trị mặc định. Nên phải có vài quy ước bù vào, và chỉ đúng
những quy ước dưới đây — ngoài ra không thêm gì mà sơ đồ không nói:

    CHAR        -> CHAR(36)          khóa dạng UUID
    VARCHAR     -> VARCHAR(255)
    DECIMAL     -> DECIMAL(10,2)
    BIT         -> BIT(1)
    ENUM        -> giữ nguyên danh sách giá trị của sơ đồ

Riêng cách khóa chính NHẬN giá trị thì sơ đồ không nói được, mà không có nó
thì lược đồ không dùng được:

    khóa INT    -> AUTO_INCREMENT
    khóa CHAR   -> DEFAULT (UUID())

Bảng dùng khóa INT là các bảng danh mục tra cứu, vì khóa UUID 36 ký tự làm
chúng rất khó đọc khi mở thẳng cơ sở dữ liệu ra xem. Các bảng còn lại dùng
CHAR(36).

Khóa ngoại suy từ tên cột (`user_id` -> `users.id`). Sơ đồ có 29 cột mang cờ
FK nhưng không cột nào đặt `referenceTo`, nên không suy được từ chính sơ đồ.
Script tự đối chiếu: đủ 29 cột và mọi bảng đích phải tồn tại, lệch thì dừng.

KHÔNG sinh một dòng dữ liệu nào.

Chạy:
    python tools/baocao/xuat_sql_tu_erd.py
    python tools/baocao/xuat_sql_tu_erd.py --ra duong/dan/khac.sql
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MDJ = ROOT / "BAOCAO" / "Diagram.mdj"
RA_MAC_DINH = ROOT / "BAOCAO" / "CSDL_DATN_TranLamNghia.sql"

TEN_MO_HINH = "ERD"
TEN_CSDL = "nutrition_rec"

# Bảng danh mục tra cứu: khóa INT cho dễ đọc khi nhìn thẳng cơ sở dữ liệu.
BANG_KHOA_INT = {
    "conditions",
    "condition_rules",
    "tags",
    "food_categories",
    "rda_reference",
}

# Hậu tố tên cột -> bảng được trỏ tới. Xét theo thứ tự, lấy khớp dài nhất
# trước: `replaced_by_food_id` phải khớp trước `food_id`.
SUY_FK = [
    ("replaced_by_food_id", "foods"),
    ("meal_plan_id", "meal_plans"),
    ("condition_id", "conditions"),
    ("category_id", "food_categories"),
    ("owner_id", "users"),
    ("model_id", "ml_models"),
    ("user_id", "users"),
    ("food_id", "foods"),
    ("tag_id", "tags"),
]

DAI_CHAR = 36
DAI_VARCHAR = 255
DO_CHINH_XAC_DECIMAL = "10,2"

# ── Cột dẫn xuất ──────────────────────────────────────────────────────────
# Ba cột này KHÔNG lưu dữ liệu: `VIRTUAL` nên MySQL không ghi byte nào xuống
# đĩa, chỉ tính lại mỗi lần đọc. Để công thức trong lược đồ thay vì trong mã
# ứng dụng vì mỗi công thức được đọc từ nhiều nơi (ứng dụng Flutter, dịch vụ
# máy chủ, mô-đun Python) — viết ba lần là ba cơ hội để ba bản lệch nhau.
#
# Sơ đồ ERD không có chỗ ghi biểu thức sinh, nên phải khai ở đây. Đây là
# ngoại lệ DUY NHẤT so với nguyên tắc "không thêm gì sơ đồ không nói".
COT_SINH = {
    # Chỉ số khối cơ thể. Tính lại theo cân nặng mới nhất, nên không bao giờ
    # lạc hậu như một cột lưu sẵn.
    ("health_profiles", "bmi"):
        "weight_kg / ((height_cm / 100) * (height_cm / 100))",

    # Độ lệch năng lượng cả ngày so với hạn mức, tính bằng phần trăm. Đây là
    # tiêu chí nghiệm thu của đồ án ("lệch không quá 10 %"), nên công thức
    # nằm ở lược đồ để báo cáo và ứng dụng cùng lấy một con số.
    # `actual_*` còn NULL khi chưa sinh thực đơn, biểu thức trả NULL —
    # "chưa đo được", không phải 0.
    ("meal_plans", "calorie_deviation_pct"):
        "100 * (actual_calories_kcal - target_calories_kcal) "
        "/ target_calories_kcal",

}

# ── Cột bỏ khỏi thiết kế ──────────────────────────────────────────────────
# Để trống là đúng: sơ đồ ERD hiện không còn vẽ cột nào đã bỏ khỏi lược đồ.
#
# Chỗ này từng khai `rda_reference.qualifier_key` — một cột sinh
# `COALESCE(qualifier,'')` tồn tại chỉ để khóa `uq_rda` chặn được trùng ở
# những dòng `qualifier IS NULL`, vì MySQL coi mọi NULL là khác nhau. Nay
# phép quy đổi nằm thẳng trong khóa dạng khóa hàm nên cột trung gian không
# cần nữa, và sơ đồ cũng đã xóa nó ở cả hai mô hình.
#
# Giữ lại cơ chế này cho lần sau: khi bỏ một cột khỏi `db/schema.sql` mà
# chưa kịp xóa trong StarUML, khai nó vào đây để tệp nộp vẫn đúng; script sẽ
# nhắc gỡ khi sơ đồ đã được sửa.
COT_BO: set[tuple[str, str]] = set()

# Khóa mà sơ đồ không ghi được vì nó gồm nhiều cột, hoặc vì nó chứa biểu
# thức. Chỉ khai những khóa thật sự cần cho đúng đắn — không chép toàn bộ
# khóa ghép của lược đồ thật vào đây.
KHOA_GHEP = {
    "rda_reference": [
        "UNIQUE KEY uq_rda "
        "(gender, age_min, age_max, nutrient, (COALESCE(qualifier, '')))",
    ],
}


def doc_mo_hinh() -> list[dict]:
    """Lấy danh sách thực thể của mô hình ERD tiếng Anh."""
    if not MDJ.exists():
        sys.exit(f"Không thấy {MDJ}")
    d = json.loads(MDJ.read_text(encoding="utf-8"))

    mo_hinh = [e for e in d["ownedElements"] if e["_type"] == "ERDDataModel"]
    m = next((e for e in mo_hinh if e["name"].strip() == TEN_MO_HINH), None)
    if m is None:
        sys.exit(f"Không thấy mô hình {TEN_MO_HINH!r}. Đang có: "
                 + ", ".join(repr(e["name"].strip()) for e in mo_hinh))

    ents = [e for e in m["ownedElements"] if e["_type"] == "ERDEntity"]
    if not ents:
        sys.exit(f"Mô hình {TEN_MO_HINH!r} không có thực thể nào.")
    return ents


def bang_dich(ten_cot: str) -> str | None:
    for hau_to, bang in SUY_FK:
        if ten_cot == hau_to:
            return bang
    return None


def kieu_sql(cot: dict, la_khoa_int: bool) -> str:
    """Đổi tên kiểu của sơ đồ thành kiểu MySQL đầy đủ."""
    t = (cot.get("type") or "").strip()

    if t.upper().startswith("ENUM"):
        gia_tri = re.findall(r"'([^']*)'", t)
        if not gia_tri:
            sys.exit(f"ENUM không có giá trị: {cot.get('name')}")
        return "ENUM(" + ",".join(f"'{v}'" for v in gia_tri) + ")"

    if la_khoa_int:
        return "INT UNSIGNED"

    bang = {
        "CHAR": f"CHAR({DAI_CHAR})",
        "VARCHAR": f"VARCHAR({DAI_VARCHAR})",
        "DECIMAL": f"DECIMAL({DO_CHINH_XAC_DECIMAL})",
        "BIT": "BIT(1)",
    }
    return bang.get(t.upper(), t.upper())


def sap_xep(ents: list[dict], fk: dict[str, list[tuple[str, str]]]) -> list[str]:
    """Sắp bảng cha trước bảng con, để chạy một lượt từ trên xuống là được."""
    ten = [e["name"] for e in ents]
    phu_thuoc = {t: {b for _, b in fk.get(t, []) if b != t} for t in ten}

    xong, thu_tu = set(), []
    while len(thu_tu) < len(ten):
        san = [t for t in ten
               if t not in xong and phu_thuoc[t] <= xong]
        if not san:
            con_lai = [t for t in ten if t not in xong]
            sys.exit(f"Khóa ngoại tạo thành vòng, không sắp được: {con_lai}")
        san.sort()
        thu_tu += san
        xong |= set(san)
    return thu_tu


def dung_bang(e: dict, dung_int: dict[str, bool]) -> str:
    ten = e["name"]
    cols = [c for c in e.get("columns", [])
            if (ten, c["name"]) not in COT_BO]
    dong: list[str] = []

    khoa_chinh = [c["name"] for c in cols if c.get("primaryKey")]
    rong = max(len(c["name"]) for c in cols) + 2

    for c in cols:
        ten_cot = c["name"]
        dich = bang_dich(ten_cot) if c.get("foreignKey") else None

        # Cột khóa phải cùng kiểu với cột nó trỏ tới, nếu không MySQL từ chối.
        if dich is not None:
            la_int = dung_int[dich]
        elif ten_cot == "id":
            la_int = dung_int[ten]
        else:
            la_int = False

        s = f"    {ten_cot:<{rong}}{kieu_sql(c, la_int)}"

        bieu_thuc = COT_SINH.get((ten, ten_cot))
        if bieu_thuc is not None:
            # Thứ tự MySQL bắt buộc: AS (…) rồi VIRTUAL rồi mới tới NULL.
            s += f" GENERATED ALWAYS AS ({bieu_thuc}) VIRTUAL"
            s += " NULL" if c.get("nullable") else " NOT NULL"
            dong.append(s)
            continue

        s += " NULL" if c.get("nullable") else " NOT NULL"
        if ten_cot == "id" and ten_cot in khoa_chinh:
            s += " AUTO_INCREMENT" if la_int else " DEFAULT (UUID())"
        dong.append(s)

    if khoa_chinh:
        dong.append(f"    PRIMARY KEY ({', '.join(khoa_chinh)})")

    for c in cols:
        if c.get("unique") and not c.get("primaryKey"):
            dong.append(f"    UNIQUE KEY uq_{ten}_{c['name']} ({c['name']})")

    for k in KHOA_GHEP.get(ten, []):
        dong.append(f"    {k}")

    for c in cols:
        if c.get("foreignKey"):
            dich = bang_dich(c["name"])
            dong.append(f"    FOREIGN KEY ({c['name']}) "
                        f"REFERENCES {dich}(id)")

    return (f"CREATE TABLE {ten} (\n" + ",\n".join(dong)
            + "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 "
              "COLLATE=utf8mb4_unicode_ci;")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ra", default=str(RA_MAC_DINH))
    args = ap.parse_args()

    ents = doc_mo_hinh()
    theo_ten = {e["name"]: e for e in ents}
    dung_int = {t: t in BANG_KHOA_INT for t in theo_ten}

    # ── Suy và kiểm khóa ngoại ──
    fk: dict[str, list[tuple[str, str]]] = defaultdict(list)
    thieu = []
    for e in ents:
        for c in e.get("columns", []):
            if not c.get("foreignKey"):
                continue
            dich = bang_dich(c["name"])
            if dich is None or dich not in theo_ten:
                thieu.append(f"{e['name']}.{c['name']}")
            else:
                fk[e["name"]].append((c["name"], dich))
    if thieu:
        sys.exit("Không suy được bảng đích cho các cột khóa ngoại: "
                 + ", ".join(thieu))

    so_fk = sum(len(v) for v in fk.values())
    so_cot = sum(1 for e in ents for c in e.get("columns", [])
                 if (e["name"], c["name"]) not in COT_BO)

    # Cột sinh khai bằng tay, nên phải chắc tên vẫn còn trong sơ đồ. Đổi tên
    # cột mà quên sửa ở đây thì công thức biến mất không một lời cảnh báo.
    co_that = {(e["name"], c["name"])
               for e in ents for c in e.get("columns", [])}
    lac = sorted(f"{t}.{c}" for t, c in COT_SINH if (t, c) not in co_that)
    if lac:
        sys.exit("Khai cột sinh cho cột không có trong sơ đồ: "
                 + ", ".join(lac))
    # Không dừng: sơ đồ đã bỏ cột rồi thì kết quả vẫn đúng, chỉ là khai thừa.
    thua = sorted(f"{t}.{c}" for t, c in COT_BO if (t, c) not in co_that)
    if thua:
        print("   Lưu ý: sơ đồ đã không còn vẽ " + ", ".join(thua)
              + " — gỡ khỏi COT_BO cho gọn.")
    lac_bang = sorted(b for b in KHOA_GHEP if b not in theo_ten)
    if lac_bang:
        sys.exit("Khai khóa ghép cho bảng không có trong sơ đồ: "
                 + ", ".join(lac_bang))

    thu_tu = sap_xep(ents, fk)

    dau = [
        "-- ════════════════════════════════════════════════════════════════",
        f"-- Cơ sở dữ liệu `{TEN_CSDL}`",
        "-- Ứng dụng di động khuyến nghị thực đơn dinh dưỡng cá nhân hóa",
        "-- Sinh viên: Trần Lâm Nghĩa — 22115053122231",
        "--",
        "-- Tệp này được SINH TỰ ĐỘNG từ mô hình ERD trong BAOCAO/Diagram.mdj",
        "-- bằng tools/baocao/xuat_sql_tu_erd.py. Sửa sơ đồ rồi chạy lại,",
        "-- đừng sửa tay vào đây.",
        f"-- Ngày sinh tệp: {date.today():%d/%m/%Y}",
        "--",
        f"-- {len(ents)} bảng · {so_cot} cột · {so_fk} khóa ngoại · 0 dòng dữ liệu",
        f"-- Trong đó {len(COT_SINH)} cột là cột DẪN XUẤT, không lưu dữ liệu:",
        "--   health_profiles.bmi              = cân nặng / bình phương chiều cao",
        "--   meal_plans.calorie_deviation_pct = % lệch so với hạn mức năng lượng",
        "-- Cả hai khai VIRTUAL: MySQL không ghi byte nào xuống đĩa, chỉ tính",
        "-- lại lúc đọc. Không có dư thừa lưu trữ nên không sinh dị thường",
        "-- cập nhật — thứ mà dạng chuẩn 3 đặt ra để ngăn.",
        "--",
        "-- Khóa `rda_reference.uq_rda` đi qua COALESCE ngay trong khóa (khóa",
        "-- hàm, MySQL 8.0.13+): MySQL coi mọi NULL là khác nhau, nên khóa đi",
        "-- thẳng qua `qualifier` sẽ không chặn trùng ở những dòng để trống.",
        "--",
        "-- Quy ước bù cho những gì sơ đồ ERD không ghi được:",
        f"--   CHAR -> CHAR({DAI_CHAR}) · VARCHAR -> VARCHAR({DAI_VARCHAR})",
        f"--   DECIMAL -> DECIMAL({DO_CHINH_XAC_DECIMAL}) · BIT -> BIT(1)",
        "--   Khóa chính: bảng danh mục dùng INT AUTO_INCREMENT cho dễ đọc,",
        "--   các bảng còn lại dùng CHAR(36) DEFAULT (UUID()).",
        "-- ════════════════════════════════════════════════════════════════",
        "",
        "SET NAMES utf8mb4;",
        "SET FOREIGN_KEY_CHECKS = 0;",
        "",
        f"DROP DATABASE IF EXISTS {TEN_CSDL};",
        f"CREATE DATABASE {TEN_CSDL}",
        "    DEFAULT CHARACTER SET utf8mb4",
        "    DEFAULT COLLATE utf8mb4_unicode_ci;",
        f"USE {TEN_CSDL};",
        "",
    ]

    than = []
    for t in thu_tu:
        cha = sorted({b for _, b in fk.get(t, []) if b != t})
        ghi = f"  (phụ thuộc: {', '.join(cha)})" if cha else "  (bảng gốc)"
        than.append("-- " + "─" * 70)
        than.append(f"-- {t}{ghi}")
        than.append("-- " + "─" * 70)
        than.append(dung_bang(theo_ten[t], dung_int))
        than.append("")

    cuoi = ["SET FOREIGN_KEY_CHECKS = 1;", ""]

    ra = Path(args.ra)
    ra.parent.mkdir(parents=True, exist_ok=True)
    ra.write_text("\n".join(dau + than + cuoi), encoding="utf-8")

    print(f"Đọc mô hình {TEN_MO_HINH!r}: {len(ents)} bảng, {so_cot} cột, "
          f"{so_fk} khóa ngoại")
    print(f"Khóa INT: {', '.join(sorted(BANG_KHOA_INT))}")
    print(f"Đã ghi {ra.relative_to(ROOT)} ({ra.stat().st_size:,} byte)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
