# -*- coding: utf-8 -*-
"""Vẽ 18 flowchart ra PNG để soi bố cục bằng mắt, trước khi ghi vào .mdj.

Dùng đúng các hàm bố cục của `flowchart_lib.py` mà `them_flowchart.py` dùng,
nên ảnh nói đúng về tệp sẽ được ghi. Hình vẽ ở đây mô phỏng hình StarUML
chứ không trùng khít từng pixel — điều phải khớp là *vị trí và kích thước
khối* cùng *đường đi của đường nối*, vì đó là những thứ .mdj lưu.

Chạy:
    python tools/baocao/ve_flowchart.py            # cả 18
    python tools/baocao/ve_flowchart.py FC07        # một sơ đồ
"""
from __future__ import annotations

import pathlib
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import flowchart_lib as fl  # noqa: E402
from flowchart_data import SO_DO  # noqa: E402

RA = pathlib.Path("BAOCAO/_render/flowchart")

MAU = {
    "term":  ("#2E5FBF", "#EDF2FD"),
    "input": ("#8A6314", "#FBF4E4"),
    "disp":  ("#6B6C71", "#F4F4F5"),
    "proc":  ("#11788E", "#E8F4F7"),
    "call":  ("#7A3FB0", "#F3ECFA"),
    "db":    ("#0A7A3C", "#E9F6EE"),
    "dec":   ("#B3500F", "#FDF0E6"),
}


def _chu(d, h: fl.Hop, mau: str) -> None:
    """Đặt chữ đúng vào khung mà StarUML dành cho nhãn, không phải vào tâm
    khối — với hình trụ và hình thoi hai chỗ đó lệch nhau khá nhiều."""
    f = fl.font()
    kl, kt, kw, kh = fl.khung_chu(h)
    y = kt + (kh - len(h.dong) * fl.CAO_DONG) / 2
    for ln in h.dong:
        d.text((kl + (kw - f.getlength(ln)) / 2, y), ln, font=f, fill=mau)
        y += fl.CAO_DONG


def _ve_khoi(d, h: fl.Hop) -> None:
    vien, nen = MAU[h.loai]
    l, t, r, b = h.left, h.top, h.right, h.bottom
    if h.loai == "term":
        d.rounded_rectangle([l, t, r, b], radius=h.height // 2,
                            outline=vien, fill=nen, width=2)
    elif h.loai == "dec":
        d.polygon([(h.cx, t), (r, h.cy), (h.cx, b), (l, h.cy)],
                  outline=vien, fill=nen, width=2)
    elif h.loai == "db":
        e = 12
        d.rectangle([l, t + e, r, b - e], outline=nen, fill=nen)
        d.ellipse([l, b - e * 2, r, b], outline=vien, fill=nen, width=2)
        d.rectangle([l, t + e, r, b - e], outline=nen, fill=nen)
        d.line([(l, t + e), (l, b - e)], fill=vien, width=2)
        d.line([(r, t + e), (r, b - e)], fill=vien, width=2)
        d.ellipse([l, t, r, t + e * 2], outline=vien, fill=nen, width=2)
    elif h.loai == "input":
        # Nhập tay: mép trên xiên.
        d.polygon([(l, t + 14), (r, t), (r, b), (l, b)],
                  outline=vien, fill=nen, width=2)
    elif h.loai == "disp":
        d.polygon([(l, h.cy), (l + 18, t), (r - 14, t), (r, h.cy),
                   (r - 14, b), (l + 18, b)],
                  outline=vien, fill=nen, width=2)
    elif h.loai == "call":
        d.rectangle([l, t, r, b], outline=vien, fill=nen, width=2)
        d.line([(l + 10, t), (l + 10, b)], fill=vien, width=1)
        d.line([(r - 10, t), (r - 10, b)], fill=vien, width=1)
    else:
        d.rectangle([l, t, r, b], outline=vien, fill=nen, width=2)
    _chu(d, h, vien)


def _mui_nhon(d, p1, p2) -> None:
    """Mũi nhọn ở đầu đường nối, hướng theo đoạn cuối."""
    x1, y1 = p1
    x2, y2 = p2
    k = 7
    if x1 == x2:
        dy = k if y2 > y1 else -k
        d.polygon([(x2, y2), (x2 - 5, y2 - dy), (x2 + 5, y2 - dy)],
                  fill="#444")
    else:
        dx = k if x2 > x1 else -k
        d.polygon([(x2, y2), (x2 - dx, y2 - 5), (x2 - dx, y2 + 5)],
                  fill="#444")


def ve(ma: str, ten: str, khoi, canh, ra: pathlib.Path) -> tuple[int, int]:
    hop = fl.dat_cho(khoi)
    duong = fl.dung_canh(canh, hop)

    xs = [h.left for h in hop.values()] + [h.right for h in hop.values()]
    ys = [h.top for h in hop.values()] + [h.bottom for h in hop.values()]
    for _, _, _, pts in duong:
        xs += [p[0] for p in pts]
        ys += [p[1] for p in pts]
    W = max(xs) + fl.LE
    H = max(ys) + fl.LE

    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.text((fl.LE, 16), f"{ma} — {ten}", font=fl.font(), fill="#111")

    for _, _, nhan, pts in duong:
        d.line(pts, fill="#444", width=2)
        _mui_nhon(d, pts[-2], pts[-1])
        if nhan:
            mx, my = pts[0], pts[1]
            x = (mx[0] + my[0]) / 2
            y = (mx[1] + my[1]) / 2
            w = fl.font().getlength(nhan)
            d.rectangle([x - w / 2 - 3, y - 8, x + w / 2 + 3, y + 8],
                        fill="white")
            d.text((x - w / 2, y - 7), nhan, font=fl.font(), fill="#B3500F")

    for h in hop.values():
        _ve_khoi(d, h)

    ra.parent.mkdir(parents=True, exist_ok=True)
    img.save(ra)
    return W, H


def main() -> int:
    fl.in_utf8()
    loc = sys.argv[1] if len(sys.argv) > 1 else None
    tong_loi = 0
    for ma, ten, khoi, canh in SO_DO:
        if loc and ma != loc:
            continue
        loi = fl.mot_dinh(khoi, canh)
        hop = fl.dat_cho(khoi)
        duong = fl.dung_canh(canh, hop)
        for a, b in fl.chong_nhau(hop):
            loi.append(f"chồng hình: {a} và {b}")
        for ma_k, h in hop.items():
            tran = fl.chu_tran(h)
            if tran:
                loi.append(f"khối {ma_k} tràn chữ: {tran}")
        for a, b, m in fl.xuyen_khoi(duong, hop):
            loi.append(f"đường {a}→{b} xuyên qua khối {m}")
        W, H = ve(ma, ten, khoi, canh, RA / f"{ma}.png")
        dau = "✗" if loi else "ok"
        print(f"[{dau}] {ma}  {len(khoi):2d} khối, {len(canh):2d} nối  "
              f"{W}×{H}")
        for x in loi:
            print(f"        {x}")
        tong_loi += len(loi)
    print(f"\n{tong_loi} lỗi bố cục")
    return 1 if tong_loi else 0


if __name__ == "__main__":
    sys.exit(main())
