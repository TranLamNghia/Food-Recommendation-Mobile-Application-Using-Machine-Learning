#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Đổi tên bảng và cột của mô hình `ERD_vi` sang tiếng Việt KHÔNG DẤU.

    users            ->  nguoiDung
    health_profiles  ->  hoSoSucKhoe
    password_hash    ->  maBamMatKhau

Tên tiếng Việt lấy từ `erd_vi.py` rồi bỏ dấu: đó cũng là bộ tên dùng cho
`docs/ERD_TIENG_VIET.md`, nên hai tài liệu không thể gọi khác nhau. Bỏ dấu vì
yêu cầu của môn là tên thực thể và tên thuộc tính không có dấu tiếng Việt.

CHỈ ĐỘNG VÀO MÔ HÌNH `ERD_vi`. Hai mô hình `ERD` và `ERD tiếng Việt` trong
cùng tệp được ghi lại nguyên văn, kể cả toạ độ hộp và đường nối.

CHỈ ĐỔI TÊN. Kiểu dữ liệu, cờ khóa, quan hệ, vị trí hộp giữ nguyên hết — bố
cục bạn đã chỉnh tay không bị đụng tới. Bề ngang hộp chỉ nới ra khi tên mới
dài hơn chỗ đang có, và script báo rõ hộp nào bị nới bao nhiêu.

Chạy lại được nhiều lần: tên đã đổi rồi thì nhận ra và bỏ qua.

Chạy:
    python tools/baocao/doi_ten_erd_vi.py
    python tools/baocao/doi_ten_erd_vi.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from erd_vi import BANG, COT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
MDJ = ROOT / "BAOCAO" / "Diagram.mdj"
TEN_MO_HINH = "ERD_vi"

FONT_FILE = r"C:\Windows\Fonts\arial.ttf"
FONT_BOLD = r"C:\Windows\Fonts\arialbd.ttf"
FONT_SIZE = 13
DEM_CHU = 24          # chừa tối thiểu hai bên chữ trong hộp
CAO_DONG = 15         # bề cao một dòng cột, đúng bước StarUML dùng


def bo_dau(s: str) -> str:
    """Bỏ dấu tiếng Việt, giữ nguyên kiểu viết hoa thường.

    Tách ký tự thành chữ gốc + dấu rồi bỏ phần dấu. Chữ `đ` và `Đ` không tách
    được theo cách đó — chúng là chữ cái riêng chứ không phải `d` có dấu —
    nên phải đổi tay trước.
    """
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if not unicodedata.combining(c))


