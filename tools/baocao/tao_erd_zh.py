#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sinh mô hình `ERD 中文` trong BAOCAO/Diagram.mdj từ mô hình ERD gốc.

    users            ->  用户
    health_profiles  ->  健康档案
    password_hash    ->  密码哈希

Tên tiếng Trung lấy từ `erd_zh.py`.

NHÂN BẢN, KHÔNG SỬA BẢN GỐC. Mô hình `ERD` (tiếng Anh) được chép sâu thành
một mô hình mới, mọi `_id` trong bản chép được cấp lại và mọi `$ref` trỏ
trong nội bộ được nối sang `_id` mới — nên hai mô hình độc lập hẳn, sửa bên
này không kéo theo bên kia. Ba mô hình `ERD`, `ERD tiếng Việt`, `ERD_vi`
được ghi lại nguyên văn.

CHỈ ĐỔI TÊN. Kiểu dữ liệu, cờ khóa, quan hệ, vị trí hộp giữ nguyên. Bề
ngang hộp chỉ nới ra khi tên mới dài hơn chỗ đang có.

Chạy lại được nhiều lần: nếu đã có `ERD 中文` thì thay bằng bản sinh mới.

Chạy:
    python tools/baocao/tao_erd_zh.py
    python tools/baocao/tao_erd_zh.py --dry-run
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from erd_zh import BANG, COT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
MDJ = ROOT / "BAOCAO" / "Diagram.mdj"
TEN_GOC = "ERD"
TEN_MO_HINH = "ERD 中文"
TEN_DIAGRAM = "ERDDiagram_ZH"

# Arial không có chữ Hán; StarUML vẽ bằng phông dự phòng của Windows, gần
# với Microsoft YaHei. Đo bằng phông đó để biết chữ có tràn hộp không.
FONT_FILE = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_SIZE = 13
DEM_CHU = 24          # chừa tối thiểu hai bên chữ trong hộp


def id_moi(da_dung: set[str]) -> str:
    """`_id` kiểu StarUML: base64 của 14 byte ngẫu nhiên, không trùng."""
    while True:
        s = base64.b64encode(os.urandom(14)).decode()
        if s not in da_dung:
            da_dung.add(s)
            return s


def gom_id(o, ra: set[str]) -> None:
    if isinstance(o, dict):
        if "_id" in o:
            ra.add(o["_id"])
        for v in o.values():
            gom_id(v, ra)
    elif isinstance(o, list):
        for v in o:
            gom_id(v, ra)


def doi_id(o, bang: dict[str, str]) -> None:
    """Thay `_id` và `$ref` theo bảng ánh xạ cũ -> mới, tại chỗ."""
    if isinstance(o, dict):
        if "_id" in o:
            o["_id"] = bang[o["_id"]]
        if "$ref" in o and o["$ref"] in bang:
            o["$ref"] = bang[o["$ref"]]
        for v in o.values():
            doi_id(v, bang)
    elif isinstance(o, list):
        for v in o:
            doi_id(v, bang)


