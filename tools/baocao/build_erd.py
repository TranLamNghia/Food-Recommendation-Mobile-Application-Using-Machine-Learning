#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dựng lại hai sơ đồ ERD trong BAOCAO/Diagram.mdj từ CSDL đang chạy.

Sinh ra HAI mô hình ERD, cùng một lược đồ, khác nhau ở cách gọi tên:

    ERD            tên tiếng Anh không dấu — bản nộp kèm, vì yêu cầu của
                   môn là tên thực thể và tên thuộc tính không có dấu.
    ERD tiếng Việt tên tiếng Việt viết kiểu lạc đà, lấy từ `erd_vi.py` —
                   dùng cho phần thuyết minh trong báo cáo.

Cả hai nằm trong cùng tệp `.mdj`, mở bằng StarUML thấy hai sơ đồ ở mục
WORKING DIAGRAMS.

VÌ SAO SINH TỰ ĐỘNG CHỨ KHÔNG SỬA TAY
--------------------------------------
Sơ đồ gõ tay đã lệch khỏi CSDL theo kiểu rất khó thấy: thiếu bảng, sót cột
đã xóa, sót cột giữ chỗ tên `Column1`, sai kiểu dữ liệu, cột ENUM không có
tập giá trị, quan hệ bị nhân đôi hoặc nối sai cặp bảng. StarUML không báo gì
cả — sơ đồ vẫn mở ra bình thường. Sinh lại từ `information_schema` là cách
duy nhất giữ cho sơ đồ không thể lệch.

Nhánh `Model` (sơ đồ lớp) và nhánh `UseCase` (sơ đồ Use case) được ghi lại
NGUYÊN VĂN, kể cả toạ độ và đường nối đã lưu.

BỐ CỤC — XẾP SAO CHO ÍT ĐƯỜNG CẮT NHAU
---------------------------------------
Xếp theo lớp như phương pháp Sugiyama, ba bước:

1. CHIA LỚP. Bảng cha luôn ở hàng trên bảng con (bảng `HANG` bên dưới), nên
   mọi quan hệ đều chạy một chiều từ trên xuống.

2. NÚT ẢO. Quan hệ vượt quá một hàng được cắt thành nhiều chặng, mỗi hàng ở
   giữa chèn một nút ảo rộng 1 px. Nút ảo chiếm một cột riêng nên đường đi
   có lối dọc dành riêng, không phải len qua giữa các hộp. Đây là thứ thay
   đổi nhiều nhất: `users` có 11 bảng con nằm rải khắp ba hàng dưới, không
   có nút ảo thì 11 đường ấy cắt qua mọi thứ trên đường đi.

3. SẮP LẠI TRONG HÀNG. Quét xuôi rồi quét ngược nhiều lượt, mỗi lượt xếp
   các nút trong một hàng theo TRỌNG TÂM vị trí của những nút nối với nó ở
   hàng kề. Đếm số cặp đường cắt nhau sau mỗi lượt và giữ lại phương án tốt
   nhất, nên kết quả không bao giờ tệ hơn thứ tự ban đầu.

Đoạn đi ngang nằm trong dải trống giữa hai hàng. Mỗi dải chia thành các làn,
hai đoạn không đè lên nhau thì dùng chung một làn (tô màu đồ thị khoảng
cách kiểu tham lam), nên dải chỉ cao vừa đủ.

Chạy:
    python tools/baocao/build_erd.py            # ghi vào Diagram.mdj
    python tools/baocao/build_erd.py --dry-run  # chỉ in những gì sẽ đổi
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _env  # noqa: E402
from erd_vi import BANG, COT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
MDJ = ROOT / "BAOCAO" / "Diagram.mdj"
DB_NAME = "nutrition_rec"

# `_parent` của mọi mô hình con — chính là nút gốc Project của tệp.
ID_PROJECT = "AAAAAAFF+h6SjaM2Hec="
TEN_MODEL_VI = "ERD tiếng Việt"
TEN_DIAGRAM_VI = "ERDDiagram_VI"

FONT_FILE = r"C:\Windows\Fonts\arial.ttf"
FONT_BOLD = r"C:\Windows\Fonts\arialbd.ttf"
FONT_SIZE = 13

# ── Bố cục ───────────────────────────────────────────────────────────────
LE = 40            # lề quanh sơ đồ
KHE_NGANG = 64     # khoảng cách giữa hai cột trong một hàng
KHE_DOC = 72       # bề tối thiểu của dải trống giữa hai hàng
DEM_CHU = 70       # chừa thêm quanh chữ, đo từ sơ đồ cũ (hụt nhất 31)
RONG_TOI_THIEU = 120
RONG_NUT_AO = 1    # nút ảo chỉ là một cột mỏng dành chỗ cho đường đi

CAO_NHAN = 23      # từ đỉnh hộp xuống đỉnh khoang cột
CAO_DONG = 15      # mỗi dòng cột
DEM_KHOANG = 8     # chừa trên dưới trong khoang cột

CACH_LAN = 14      # khoảng cách giữa hai làn trong dải trống
SO_LUOT = 12     # số lượt quét xuôi–ngược khi sắp lại thứ tự trong hàng
SO_LUOT_X = 30   # số lượt nới toạ độ x về trọng tâm

# Các phương án bố cục đem ra thử. `tron` pha giữa phương án nới hết cỡ (1,0)
# và phương án xếp khít (0,0); `kieu_lan` là thứ tự xét khi chia làn trong dải
# trống. Không có công thức nào nói trước phương án nào đẹp hơn, nên dựng thử
# tất cả rồi chấm điểm bằng số chỗ cắt đo được trên hình.
THU_TRON = (0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 0.9, 1.0)
THU_LAN = ("trai", "trai_nguoc", "phai", "phai_nguoc", "dai", "dai_nguoc")

# Điểm = số chỗ cắt + bề ngang / PHAT_RONG, chọn phương án điểm thấp nhất.
#
# Đặt PHAT_RONG lớn nghĩa là ưu tiên ít đường cắt nhau, chấp nhận sơ đồ rộng
# ra; bề ngang chỉ còn là thứ để phân định khi hai phương án cắt nhau bằng
# nhau. Chọn vậy vì sơ đồ này dù hẹp cỡ nào cũng không đọc nổi khi ép vừa
# một trang A4 — phải phóng to hoặc cắt trang để xem — nên rộng thêm không
# mất gì, còn đường cắt nhau thì nhìn phát là thấy rối.
PHAT_RONG = 800