class Thuoc:
    """Đo bề rộng chữ bằng chính phông StarUML dùng (Arial 13)."""

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
    m = next((e for e in mo_hinh if e["name"].strip() == TEN_MO_HINH), None)
    if m is None:
        sys.exit(f"Không thấy mô hình {TEN_MO_HINH!r}. Đang có: "
                 + ", ".join(repr(e["name"]) for e in mo_hinh))

    # ── Bộ tên không dấu, dựng từ chính từ điển của ERD_TIENG_VIET.md ──
    ten_bang = {k: bo_dau(v[0]) for k, v in BANG.items()}
    ten_cot = {b: {c: bo_dau(v) for c, v in ds.items()}
               for b, ds in COT.items()}

    trung = [v for v in set(ten_bang.values())
             if list(ten_bang.values()).count(v) > 1]
    if trung:
        sys.exit(f"Bỏ dấu xong có tên bảng trùng nhau: {trung}")
    for b, ds in ten_cot.items():
        t = [v for v in set(ds.values()) if list(ds.values()).count(v) > 1]
        if t:
            sys.exit(f"Bỏ dấu xong {b} có cột trùng tên: {t}")

    thuc_the = [e for e in m["ownedElements"] if e["_type"] == "ERDEntity"]
    dia = next(e for e in m["ownedElements"] if e["_type"] == "ERDDiagram")

    # Nhận ra lần chạy lại: tên đã là tên không dấu rồi.
    da_doi = {e["name"] for e in thuc_the} <= set(ten_bang.values())
    if da_doi:
        print(f"{TEN_MO_HINH} đã mang tên tiếng Việt không dấu — không đổi "
              f"gì thêm.")
        return 0

    thieu = [e["name"] for e in thuc_the if e["name"] not in ten_bang]
    if thieu:
        sys.exit(f"Chưa có tên tiếng Việt cho bảng: {thieu}")

    # ── Gỡ cột đã bị xóa khỏi CSDL ──
    # Sơ đồ được chép từ bản cũ nên còn `foods.owner_key`, cột đã bỏ khi phép
    # quy đổi NULL chuyển vào thẳng khóa `uq_food_name`. Để lại thì sơ đồ vẽ
    # một cột không tồn tại. Từ điển tên là thứ quyết định: cột nào không có
    # trong đó thì không còn trong CSDL.
    bo = []
    for e in thuc_the:
        thua = [c for c in e.get("columns", [])
                if c.get("name") not in ten_cot[e["name"]]]
        if not thua:
            continue
        id_bo = {c["_id"] for c in thua}
        e["columns"] = [c for c in e["columns"] if c["_id"] not in id_bo]
        bo += [f"{e['name']}.{c['name']}" for c in thua]

        # Hộp thấp đi đúng số dòng đã bỏ, và các dòng bên dưới dồn lên.
        for v in dia["ownedViews"]:
            if (v["_type"] != "ERDEntityView"
                    or v["model"]["$ref"] != e["_id"]):
                continue
            khoang = v["subViews"][1]
            con = khoang.get("subViews", [])
            giu = [cv for cv in con if cv["model"]["$ref"] not in id_bo]
            hut = (len(con) - len(giu)) * CAO_DONG
            for i, cv in enumerate(giu):
                cv["top"] = khoang["top"] + 5 + CAO_DONG * i
            khoang["subViews"] = giu
            khoang["height"] -= hut
            v["height"] -= hut
    if bo:
        print(f"   gỡ {len(bo)} cột không còn trong CSDL: {', '.join(bo)}")

    # ── Đổi tên ──
    doi_bang = doi_cot = 0
    for e in thuc_the:
        goc_bang = e["name"]
        for c in e.get("columns", []):
            if c.get("name") not in ten_cot[goc_bang]:
                sys.exit(f"Chưa có tên tiếng Việt cho {goc_bang}."
                         f"{c.get('name')}")
            c["name"] = ten_cot[goc_bang][c["name"]]
            doi_cot += 1
        e["name"] = ten_bang[goc_bang]
        doi_bang += 1

    # Nhãn tên hộp giữ MỘT BẢN SAO của tên trong `text`, không đọc từ thực
    # thể. Quên chỗ này thì mô hình đã đổi mà sơ đồ vẫn hiện tên cũ.
    ten_theo_id = {e["_id"]: e["name"] for e in thuc_the}
    doi_nhan = 0
    for v in dia["ownedViews"]:
        if v["_type"] != "ERDEntityView":
            continue
        ten = ten_theo_id[v["model"]["$ref"]]
        for sv in v.get("subViews", []):
            if sv["_type"] == "LabelView":
                sv["text"] = ten
                doi_nhan += 1

    print(f"{TEN_MO_HINH}: đổi {doi_bang} tên bảng, {doi_cot} tên cột, "
          f"{doi_nhan} nhãn trên sơ đồ")

    # ── Kiểm bề ngang: tên mới có tràn khỏi hộp không ──
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
        for ten, cu, moi in da_noi:
            print(f"      {ten}: {cu} -> {moi} px")
    else:
        print("   ✓ không hộp nào phải nới — tên mới vừa chỗ cũ")

    # ── Hai mô hình kia phải y nguyên ──
    for e in mo_hinh:
        if e is m:
            continue
        print(f"   giữ nguyên mô hình {e['name'].strip()!r}")

    if args.dry_run:
        print("\n--dry-run: không ghi tệp.")
        return 0

    sao_luu = MDJ.with_suffix(".mdj.bak_doiten")
    if not sao_luu.exists():
        shutil.copy2(MDJ, sao_luu)
        print(f"   Đã sao lưu -> {sao_luu.name}")

    MDJ.write_text(json.dumps(goc, ensure_ascii=False, indent="\t"),
                   encoding="utf-8")
    print(f"\nĐã ghi {MDJ.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