class Thuoc:
    """Đo bề rộng chữ bằng phông có chữ Hán."""

    def __init__(self) -> None:
        self.ve = None
        try:
            from PIL import Image, ImageDraw, ImageFont

            self.thuong = ImageFont.truetype(FONT_FILE, FONT_SIZE)
            self.dam = ImageFont.truetype(FONT_BOLD, FONT_SIZE)
            self.ve = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        except Exception as loi:                       # noqa: BLE001
            print(f"  (không đo được chữ: {loi} — bỏ qua bước kiểm bề ngang)")

    def rong(self, text: str, dam: bool = False) -> float:
        if self.ve is None:
            return 0.0
        return self.ve.textlength(text, font=self.dam if dam else self.thuong)



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
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not MDJ.exists():
        sys.exit(f"Không thấy {MDJ}")
    goc = json.loads(MDJ.read_text(encoding="utf-8"))

    mo_hinh = [e for e in goc["ownedElements"]
               if e["_type"] == "ERDDataModel"]
    nguon = next((e for e in mo_hinh if e["name"].strip() == TEN_GOC), None)
    if nguon is None:
        sys.exit(f"Không thấy mô hình {TEN_GOC!r}. Đang có: "
                 + ", ".join(repr(e["name"]) for e in mo_hinh))

    # ── Kiểm từ điển đủ và không trùng tên ──
    if len(set(BANG.values())) != len(BANG):
        sys.exit("Có tên bảng tiếng Trung trùng nhau")
    for b, ds in COT.items():
        if len(set(ds.values())) != len(ds):
            sys.exit(f"{b} có cột tiếng Trung trùng tên")

    # ── Chép sâu, cấp lại toàn bộ _id ──
    m = copy.deepcopy(nguon)
    da_dung: set[str] = set()
    gom_id(goc, da_dung)
    cu: set[str] = set()
    gom_id(m, cu)
    doi_id(m, {i: id_moi(da_dung) for i in cu})
    m["name"] = TEN_MO_HINH

    thuc_the = [e for e in m["ownedElements"] if e["_type"] == "ERDEntity"]
    dia = next(e for e in m["ownedElements"] if e["_type"] == "ERDDiagram")
    dia["name"] = TEN_DIAGRAM
    dia.pop("defaultDiagram", None)

    # ── Đổi tên ──
    doi_cot = 0
    for e in thuc_the:
        b = e["name"]
        if b not in BANG:
            sys.exit(f"Chưa có tên tiếng Trung cho bảng: {b}")
        for c in e.get("columns", []):
            if c.get("name") not in COT[b]:
                sys.exit(f"Chưa có tên tiếng Trung cho {b}.{c.get('name')}")
            c["name"] = COT[b][c["name"]]
            doi_cot += 1
        e["name"] = BANG[b]

    # Nhãn tên hộp giữ một bản sao của tên trong `text`, phải đổi theo.
    ten_theo_id = {e["_id"]: e["name"] for e in thuc_the}
    doi_nhan = 0
    for v in dia["ownedViews"]:
        if v["_type"] != "ERDEntityView":
            continue
        for sv in v.get("subViews", []):
            if sv["_type"] == "LabelView":
                sv["text"] = ten_theo_id[v["model"]["$ref"]]
                doi_nhan += 1

    print(f"{TEN_MO_HINH}: đổi {len(thuc_the)} tên bảng, {doi_cot} tên cột, "
          f"{doi_nhan} nhãn trên sơ đồ")

    # ── Kiểm bề ngang ──
    thuoc = Thuoc()
    noi = {e["_id"]: e for e in thuc_the}
    da_noi = []
    if thuoc.ve is not None:
        for v in dia["ownedViews"]:
            if v["_type"] != "ERDEntityView":
                continue
            e = noi[v["model"]["$ref"]]
            can = thuoc.rong(e["name"], dam=True)
            for c in e["columns"]:
                can = max(can, thuoc.rong(f"{c['name']}: {c['type']}"))
            can = int(can + DEM_CHU)
            if can > v["width"]:
                da_noi.append((e["name"], round(v["width"]), can))
                them = can - v["width"]
                v["width"] = can
                for sv in v["subViews"]:
                    sv["width"] = sv["width"] + them
                    for cv in sv.get("subViews", []):
                        cv["width"] = cv["width"] + them
    if da_noi:
        print(f"   nới {len(da_noi)} hộp cho vừa chữ:")
        for ten, cu_w, moi in da_noi:
            print(f"      {ten}: {cu_w} -> {moi} px")
    else:
        print("   ✓ không hộp nào phải nới — tên mới vừa chỗ cũ")

    # ── Gắn vào tệp: thay bản cũ nếu đã có, không thì thêm vào cuối ──
    ds = goc["ownedElements"]
    vi_tri = next((i for i, e in enumerate(ds)
                   if e["_type"] == "ERDDataModel"
                   and e["name"].strip() == TEN_MO_HINH), None)
    if vi_tri is None:
        ds.append(m)
    else:
        ds[vi_tri] = m
        print(f"   thay mô hình {TEN_MO_HINH!r} đã có")
    for e in mo_hinh:
        if e["name"].strip() != TEN_MO_HINH:
            print(f"   giữ nguyên mô hình {e['name'].strip()!r}")

    if args.dry_run:
        print("\n--dry-run: không ghi tệp.")
        return 0

    sao_luu = MDJ.with_suffix(".mdj.bak_zh")
    if not sao_luu.exists():
        shutil.copy2(MDJ, sao_luu)
        print(f"   Đã sao lưu -> {sao_luu.name}")

    MDJ.write_text(json.dumps(goc, ensure_ascii=False, indent="\t"),
                   encoding="utf-8")
    print(f"\nĐã ghi {MDJ.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