# Chia lớp. Ràng buộc DUY NHẤT: bảng cha phải nằm ở hàng trên bảng con —
# `kiem_hang()` kiểm lại bằng chính danh sách khóa ngoại đọc từ CSDL, nên
# xếp sai là script dừng chứ không ra sơ đồ sai.
#
# Thứ tự viết trong mỗi hàng chỉ là thứ tự KHỞI ĐẦU; bước sắp lại sẽ đổi,
# và chỉ đổi khi số đường cắt nhau giảm đi.
#
# Hai bảng rộng nhất là `rda_reference` và `condition_rules` — mỗi bảng gần
# 1.100 px vì cột `nutrient` liệt kê đủ 14 tên chất. Xếp chúng vào hàng nào
# thì hàng đó phình ra, nên đặt mỗi bảng một hàng khác nhau và đặt ở hàng
# nào ít hộp nhất. `condition_rules` không có bảng con nên xuống được hàng
# cuối; nhờ vậy sơ đồ hẹp bớt khoảng 800 px.
#
# `rda_reference` không dính khóa ngoại nào nên xếp đâu cũng hợp lệ; bước
# sắp xếp cũng không đụng tới nó vì nó không có nút kề để lấy trọng tâm.
# Thử đủ tám chỗ thì cuối hàng 2 cho cùng số chỗ cắt mà sơ đồ hẹp hơn
# chỗ tốt nhì khoảng 460 px.
HANG = [
    ["conditions", "tags", "users", "food_categories", "ml_models"],
    ["user_conditions", "health_profiles", "body_logs",
     "user_preference_profiles", "foods", "rda_reference"],
    ["food_nutrition", "food_tags", "meal_plans", "recommendations",
     "food_diary", "feedbacks", "interactions"],
    ["condition_rules", "meal_plan_items", "ml_training_samples",
     "ml_evaluations"],
]

NHAY = "'"


# ══════════════════════════════════════════════════════════════════════════
#  Đọc CSDL
# ══════════════════════════════════════════════════════════════════════════
def doc_csdl() -> dict:
    """Cột, khóa ngoại và ràng buộc duy nhất của CSDL, giữ đúng thứ tự cột."""
    import pymysql

    conn = pymysql.connect(
        host=_env.get("MYSQL_HOST", "localhost"),
        port=int(_env.get("MYSQL_PORT", "3306")),
        user=_env.require("MYSQL_USER"),
        password=_env.require("MYSQL_PASSWORD"),
        database=DB_NAME,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE "
                "FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s "
                "ORDER BY TABLE_NAME, ORDINAL_POSITION",
                (DB_NAME,),
            )
            cot: dict[str, list[dict]] = {}
            for bang, ten, kieu, co_null in cur.fetchall():
                cot.setdefault(bang, []).append(
                    {"ten": ten, "kieu": kieu, "null": co_null == "YES"}
                )

            cur.execute(
                "SELECT TABLE_NAME, COLUMN_NAME, CONSTRAINT_NAME, "
                "       REFERENCED_TABLE_NAME "
                "FROM information_schema.KEY_COLUMN_USAGE "
                "WHERE TABLE_SCHEMA = %s "
                "ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION",
                (DB_NAME,),
            )
            pk: set[tuple[str, str]] = set()
            fk: set[tuple[str, str]] = set()
            quan_he: list[tuple[str, str, str]] = []   # (cha, con, cột con)
            for bang, ten, rang_buoc, bang_cha in cur.fetchall():
                if rang_buoc == "PRIMARY":
                    pk.add((bang, ten))
                if bang_cha:
                    fk.add((bang, ten))
                    quan_he.append((bang_cha, bang, ten))

            # UNIQUE một cột khác UNIQUE nhiều cột: chỉ cột ĐỨNG MỘT MÌNH mới
            # được đánh dấu `unique`, nếu không người đọc sẽ tưởng một mình
            # cột đó đã là duy nhất. Cùng lập luận với tools/sync_erd_flags.py.
            cur.execute(
                "SELECT TABLE_NAME, INDEX_NAME, "
                "       GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) "
                "FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = %s AND NON_UNIQUE = 0 "
                "GROUP BY TABLE_NAME, INDEX_NAME",
                (DB_NAME,),
            )
            uq: set[tuple[str, str]] = set()
            for bang, chi_muc, cac_cot in cur.fetchall():
                if chi_muc == "PRIMARY" or "," in cac_cot:
                    continue
                uq.add((bang, cac_cot))

            return {"cot": cot, "pk": pk, "fk": fk, "uq": uq,
                    "quan_he": quan_he}
    finally:
        conn.close()


def kieu_hien(raw: str) -> str:
    """Kiểu MySQL viết lại cho sơ đồ: từ khóa in hoa, giá trị ENUM giữ nguyên.

    Giá trị ENUM phải giữ ĐÚNG chữ thường như trong CSDL, vì đó là dữ liệu
    thật — `'user'` chứ không phải `'USER'`. Chỉ in hoa phần từ khóa kiểu.
    """
    m = re.match(r"(\w+)(?:\((.*)\))?(.*)$", raw, re.S)
    if not m:
        return raw.upper()
    tu_khoa, tham_so, duoi = m.group(1).upper(), m.group(2), m.group(3)
    duoi = duoi.strip().upper()          # UNSIGNED, ZEROFILL…

    if tu_khoa in ("ENUM", "SET"):
        gia_tri = re.findall(NHAY + r"([^" + NHAY + r"]*)" + NHAY,
                             tham_so or "")
        tham_so = ", ".join(NHAY + v + NHAY for v in gia_tri)

    out = tu_khoa + (f"({tham_so})" if tham_so else "")
    return f"{out} {duoi}".strip()


