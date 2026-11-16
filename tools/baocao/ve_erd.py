# -*- coding: utf-8 -*-
"""Vẽ lại các sơ đồ ERD trong Diagram.mdj ra ảnh PNG để soi bố cục.

Không thay cho StarUML — chỉ đọc đúng những toạ độ đã lưu trong tệp rồi vẽ
lại bằng cùng phông Arial 13, để kiểm tra bằng mắt rằng hộp không đè nhau,
chữ không tràn khỏi hộp và đường nối cắm đúng viền hộp. Nếu ảnh này đúng
thì StarUML mở ra cũng đúng, vì cả hai đọc cùng một bộ toạ độ.

Script còn ĐẾM SỐ CHỖ HAI ĐƯỜNG CẮT NHAU trên ảnh. Đây là con số đo thật
trên hình vẽ, khác với số cặp đường cắt nhau mà `build_erd.py` tối ưu —
con số kia đếm theo thứ tự các nút giữa hai hàng, chưa tính đoạn đi ngang
trong dải trống. Hai con số bổ sung cho nhau.

Chạy:
    python tools/baocao/ve_erd.py          # vẽ cả hai sơ đồ
"""

import json
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
MDJ = ROOT / "BAOCAO" / "Diagram.mdj"
RA = ROOT / "BAOCAO" / "_render"
LE = 24
ARIAL = r"C:\Windows\Fonts\arial.ttf"
ARIAL_B = r"C:\Windows\Fonts\arialbd.ttf"


def doan_cat(a, b) -> bool:
    """Hai đoạn thẳng vuông góc có cắt nhau trong lòng không."""
    (x1, y1), (x2, y2) = a
    (x3, y3), (x4, y4) = b
    doc_a, doc_b = x1 == x2, x3 == x4
    if doc_a == doc_b:
        return False
    if doc_b:
        (x1, y1), (x2, y2), (x3, y3), (x4, y4) = (x3, y3), (x4, y4), \
            (x1, y1), (x2, y2)
    # a dọc tại x1, b ngang tại y3
    return (min(y1, y2) < y3 < max(y1, y2)
            and min(x3, x4) < x1 < max(x3, x4))


def ve(dia, ent, ra: pathlib.Path, nhan: str) -> None:
    hop = [v for v in dia["ownedViews"] if v["_type"] == "ERDEntityView"]
    canh = [v for v in dia["ownedViews"]
            if v["_type"] == "ERDRelationshipView"]

    duong = [[tuple(map(float, p.split(":"))) for p in v["points"].split(";")]
             for v in canh]
    diem = [p for d in duong for p in d]
    w = int(max([v["left"] + v["width"] for v in hop]
                + [x for x, _ in diem])) + LE * 2
    h = int(max([v["top"] + v["height"] for v in hop]
                + [y for _, y in diem])) + LE * 2

    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(ARIAL, 13)
    fb = ImageFont.truetype(ARIAL_B, 13)

    # ── Đường nối: vẽ trước để nằm dưới hộp ──
    for pts in duong:
        d.line([(x + LE, y + LE) for x, y in pts], fill="#8a8a8a", width=2)
        # Chân quạ ở đầu phía con, như StarUML vẽ cho lượng số 0..*
        (x2, y2), (x1, y1) = pts[-1], pts[-2]
        if x1 != x2:
            k = 1 if x1 > x2 else -1
            for dy in (-5, 5):
                d.line([(x2 + LE, y2 + LE), (x2 + LE + 5 * k, y2 + LE + dy)],
                       fill="#8a8a8a", width=2)
        else:
            k = 1 if y1 > y2 else -1
            for dx in (-5, 5):
                d.line([(x2 + LE, y2 + LE), (x2 + LE + dx, y2 + LE + 5 * k)],
                       fill="#8a8a8a", width=2)

    # ── Hộp thực thể ──
    tran = []
    for v in hop:
        e = ent[v["model"]["$ref"]]
        x, y = v["left"] + LE, v["top"] + LE
        x2, y2 = x + v["width"], y + v["height"]
        d.rectangle([x, y, x2, y2], fill="#ffffff", outline="#333333",
                    width=2)
        d.text((x + 6, y + 4), e["name"], font=fb, fill="black")
        d.line([x, y + 23, x2, y + 23], fill="#999999", width=1)

        for i, c in enumerate(e["columns"]):
            co = []
            if c.get("primaryKey"):
                co.append("PK")
            if c.get("foreignKey"):
                co.append("FK")
            if c.get("unique"):
                co.append("UQ")
            txt = f"{c['name']}: {c['type']}"
            ty = y + 23 + 5 + 15 * i
            d.text((x + 5, ty), txt, font=f, fill="black")
            if co:
                d.text((x2 - 34, ty), "/".join(co)[:5], font=f, fill="#0a6ebd")
            if d.textlength(txt, font=f) > v["width"] - 44:
                tran.append(f"{e['name']}.{c['name']}")

    # ── Đếm chỗ cắt nhau thật trên hình ──
    seg = [(i, (a, b)) for i, pts in enumerate(duong)
           for a, b in zip(pts, pts[1:])]
    cat = sum(1 for i, (k, s) in enumerate(seg) for k2, s2 in seg[i + 1:]
              if k != k2 and doan_cat(s, s2))

    ra.parent.mkdir(parents=True, exist_ok=True)
    img.save(ra)
    print(f"{ra.relative_to(ROOT)}  {w}×{h}  — {len(hop)} thực thể, "
          f"{len(canh)} quan hệ, {cat} chỗ đường cắt nhau")
    if tran:
        print(f"  CHỮ TRÀN KHỎI HỘP ({len(tran)}): {tran[:6]}")
    else:
        print(f"  ✓ [{nhan}] không dòng nào tràn khỏi hộp")



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
    goc = json.loads(MDJ.read_text(encoding="utf-8"))
    mo_hinh = [e for e in goc["ownedElements"]
               if e["_type"] == "ERDDataModel"]
    if not mo_hinh:
        sys.exit("Không thấy mô hình ERD nào trong tệp.")

    for n, m in enumerate(mo_hinh):
        dia = next(e for e in m["ownedElements"]
                   if e["_type"] == "ERDDiagram")
        ent = {e["_id"]: e for e in m["ownedElements"]
               if e["_type"] == "ERDEntity"}
        ten = "erd.png" if n == 0 else f"erd_{n + 1}.png"
        ve(dia, ent, RA / ten, m["name"].strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
