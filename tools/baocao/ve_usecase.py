# -*- coding: utf-8 -*-
"""Vẽ lại sơ đồ Use case từ Diagram.mdj ra ảnh PNG để soi bố cục.

Không thay cho StarUML — chỉ đọc đúng những toạ độ StarUML đã lưu rồi vẽ
lại, để kiểm tra bằng mắt rằng hình mới không chồng hình cũ, không lọt ra
ngoài khung và đường nối cắm đúng viền hình.

Chạy:
    python tools/baocao/ve_usecase.py BAOCAO/_render/usecase.png
"""
import json
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

MDJ = pathlib.Path("BAOCAO/Diagram.mdj")
TY_LE = 0.72
LE = 40
FONT_PATH = r"C:\Windows\Fonts\times.ttf"


def font(co: int):
    try:
        return ImageFont.truetype(FONT_PATH, co)
    except OSError:
        return ImageFont.load_default()


def chu_nhieu_dong(d, text, l, t, w, h, f, mau="black"):
    """Xuống dòng cho vừa bề ngang hình rồi căn giữa theo cả hai chiều."""
    tu = text.split()
    dong, cur = [], ""
    for x in tu:
        thu = (cur + " " + x).strip()
        if d.textlength(thu, font=f) <= w - 16 or not cur:
            cur = thu
        else:
            dong.append(cur)
            cur = x
    if cur:
        dong.append(cur)
    cao = len(dong) * (f.size + 2)
    y = t + (h - cao) / 2
    for ln in dong:
        x = l + (w - d.textlength(ln, font=f)) / 2
        d.text((x, y), ln, font=f, fill=mau)
        y += f.size + 2



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
    ra = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                      else "BAOCAO/_render/usecase.png")
    goc = json.loads(MDJ.read_text(encoding="utf-8"))
    ucm = next(e for e in goc["ownedElements"]
               if e["_type"] == "UMLModel" and e["name"] == "UseCase")
    dia = next(e for e in ucm["ownedElements"]
               if e["_type"] == "UMLUseCaseDiagram")
    ten = {e["_id"]: e.get("name", "") for e in ucm["ownedElements"]}
    moi = {t[0] for t in [
        ("Ghi nhật ký ăn uống",), ("Theo dõi tình trạng cơ thể",),
        ("Thêm món ăn của tôi vào thực đơn",),
        ("Quản lý bệnh lý và ngưỡng dinh dưỡng",)]}

    views = [v for v in dia["ownedViews"]]
    hop = [v for v in views if v["_type"] in
           ("UMLUseCaseView", "UMLActorView", "UMLUseCaseSubjectView")]
    canh = [v for v in views if v["_type"] == "UMLAssociationView"]

    x2 = max(v["left"] + v["width"] for v in hop)
    y2 = max(v["top"] + v["height"] for v in hop)
    W = int((x2 + LE * 2) * TY_LE)
    H = int((y2 + LE * 2) * TY_LE)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    def P(x, y):
        return ((x + LE) * TY_LE, (y + LE) * TY_LE)

    # ── Khung hệ thống ──
    for v in hop:
        if v["_type"] != "UMLUseCaseSubjectView":
            continue
        a, b = P(v["left"], v["top"])
        c, e = P(v["left"] + v["width"], v["top"] + v["height"])
        d.rectangle([a, b, c, e], outline="#555", width=2)
        d.text((a + 8, b + 6), ten.get(v["model"]["$ref"], ""),
               font=font(15), fill="#555")

    # ── Đường nối: vẽ trước để nằm dưới hình ──
    for v in canh:
        pts = [tuple(map(float, p.split(":"))) for p in v["points"].split(";")]
        d.line([P(*p) for p in pts], fill="#888", width=2)

    # ── Tác nhân ──
    for v in hop:
        if v["_type"] != "UMLActorView":
            continue
        cx = v["left"] + v["width"] / 2
        a, b = P(cx - 16, v["top"])
        c, e = P(cx + 16, v["top"] + 32)
        d.ellipse([a, b, c, e], outline="black", width=2)
        d.line([P(cx, v["top"] + 32), P(cx, v["top"] + 60)],
               fill="black", width=2)
        d.line([P(cx - 22, v["top"] + 42), P(cx + 22, v["top"] + 42)],
               fill="black", width=2)
        d.line([P(cx, v["top"] + 60), P(cx - 18, v["top"] + 80)],
               fill="black", width=2)
        d.line([P(cx, v["top"] + 60), P(cx + 18, v["top"] + 80)],
               fill="black", width=2)
        nm = ten.get(v["model"]["$ref"], "")
        f = font(16)
        d.text(P(cx - d.textlength(nm, font=f) / TY_LE / 2,
                 v["top"] + 86), nm, font=f, fill="black")

    # ── Use case ──
    for v in hop:
        if v["_type"] != "UMLUseCaseView":
            continue
        nm = ten.get(v["model"]["$ref"], "")
        la = nm in moi
        a, b = P(v["left"], v["top"])
        c, e = P(v["left"] + v["width"], v["top"] + v["height"])
        d.ellipse([a, b, c, e], outline="#c00" if la else "black",
                  width=3 if la else 2, fill="#fff3f3" if la else "white")
        chu_nhieu_dong(d, nm, a, b, c - a, e - b, font(14),
                       "#c00" if la else "black")

    ra.parent.mkdir(parents=True, exist_ok=True)
    img.save(ra)
    print(f"{ra}  {W}×{H}  — {len(hop) - 3} use case, {len(canh)} đường nối")
    return 0


if __name__ == "__main__":
    sys.exit(main())