# ══════════════════════════════════════════════════════════════════════════
#  Đo chữ
# ══════════════════════════════════════════════════════════════════════════
class Thuoc:
    """Đo bề rộng chữ bằng chính phông StarUML dùng (Arial 13).

    Không có Pillow thì quay về ước lượng 6,6 px/ký tự — rộng hơn thực tế
    một chút, nên hộp chỉ bị thừa chỗ chứ không bị cắt chữ.
    """

    def __init__(self) -> None:
        self.ve = None
        try:
            from PIL import Image, ImageDraw, ImageFont

            self.thuong = ImageFont.truetype(FONT_FILE, FONT_SIZE)
            self.dam = ImageFont.truetype(FONT_BOLD, FONT_SIZE)
            self.ve = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        except Exception as loi:                       # noqa: BLE001
            print(f"  (không đo được chữ: {loi} — dùng ước lượng)")

    def rong(self, text: str, dam: bool = False) -> float:
        if self.ve is None:
            return len(text) * (7.2 if dam else 6.6)
        return self.ve.textlength(text, font=self.dam if dam else self.thuong)


# ══════════════════════════════════════════════════════════════════════════
#  Sinh mã định danh
# ══════════════════════════════════════════════════════════════════════════
class MaSo:
    """Mã `_id` cho phần tử mới.

    StarUML không đòi định dạng gì, chỉ đòi duy nhất trong tệp; tiền tố
    DATNERD giúp nhận ra ngay phần nào do script sinh.
    """

    def __init__(self, da_dung: set[str]) -> None:
        self.da_dung = set(da_dung)
        self.dem = 0

    def __call__(self) -> str:
        while True:
            self.dem += 1
            ma = f"DATNERD{self.dem:05d}X="
            if ma not in self.da_dung:
                self.da_dung.add(ma)
                return ma


def moi_id(cay) -> set[str]:
    """Mọi `_id` đang có trong tệp, để mã mới không trùng."""
    ra: set[str] = set()
    goi = [cay]
    while goi:
        o = goi.pop()
        if isinstance(o, dict):
            if isinstance(o.get("_id"), str):
                ra.add(o["_id"])
            goi.extend(o.values())
        elif isinstance(o, list):
            goi.extend(o)
    return ra


# ══════════════════════════════════════════════════════════════════════════
#  Dựng mô hình
# ══════════════════════════════════════════════════════════════════════════
def dung_thuc_the(db: dict, id_model: str, ma: MaSo, ten_bang, ten_cot,
                  id_cu: dict[str, str]) -> tuple[list[dict], dict]:
    """Thực thể + cột. `ten_bang` / `ten_cot` quyết định dùng tên Anh hay Việt.

    Giữ `_id` cũ của thực thể đã có (chỉ bản tiếng Anh có) để tệp đỡ bị xáo
    hơn mức cần thiết.
    """
    thuc_the: list[dict] = []
    tra = {}
    for bang in [t for dong in HANG for t in dong]:
        eid = id_cu.get(bang) or ma()
        cols = []
        for c in db["cot"][bang]:
            col = {
                "_type": "ERDColumn",
                "_id": ma(),
                "_parent": {"$ref": eid},
                "name": ten_cot(bang, c["ten"]),
                "type": kieu_hien(c["kieu"]),
                "length": 0,
            }
            if (bang, c["ten"]) in db["pk"]:
                col["primaryKey"] = True
            if (bang, c["ten"]) in db["fk"]:
                col["foreignKey"] = True
            if (bang, c["ten"]) in db["uq"]:
                col["unique"] = True
            if c["null"]:
                col["nullable"] = True
            cols.append(col)

        e = {
            "_type": "ERDEntity",
            "_id": eid,
            "_parent": {"$ref": id_model},
            "name": ten_bang(bang),
            "columns": cols,
        }
        thuc_the.append(e)
        tra[bang] = e
    return thuc_the, tra


def dung_quan_he(db: dict, ma: MaSo, tra: dict) -> list[dict]:
    """Một ERDRelationship cho mỗi khóa ngoại, treo vào thực thể CHA.

    Giữ đúng quy ước của sơ đồ cũ: `end1` là phía cha (không ghi lượng số),
    `end2` là phía con với lượng số `0..*`. Hai khóa ngoại khác nhau trỏ
    cùng một cặp bảng vẫn là HAI quan hệ — `meal_plan_items` trỏ `foods`
    hai lần, qua `food_id` và `replaced_by_food_id`, và cả hai đều có nghĩa
    riêng nên phải vẽ cả hai.
    """
    ra: list[dict] = []
    for cha, con, cot_con in db["quan_he"]:
        e_cha, e_con = tra[cha], tra[con]
        rid = ma()
        r = {
            "_type": "ERDRelationship",
            "_id": rid,
            "_parent": {"$ref": e_cha["_id"]},
            "end1": {
                "_type": "ERDRelationshipEnd",
                "_id": ma(),
                "_parent": {"$ref": rid},
                "reference": {"$ref": e_cha["_id"]},
            },
            "end2": {
                "_type": "ERDRelationshipEnd",
                "_id": ma(),
                "_parent": {"$ref": rid},
                "reference": {"$ref": e_con["_id"]},
                "cardinality": "0..*",
            },
        }
        e_cha.setdefault("ownedElements", []).append(r)
        ra.append({"r": r, "cha": cha, "con": con, "cot": cot_con})
    return ra


def kiem_hang(quan_he: list[dict]) -> None:
    """Bảng cha phải ở hàng trên bảng con, nếu không thì cách đi đường sai."""
    o = {b: i for i, dong in enumerate(HANG) for b in dong}
    sai = [f"{q['cha']} -> {q['con']}" for q in quan_he
           if o[q["cha"]] >= o[q["con"]]]
    if sai:
        sys.exit("LỖI: bảng cha không nằm trên bảng con trong HANG: "
                 + ", ".join(sorted(set(sai))))


# ══════════════════════════════════════════════════════════════════════════
#  Bố cục xếp lớp
# ══════════════════════════════════════════════════════════════════════════
def dem_cat(tren: list, duoi: list, canh: list[tuple]) -> int:
    """Số cặp đường cắt nhau giữa hai hàng kề.

    Hai đường (a→b) và (c→d) cắt nhau khi thứ tự của chúng đảo chiều giữa
    hàng trên và hàng dưới. Đếm thẳng từng cặp: 29 quan hệ nên số cặp rất
    nhỏ, không cần thuật toán đếm nhanh.
    """
    vt_t = {n: i for i, n in enumerate(tren)}
    vt_d = {n: i for i, n in enumerate(duoi)}
    cap = [(vt_t[a], vt_d[b]) for a, b in canh]
    return sum(1 for i, (a, b) in enumerate(cap) for c, d in cap[i + 1:]
               if (a - c) * (b - d) < 0)


def dem_cat_hinh(quan_he: list[dict]) -> int:
    """Số chỗ hai đường thật sự cắt nhau trên hình vẽ.

    Khác với `dem_cat()`: hàm kia đếm theo THỨ TỰ các nút giữa hai hàng, là
    đại lượng mà bước sắp xếp tối ưu. Hàm này đếm trên các đoạn thẳng đã
    định vị, nên tính cả chỗ một đoạn đi ngang trong dải trống cắt qua một
    đoạn đi dọc — thứ chỉ xuất hiện sau khi đã có toạ độ. Đây mới là con số
    người đọc nhìn thấy.
    """
    doan = [(i, a, b) for i, qh in enumerate(quan_he)
            for a, b in zip(qh["points"], qh["points"][1:])]

    def cat(a1, a2, b1, b2) -> bool:
        if (a1[0] == a2[0]) == (b1[0] == b2[0]):
            return False                       # song song, không tính
        if b1[0] == b2[0]:                     # luôn để a dọc, b ngang
            a1, a2, b1, b2 = b1, b2, a1, a2
        return (min(a1[1], a2[1]) < b1[1] < max(a1[1], a2[1])
                and min(b1[0], b2[0]) < a1[0] < max(b1[0], b2[0]))

    return sum(1 for i, (k, a1, a2) in enumerate(doan)
               for k2, b1, b2 in doan[i + 1:]
               if k != k2 and cat(a1, a2, b1, b2))


class BoCuc:
    """Chia lớp, chèn nút ảo, sắp lại trong hàng, rồi tính toạ độ."""

    def __init__(self, tra: dict, quan_he: list[dict], thuoc: Thuoc,
                 tron: float = 0.5, kieu_lan: str = "trai") -> None:
        self.quan_he = quan_he
        self.tron = tron
        self.kieu_lan = kieu_lan
        self.lop = {b: i for i, dong in enumerate(HANG) for b in dong}

        # ── Kích thước hộp, tính từ chữ thật sẽ hiện trong hộp ──
        self.kich: dict = {}
        for bang, e in tra.items():
            rong = thuoc.rong(e["name"], dam=True)
            for c in e["columns"]:
                rong = max(rong, thuoc.rong(f"{c['name']}: {c['type']}"))
            self.kich[bang] = (max(RONG_TOI_THIEU, int(rong + DEM_CHU)),
                               CAO_NHAN + CAO_DONG * len(e["columns"])
                               + DEM_KHOANG)

        self._chuoi()
        self._sap_xep()
        self._dat_x()
        self._dat_y()
        self._duong()
        self.cat_hinh = dem_cat_hinh(quan_he)

    # ── Nút ảo ───────────────────────────────────────────────────────────
    def _chuoi(self) -> None:
        """Cắt quan hệ vượt nhiều hàng thành chuỗi chặng qua các nút ảo."""
        self.thu_tu = [list(dong) for dong in HANG]
        for k, qh in enumerate(self.quan_he):
            i, j = self.lop[qh["cha"]], self.lop[qh["con"]]
            chuoi = [qh["cha"]]
            for r in range(i + 1, j):
                ao = ("ao", k, r)
                self.kich[ao] = (RONG_NUT_AO, 0)
                self.thu_tu[r].append(ao)
                chuoi.append(ao)
            chuoi.append(qh["con"])
            qh["chuoi"] = chuoi

        # Danh sách cạnh của từng cặp hàng kề, dùng cho cả việc đếm cắt
        # nhau lẫn việc tính trọng tâm.
        self.canh: list[list[tuple]] = [[] for _ in range(len(HANG) - 1)]
        for qh in self.quan_he:
            i = self.lop[qh["cha"]]
            for n, (a, b) in enumerate(zip(qh["chuoi"], qh["chuoi"][1:])):
                self.canh[i + n].append((a, b))

    # ── Sắp lại trong hàng ───────────────────────────────────────────────
    def _trong_tam(self, dong: list, ke: list, canh: list[tuple],
                   xuoi: bool) -> list:
        """Xếp `dong` theo trọng tâm vị trí các nút nối với nó ở hàng `ke`."""
        vt = {n: i for i, n in enumerate(ke)}
        gom: dict = {}
        for a, b in canh:
            nut, kia = (b, a) if xuoi else (a, b)
            gom.setdefault(nut, []).append(vt[kia])
        # Nút không nối với hàng kề thì giữ nguyên chỗ cũ, nếu không nó sẽ
        # bị đẩy về đầu hàng và kéo theo cả loạt đường đi vòng.
        return sorted(dong, key=lambda n: (
            sum(gom[n]) / len(gom[n]) if n in gom else dong.index(n),
            dong.index(n),
        ))

    def _tong_cat(self, thu_tu: list[list]) -> int:
        return sum(dem_cat(thu_tu[i], thu_tu[i + 1], self.canh[i])
                   for i in range(len(self.canh)))

    def _sap_xep(self) -> None:
        tot = [list(d) for d in self.thu_tu]
        self.cat_dau = diem_tot = self._tong_cat(tot)
        hien = [list(d) for d in tot]

        for luot in range(SO_LUOT):
            if luot % 2 == 0:                      # quét xuôi, từ trên xuống
                for i in range(1, len(hien)):
                    hien[i] = self._trong_tam(hien[i], hien[i - 1],
                                              self.canh[i - 1], True)
            else:                                  # quét ngược, từ dưới lên
                for i in range(len(hien) - 2, -1, -1):
                    hien[i] = self._trong_tam(hien[i], hien[i + 1],
                                              self.canh[i], False)
            diem = self._tong_cat(hien)
            if diem < diem_tot:
                diem_tot, tot = diem, [list(d) for d in hien]

        self.thu_tu, self.so_cat = tot, diem_tot

    # ── Toạ độ ───────────────────────────────────────────────────────────
    def _muc_tieu(self, i: int) -> dict:
        """Tâm x mà mỗi nút ở hàng `i` muốn tới: trung bình tâm các nút kề."""
        ke: dict = {}
        if i > 0:
            for a, b in self.canh[i - 1]:
                ke.setdefault(b, []).append(self._tam(a))
        if i < len(self.canh):
            for a, b in self.canh[i]:
                ke.setdefault(a, []).append(self._tam(b))
        return {n: sum(v) / len(v) for n, v in ke.items()}

    def _tam(self, n) -> float:
        return self.x[n] + self.kich[n][0] / 2

    def _keo_hang(self, i: int) -> None:
        """Kéo từng nút của hàng `i` về gần tâm các nút nối với nó.

        Giữ nguyên THỨ TỰ đã tìm được ở bước trước và khe tối thiểu giữa hai
        hộp; chỉ co giãn khoảng cách. Bài toán là: tìm bộ x gần bộ đích nhất
        mà vẫn thoả `x[k+1] >= x[k] + w[k] + khe`.

        Đổi biến `y[k] = x[k] - (bề ngang và khe của mọi hộp đứng trước)` thì
        ràng buộc rút gọn thành "y không giảm", đúng bài hồi quy đơn điệu, và
        thuật toán PAVA cho nghiệm CHÍNH XÁC trong một lượt duyệt.

        Giải đúng chứ không nới dần từng lượt là có lý do: cách nới dần chỉ
        đẩy được về một phía, nên mỗi lượt cả hàng trôi thêm một ít và sơ đồ
        phình ra tới hơn 21.000 px.
        """
        dong = self.thu_tu[i]
        muc = self._muc_tieu(i)
        w = [self.kich[n][0] for n in dong]
        # Nút không nối với hàng kề thì lấy chính chỗ nó đang đứng làm đích,
        # nhờ vậy nó neo lại chứ không bị cả hàng kéo đi.
        dich = [muc[n] - w[k] / 2 if n in muc else float(self.x[n])
                for k, n in enumerate(dong)]

        truoc, t = 0.0, []
        for k in range(len(dong)):
            t.append(dich[k] - truoc)
            truoc += w[k] + KHE_NGANG

        khoi: list[list[float]] = []          # [tổng, số phần tử]
        for v in t:
            khoi.append([v, 1])
            while (len(khoi) >= 2
                   and khoi[-2][0] / khoi[-2][1] > khoi[-1][0] / khoi[-1][1]):
                a, b = khoi.pop(), khoi.pop()
                khoi.append([a[0] + b[0], a[1] + b[1]])
        y = [s / c for s, c in khoi for _ in range(int(c))]

        truoc = 0.0
        for k, n in enumerate(dong):
            self.x[n] = int(round(y[k] + truoc))
            truoc += w[k] + KHE_NGANG

    def _dat_x(self) -> None:
        # Bước 1 — xếp khít theo thứ tự, mỗi hàng căn giữa. Đây là phương án
        # HẸP NHẤT có thể với thứ tự này.
        be = [sum(self.kich[n][0] for n in d) + KHE_NGANG * (len(d) - 1)
              for d in self.thu_tu]
        rong_nhat = max(be)
        self.x: dict = {}
        for dong, b in zip(self.thu_tu, be):
            x = LE + (rong_nhat - b) // 2
            for n in dong:
                self.x[n] = x
                x += self.kich[n][0] + KHE_NGANG
        khit = dict(self.x)

        # Bước 2 — nới theo trọng tâm. Đây là thứ làm đoạn đi ngang ngắn lại:
        # xếp khít thì một bảng con có thể nằm cách bảng cha cả nghìn px dù
        # thứ tự đã đúng, và đoạn ngang dài ấy cắt qua mọi đường đi dọc trên
        # đường của nó. Nút ảo chỉ nối với chặng trước và chặng sau nên bị kéo
        # thẳng hàng, biến quan hệ vượt nhiều hàng thành một đường dọc liền.
        for luot in range(SO_LUOT_X):
            thu = range(len(self.thu_tu))
            for i in (thu if luot % 2 == 0 else reversed(thu)):
                self._keo_hang(i)

        # Bước 3 — pha trộn hai phương án. Nới hết cỡ thì đường thẳng đẹp
        # nhưng sơ đồ rộng gấp rưỡi, xếp khít thì ngược lại.
        #
        # Trộn được là vì mọi ràng buộc đều có dạng `x[k+1] - x[k] >= hằng`:
        # tổ hợp lồi của hai nghiệm hợp lệ thì vẫn hợp lệ, nên không cần kiểm
        # lại khe giữa các hộp.
        for n in self.x:
            self.x[n] = int(round(self.tron * self.x[n]
                                  + (1 - self.tron) * khit[n]))

        # Bước 4 — dời cả sơ đồ về sát lề trái.
        lech = min(self.x.values()) - LE
        for n in self.x:
            self.x[n] -= lech
        self.rong = LE + max(self.x[n] + self.kich[n][0] for n in self.x)

    def _lan(self) -> None:
        """Xếp làn cho các đoạn đi ngang trong từng dải trống.

        Hai đoạn không đè lên nhau theo chiều ngang thì dùng chung một làn.
        Xếp kiểu tham lam theo mép trái, đúng bài toán tô màu đồ thị khoảng
        cách, cho số làn ít nhất có thể — dải chỉ cao vừa đủ.
        """
        self.doan: list[dict] = [{} for _ in self.canh]
        for qh in self.quan_he:
            i = self.lop[qh["cha"]]
            moc = [self._cong(qh, 0)[0]] \
                + [self.x[n] for n in qh["chuoi"][1:-1]] \
                + [self._cong(qh, 1)[0]]
            for n, (a, b) in enumerate(zip(moc, moc[1:])):
                self.doan[i + n][id(qh)] = (min(a, b), max(a, b))

        # Thứ tự xét quyết định đoạn nào được làn trên, làn dưới. Không có
        # cách xếp nào tối ưu hiển nhiên — số chỗ cắt phụ thuộc cả vào các
        # đoạn đi dọc — nên thử vài kiểu rồi đo bằng `dem_cat_hinh()` và giữ
        # kiểu cho ít chỗ cắt nhất.
        khoa_sap = {
            "trai": lambda t: (t[1][0], t[1][1]),
            "phai": lambda t: (t[1][1], t[1][0]),
            "dai": lambda t: (t[1][0] - t[1][1], t[1][0]),
        }[self.kieu_lan.removesuffix("_nguoc")]

        self.lan: dict = {}
        self.so_lan = []
        for b, ds in enumerate(self.doan):
            het: list[int] = []
            for khoa, (l, r) in sorted(ds.items(), key=khoa_sap):
                for k, x in enumerate(het):
                    if x < l:
                        het[k] = r
                        self.lan[(khoa, b)] = k
                        break
                else:
                    het.append(r)
                    self.lan[(khoa, b)] = len(het) - 1
            n = max(1, len(het))
            if self.kieu_lan.endswith("_nguoc"):
                for khoa in ds:
                    self.lan[(khoa, b)] = n - 1 - self.lan[(khoa, b)]
            self.so_lan.append(n)

    def _dat_y(self) -> None:
        self._lan()
        self.y: dict = {}
        self.dai: list[tuple[int, int]] = []      # (đỉnh, bề cao) của mỗi dải
        y = LE
        for i, dong in enumerate(self.thu_tu):
            cao = max(self.kich[n][1] for n in dong)
            for n in dong:
                # Hộp thấp hơn hàng thì căn giữa: phía trên và phía dưới nó
                # còn chỗ trống cho đoạn nối đi ra mà không chạm hộp nào.
                self.y[n] = y + (cao - self.kich[n][1]) // 2
            if i < len(self.canh):
                b_cao = max(KHE_DOC, (self.so_lan[i] + 1) * CACH_LAN)
                self.dai.append((y + cao, b_cao))
                y += cao + b_cao
            else:
                self.cao = y + cao + LE

    def hop(self) -> dict:
        return {b: (self.x[b], self.y[b], self.kich[b][0], self.kich[b][1])
                for b in self.kich if not isinstance(b, tuple)}

    # ── Điểm nối và đường đi ─────────────────────────────────────────────
    def _cong(self, qh: dict, ben: int) -> tuple[int, int]:
        """Điểm nối của quan hệ trên viền hộp cha (ben=0) hay hộp con (1).

        `_dat_y` cần biết các đoạn đi ngang nằm ở đâu để tính số làn, mà số
        làn lại quyết định bề cao dải trống, còn điểm nối thì chưa tính được
        vì nó chỉ phụ thuộc x. Nên lượt đầu lấy tạm TÂM hộp; `_duong` gọi
        lại `_lan()` sau khi đã chốt điểm nối. Bề cao dải không đổi nữa,
        nhưng làn luôn chia theo đúng bề dải đó nên không bao giờ tràn ra
        ngoài.
        """
        if not hasattr(self, "_diem"):
            bang = qh["cha"] if ben == 0 else qh["con"]
            return (self.x[bang] + self.kich[bang][0] // 2, 0)
        return self._diem[(id(qh), ben)]

    def _tinh_cong(self) -> None:
        """Rải điểm nối đều trên đáy hộp cha và đỉnh hộp con.

        Sắp theo vị trí của chặng kế tiếp, để các đường ra khỏi một hộp
        không bắt chéo nhau ngay tại viền — `users` có 11 bảng con, chụm
        một điểm thì 11 đường chồng lên nhau thành một.
        """
        cho: dict = {}
        for qh in self.quan_he:
            cho.setdefault((qh["cha"], "d"), []).append(
                (self.x[qh["chuoi"][1]], qh, 0))
            cho.setdefault((qh["con"], "t"), []).append(
                (self.x[qh["chuoi"][-2]], qh, 1))

        self._diem = {}
        for (bang, phia), ds in cho.items():
            ds.sort(key=lambda t: t[0])
            x, y = self.x[bang], self.y[bang]
            w, h = self.kich[bang]
            for i, (_, qh, ben) in enumerate(ds):
                self._diem[(id(qh), ben)] = (
                    int(x + w * (i + 1) / (len(ds) + 1)),
                    y + h if phia == "d" else y,
                )

    def _duong(self) -> None:
        """Đường vuông góc: ra đáy hộp cha, qua các làn và nút ảo, vào đỉnh
        hộp con."""
        self._tinh_cong()
        self._lan()                               # tính lại với cổng đã chốt

        for qh in self.quan_he:
            i = self.lop[qh["cha"]]
            p, q = self._cong(qh, 0), self._cong(qh, 1)
            moc = [self.x[n] for n in qh["chuoi"][1:-1]] + [q[0]]

            pts = [p]
            x_hien = p[0]
            for n, mx in enumerate(moc):
                y0, bc = self.dai[i + n]
                k = self.lan[(id(qh), i + n)]
                ly = int(y0 + bc * (k + 1) / (self.so_lan[i + n] + 1))
                pts.append((x_hien, ly))
                pts.append((mx, ly))
                x_hien = mx
            pts.append(q)
            qh["points"] = [pt for k, pt in enumerate(pts)
                            if k == 0 or pt != pts[k - 1]]

    def ap_dung(self) -> None:
        """Ghi lại đường đi của phương án này vào `quan_he`.

        Mỗi lần dựng thử một phương án là một lần ghi đè `points` của các
        quan hệ. Sau khi thử hết phải gọi lại hàm này trên phương án được
        chọn, nếu không sơ đồ mang đường đi của phương án thử CUỐI CÙNG
        trong khi hộp lại nằm theo phương án tốt nhất.
        """
        self._duong()


# ══════════════════════════════════════════════════════════════════════════
#  Dựng khung nhìn
# ══════════════════════════════════════════════════════════════════════════
def dung_view(tra: dict, bc: BoCuc, quan_he: list[dict], id_dia: str,
              ma: MaSo) -> list[dict]:
    views: list[dict] = []
    id_view: dict[str, str] = {}
    hop = bc.hop()

    for bang, e in tra.items():
        x, y, w, h = hop[bang]
        vid = ma()
        id_view[bang] = vid

        nhan = {
            "_type": "LabelView",
            "_id": ma(),
            "_parent": {"$ref": vid},
            "font": "Arial;13;1",
            "left": x,
            "top": y + 5,
            "width": w,
            "height": 13,
            "text": e["name"],
        }
        khoang_id = ma()
        cot_view = []
        for i, c in enumerate(e["columns"]):
            cot_view.append({
                "_type": "ERDColumnView",
                "_id": ma(),
                "_parent": {"$ref": khoang_id},
                "model": {"$ref": c["_id"]},
                "font": "Arial;13;0",
                "left": x + 5,
                "top": y + CAO_NHAN + 5 + CAO_DONG * i,
                "width": w - 10,
                "height": 13,
            })
        khoang = {
            "_type": "ERDColumnCompartmentView",
            "_id": khoang_id,
            "_parent": {"$ref": vid},
            "model": {"$ref": e["_id"]},
            "subViews": cot_view,
            "font": "Arial;13;0",
            "left": x,
            "top": y + CAO_NHAN,
            "width": w,
            "height": CAO_DONG * len(e["columns"]) + DEM_KHOANG,
        }
        views.append({
            "_type": "ERDEntityView",
            "_id": vid,
            "_parent": {"$ref": id_dia},
            "model": {"$ref": e["_id"]},
            "subViews": [nhan, khoang],
            "font": "Arial;13;0",
            "left": x,
            "top": y,
            "width": w,
            "height": h,
            "nameLabel": {"$ref": nhan["_id"]},
            "columnCompartment": {"$ref": khoang_id},
        })

    for qh in quan_he:
        vid = ma()
        pts = qh["points"]
        gx = sum(p[0] for p in pts) // len(pts)
        gy = sum(p[1] for p in pts) // len(pts)

        # Ba nhãn cạnh là bắt buộc: StarUML trỏ nameLabel / tailNameLabel /
        # headNameLabel vào chúng, thiếu một cái là tệp mở ra lỗi.
        #
        # `edgePosition` theo đúng hằng số của StarUML: HEAD = 0, MIDDLE = 1,
        # TAIL = 2. Nhãn phía đầu mang giá trị 0 nên KHÔNG ghi ra, y như
        # cách StarUML tự ghi tệp. Đánh lệch bộ ba này thì ba nhãn đổi chỗ
        # cho nhau và lượng số `0..*` hiện sai đầu.
        nhan = []
        for alpha, kc, vi_tri_nhan, hien in (
            (1.5707963267948966, 15, 1, False),   # tên quan hệ, để ẩn
            (0.5235987755982988, 30, 2, True),    # phía cha
            (-0.5235987755982988, 30, 0, True),   # phía con
        ):
            lv = {
                "_type": "EdgeLabelView",
                "_id": ma(),
                "_parent": {"$ref": vid},
                "font": "Arial;13;0",
                "left": gx,
                "top": gy,
                "height": 13,
                "alpha": alpha,
                "distance": kc,
                "hostEdge": {"$ref": vid},
            }
            if not hien:
                lv["visible"] = False
            if vi_tri_nhan:
                lv["edgePosition"] = vi_tri_nhan
            nhan.append(lv)

        views.append({
            "_type": "ERDRelationshipView",
            "_id": vid,
            "_parent": {"$ref": id_dia},
            "model": {"$ref": qh["r"]["_id"]},
            "subViews": nhan,
            "font": "Arial;13;0",
            "head": {"$ref": id_view[qh["con"]]},
            "tail": {"$ref": id_view[qh["cha"]]},
            "lineStyle": 2,
            "points": ";".join(f"{x}:{y}" for x, y in pts),
            "nameLabel": {"$ref": nhan[0]["_id"]},
            "tailNameLabel": {"$ref": nhan[1]["_id"]},
            "headNameLabel": {"$ref": nhan[2]["_id"]},
        })

    return views


# ══════════════════════════════════════════════════════════════════════════
#  Kiểm tra
# ══════════════════════════════════════════════════════════════════════════
def kiem_bo_cuc(quan_he: list[dict], hop: dict, nhan: str) -> None:
    """Không hộp nào đè nhau, không đoạn nối nào xuyên qua lòng một hộp.

    Phép kiểm thứ hai quan trọng hơn: hộp đè nhau thì nhìn ra ngay, còn một
    đường kẻ chui qua giữa bảng `foods` rất dễ lọt vào bản in.
    """
    de = []
    ten = sorted(hop)
    for i, a in enumerate(ten):
        for b in ten[i + 1:]:
            ax, ay, aw, ah = hop[a]
            bx, by, bw, bh = hop[b]
            if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
                de.append(f"{a} ↔ {b}")
    if de:
        sys.exit(f"LỖI [{nhan}]: {len(de)} cặp hộp đè nhau: {de[:5]}")

    cat = []
    for qh in quan_he:
        pts = qh["points"]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            lo_x, hi_x = min(x1, x2), max(x1, x2)
            lo_y, hi_y = min(y1, y2), max(y1, y2)
            for bang, (bx, by, bw, bh) in hop.items():
                if bang in (qh["cha"], qh["con"]):
                    continue
                if (lo_x < bx + bw - 1 and hi_x > bx + 1
                        and lo_y < by + bh - 1 and hi_y > by + 1):
                    cat.append(f"{qh['cha']}->{qh['con']} xuyên {bang}")
    if cat:
        sys.exit(f"LỖI [{nhan}]: {len(cat)} đoạn nối cắt qua hộp: {cat[:5]}")

    print(f"   ✓ [{nhan}] {len(hop)} hộp không đè nhau, "
          f"{len(quan_he)} đường nối không cắt qua hộp")


def kiem_ref(goc: dict) -> None:
    """Mọi `$ref` phải trỏ tới một `_id` có thật trong tệp."""
    co: set[str] = set()
    ref: list[str] = []
    goi = [goc]
    while goi:
        o = goi.pop()
        if isinstance(o, dict):
            if isinstance(o.get("_id"), str):
                co.add(o["_id"])
            if set(o) == {"$ref"}:
                ref.append(o["$ref"])
            else:
                goi.extend(o.values())
        elif isinstance(o, list):
            goi.extend(o)

    treo = sorted({r for r in ref if r not in co})
    if treo:
        sys.exit(f"LỖI: {len(treo)} tham chiếu trỏ vào hư không: {treo[:5]}")
    print(f"   ✓ {len(ref)} tham chiếu đều trỏ tới phần tử có thật, "
          f"{len(co)} phần tử")


# ══════════════════════════════════════════════════════════════════════════
def dung_mot_so_do(db: dict, ma: MaSo, id_model: str, ten_bang, ten_cot,
                   id_dia: str, id_cu: dict, thuoc: Thuoc, nhan: str):
    """Dựng trọn một mô hình ERD: thực thể, quan hệ, bố cục, khung nhìn."""
    thuc_the, tra = dung_thuc_the(db, id_model, ma, ten_bang, ten_cot, id_cu)
    quan_he = dung_quan_he(db, ma, tra)
    kiem_hang(quan_he)

    bc = None
    for tron in THU_TRON:
        for kieu in THU_LAN:
            thu = BoCuc(tra, quan_he, thuoc, tron, kieu)
            diem = thu.cat_hinh + thu.rong / PHAT_RONG
            if bc is None or diem < bc[0]:
                bc = (diem, thu)
    bc = bc[1]
    bc.ap_dung()                      # dựng lại phương án tốt nhất

    views = dung_view(tra, bc, quan_he, id_dia, ma)
    print(f"   {nhan}: {bc.rong} × {bc.cao} px · "
          f"cặp đảo thứ tự {bc.cat_dau} -> {bc.so_cat} · "
          f"chỗ cắt trên hình {bc.cat_hinh} · "
          f"tron={bc.tron} lan={bc.kieu_lan}")
    kiem_bo_cuc(quan_he, bc.hop(), nhan)
    return thuc_the, quan_he, views



def _in_utf8() -> None:
    """Bắt stdout nhận tiếng Việt trên Windows (mặc định cp1252).

    Không gọi thì script chết giữa lúc chạy với UnicodeEncodeError ngay khi
    đầu ra bị chuyển hướng qua ống hoặc vào tệp — tức đúng lúc chạy trong CI.
    Bản sao của `tools/_env.in_utf8`; để ở đây vì `tools/baocao/` không chắc
    có `tools/` trên `sys.path`.
    """
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover
            pass

def main() -> int:
    _in_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="chỉ in những gì sẽ đổi, không ghi tệp")
    args = ap.parse_args()

    if not MDJ.exists():
        sys.exit(f"Không thấy {MDJ}")

    goc = json.loads(MDJ.read_text(encoding="utf-8"))
    erd = next(e for e in goc["ownedElements"]
               if e["_type"] == "ERDDataModel" and e["name"] != TEN_MODEL_VI)
    dia = next(e for e in erd["ownedElements"]
               if e["_type"] == "ERDDiagram")
    id_cu = {e["name"].strip().lower(): e["_id"]
             for e in erd["ownedElements"] if e["_type"] == "ERDEntity"}

    db = doc_csdl()
    da_xep = [b for g in HANG for b in g]
    thieu = [t for t in db["cot"] if t not in da_xep]
    if thieu:
        sys.exit(f"CSDL có bảng chưa xếp vào HANG: {thieu}")
    thua = [b for b in da_xep if b not in db["cot"]]
    if thua or len(da_xep) != len(set(da_xep)):
        sys.exit(f"HANG có bảng không còn trong CSDL hoặc bị lặp: {thua}")

    so_cot = sum(len(v) for v in db["cot"].values())
    enum = [c["kieu"] for cs in db["cot"].values() for c in cs
            if c["kieu"].startswith(("enum", "set"))]
    print(f"CSDL {DB_NAME}: {len(db['cot'])} bảng, {so_cot} cột, "
          f"{len(db['quan_he'])} khóa ngoại, {len(enum)} cột ENUM/SET "
          f"({sum(t.count(NHAY) // 2 for t in enum)} giá trị)\n")

    cu_vi = next((e for e in goc["ownedElements"]
                  if e["_type"] == "ERDDataModel"
                  and e["name"] == TEN_MODEL_VI), None)

    # Mã mới chỉ cần tránh trùng với những nhánh ĐƯỢC GIỮ LẠI. Nếu gom cả mã
    # của hai nhánh ERD sắp bị thay thì mỗi lần chạy lại bộ đếm phải nhảy
    # qua loạt mã cũ, và toàn bộ mã trong tệp đổi hết sau mỗi lần chạy —
    # `git diff` lần nào cũng đỏ cả tệp dù nội dung y nguyên.
    giu = [e for e in goc["ownedElements"] if e is not erd and e is not cu_vi]
    ma = MaSo(moi_id(giu) | set(id_cu.values())
              | {erd["_id"], dia["_id"], ID_PROJECT})

    # ── Bản tiếng Anh: thay nội dung mô hình ERD đang có ──
    tt_en, qh_en, view_en = dung_mot_so_do(
        db, ma, erd["_id"], lambda b: b, lambda b, c: c,
        dia["_id"], id_cu, Thuoc(), "ERD")

    # ── Bản tiếng Việt: một mô hình riêng trong cùng tệp ──
    # Phải là mô hình RIÊNG chứ không phải sơ đồ thứ hai của cùng mô hình:
    # hai sơ đồ chung một mô hình thì dùng chung luôn thực thể, nên không
    # thể đặt hai bộ tên khác nhau.
    id_vi = cu_vi["_id"] if cu_vi else ma()
    dia_vi = {
        "_type": "ERDDiagram",
        "_id": (next(x["_id"] for x in cu_vi["ownedElements"]
                     if x["_type"] == "ERDDiagram") if cu_vi else ma()),
        "_parent": {"$ref": id_vi},
        "name": TEN_DIAGRAM_VI,
    }
    tt_vi, qh_vi, view_vi = dung_mot_so_do(
        db, ma, id_vi, lambda b: BANG[b][0], lambda b, c: COT[b][c],
        dia_vi["_id"], {}, Thuoc(), TEN_MODEL_VI)

    # ── Ghép vào cây, giữ nguyên nhánh Model và UseCase ──
    erd["ownedElements"] = [dia] + tt_en
    dia["ownedViews"] = view_en
    dia_vi["ownedViews"] = view_vi
    model_vi = {
        "_type": "ERDDataModel",
        "_id": id_vi,
        "_parent": {"$ref": ID_PROJECT},
        "name": TEN_MODEL_VI,
        "ownedElements": [dia_vi] + tt_vi,
    }
    if cu_vi:
        goc["ownedElements"][goc["ownedElements"].index(cu_vi)] = model_vi
    else:
        goc["ownedElements"].append(model_vi)

    print()
    kiem_ref(goc)

    if args.dry_run:
        print("\n--dry-run: không ghi tệp.")
        return 0

    sao_luu = MDJ.with_suffix(".mdj.bak_erd")
    if not sao_luu.exists():
        shutil.copy2(MDJ, sao_luu)
        print(f"   Đã sao lưu -> {sao_luu.name}")

    # StarUML ghi tệp này thụt bằng tab; giữ đúng vậy để `git diff` sau này
    # chỉ hiện phần nội dung thay đổi, không hiện cả tệp bị định dạng lại.
    MDJ.write_text(
        json.dumps(goc, ensure_ascii=False, indent="\t"), encoding="utf-8"
    )
    print(f"\nĐã ghi {MDJ.relative_to(ROOT)} — hai sơ đồ: "
          f"'{erd['name'].strip()}' và '{TEN_MODEL_VI}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
