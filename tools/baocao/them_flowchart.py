# -*- coding: utf-8 -*-
"""Ghi 18 flowchart vào BAOCAO/Diagram.mdj, dùng bộ hình Flowchart của StarUML.

VÌ SAO DÙNG FCFlowchart CHỨ KHÔNG PHẢI UMLActivityDiagram
---------------------------------------------------------
StarUML đóng gói sẵn phần mở rộng `extensions/essential/flowchart`, nên bộ
hình này có mặt ở mọi bản cài, không cần ai cài thêm. Nó cũng đơn giản hơn
hẳn Activity Diagram của UML: một khối chỉ cần **một nhãn**, trong khi một
`UMLUseCaseView` đòi đủ sáu ngăn con ẩn mới mở ra đúng.

Và quan trọng hơn: đề bài là *flowchart*, không phải sơ đồ hoạt động. Hình
thoi, hình trụ, hình thang là ký hiệu flowchart chuẩn; ép chúng vào
`UMLAction` thì mọi khối đều là hình chữ nhật bo góc và mất hết phần phân
tầng.

Kích thước và hình học lấy từ chính mã nguồn của phần mở rộng đó, đọc ra từ
`resources/app.asar` — xem `flowchart_lib.do_khoi`. Không đoán.

CẤU TRÚC GHI VÀO TỆP
--------------------
    UMLModel "Flowchart"              <- thêm mới, ngang hàng Model/ERD/UseCase
      FCFlowchart "FC01 — Đăng ký"
        FCFlowchartDiagram "FC01"     <- sơ đồ, chứa toàn bộ hình vẽ
        FCProcess / FCDecision / ...  <- phần tử mô hình
        (FCFlow nằm trong khối nguồn của nó)

Đặt trong một `UMLModel` thay vì rải 18 `FCFlowchart` ra gốc dự án: gốc dự
án hiện có ba mục (Model, ERD, UseCase), thêm 18 mục nữa thì cây bên trái
không đọc được nữa. Cách lồng này giống hệt cách `UMLModel "UseCase"` đang
chứa sơ đồ Use case trong chính tệp này, nên chắc chắn StarUML mở được.

KHÔNG ĐỤNG VÀO PHẦN CŨ. Script chỉ THÊM một nhánh mới. Trước khi ghi nó so
lại từng byte của ba nhánh `Model`, `ERD`, `ERD_vi` và `UseCase`; lệch một
chỗ là dừng, không ghi.

Chạy:
    python tools/baocao/them_flowchart.py            # chỉ soát, không ghi
    python tools/baocao/them_flowchart.py --ghi
    python tools/baocao/them_flowchart.py --ghi --chap-nhan-ghi-de
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import flowchart_lib as fl  # noqa: E402
from flowchart_data import DAU_DE_XUAT, SO_DO  # noqa: E402

MDJ = pathlib.Path("BAOCAO/Diagram.mdj")
TEN_MODEL = "Flowchart"
#: Ba nhánh phải nguyên vẹn sau khi ghi.
NHANH_CU = ("Model", "ERD ", "UseCase", "ERD_vi")

FONT = "Arial;13;0"

_dem = 0


def mid(s: str) -> str:
    """Sinh _id mới. Tiền tố riêng để chắc chắn không đụng _id có sẵn."""
    global _dem
    _dem += 1
    return f"DATNFC{_dem:05d}{s}="


# ── Dựng phần tử ───────────────────────────────────────────────────────────

def _view_khoi(dia: str, model: str, h: fl.Hop) -> dict:
    """Hình của một khối: một NodeView bọc đúng một LabelView.

    Toạ độ nhãn do StarUML tự tính lại lúc mở (`arrangeObject`), nên giá trị
    ghi ở đây chỉ là giá trị ban đầu; ghi đúng ngay từ đầu để tệp mở ra
    không nhảy hình trong một khung vẽ.
    """
    vid = mid("V")
    kl, kt, kw, kh = fl.khung_chu(h)
    nhan = {
        "_type": "LabelView", "_id": mid("L"), "_parent": {"$ref": vid},
        "model": {"$ref": model}, "font": FONT,
        "left": kl, "top": kt, "width": kw, "height": kh,
        "text": h.text, "wordWrap": True,
    }
    return {
        "_type": fl.KHOI[h.loai][0] + "View", "_id": vid,
        "_parent": {"$ref": dia}, "model": {"$ref": model},
        "subViews": [nhan], "font": FONT,
        "left": h.left, "top": h.top, "width": h.width, "height": h.height,
        "nameLabel": {"$ref": nhan["_id"]}, "wordWrap": True,
    }


def _view_noi(dia: str, flow: dict, v_tail: str, v_head: str,
              pts: list, nhan_text: str) -> dict:
    """Hình của một đường nối, kèm nhãn nhánh ("có" / "không")."""
    vid = mid("E")
    giua = pts[len(pts) // 2]
    nhan = {
        "_type": "EdgeLabelView", "_id": mid("G"), "_parent": {"$ref": vid},
        "model": {"$ref": flow["_id"]}, "font": FONT,
        "left": int(giua[0]), "top": int(giua[1]), "height": 13,
        "alpha": 1.5707963267948966, "distance": 15,
        "edgePosition": 1, "hostEdge": {"$ref": vid},
        "text": nhan_text, "visible": bool(nhan_text),
    }
    return {
        "_type": "FCFlowView", "_id": vid, "_parent": {"$ref": dia},
        "model": {"$ref": flow["_id"]}, "subViews": [nhan], "font": FONT,
        "head": {"$ref": v_head}, "tail": {"$ref": v_tail},
        "points": ";".join(f"{int(x)}:{int(y)}" for x, y in pts),
        "nameLabel": {"$ref": nhan["_id"]},
    }


def dung_so_do(ma: str, ten: str, khoi, canh) -> dict:
    """Một `FCFlowchart` hoàn chỉnh: sơ đồ, các khối và các đường nối."""
    fcid = mid("F")
    diaid = mid("D")
    hop = fl.dat_cho(khoi)
    duong = fl.dung_canh(canh, hop)

    con = []     # phần tử mô hình nằm trong FCFlowchart
    views = []   # hình vẽ nằm trong sơ đồ
    v_cua: dict[str, str] = {}

    for k in khoi:
        h = hop[k[0]]
        m = {"_type": fl.KHOI[h.loai][0], "_id": mid("M"),
             "_parent": {"$ref": fcid}, "name": h.text}
        con.append(m)
        v = _view_khoi(diaid, m["_id"], h)
        views.append(v)
        v_cua[h.ma] = v["_id"]

    mo_hinh = {m["name"]: m for m in con}
    for a, b, nhan_text, pts in duong:
        nguon, dich = mo_hinh[hop[a].text], mo_hinh[hop[b].text]
        flow = {"_type": "FCFlow", "_id": mid("W"),
                "_parent": {"$ref": nguon["_id"]},
                "name": nhan_text,
                "source": {"$ref": nguon["_id"]},
                "target": {"$ref": dich["_id"]}}
        nguon.setdefault("ownedElements", []).append(flow)
        views.append(_view_noi(diaid, flow, v_cua[a], v_cua[b], pts,
                               nhan_text))

    dia = {"_type": "FCFlowchartDiagram", "_id": diaid,
           "_parent": {"$ref": fcid}, "name": ma,
           "defaultDiagram": False, "ownedViews": views}
    return {"_type": "FCFlowchart", "_id": fcid, "name": f"{ma} — {ten}",
            "ownedElements": [dia] + con}


# ── Soát ───────────────────────────────────────────────────────────────────

def kiem_tham_chieu(goc) -> int:
    """Mọi {"$ref": ...} phải trỏ tới một _id có thật.

    Một tham chiếu hỏng không làm StarUML báo lỗi: nó mở tệp ra và lặng lẽ
    bỏ qua phần tử đó, nên sơ đồ thiếu một khối mà không ai biết thiếu.
    """
    co, can = set(), []

    def di(o, duong="$"):
        if isinstance(o, dict):
            if "_id" in o:
                co.add(o["_id"])
            if set(o) == {"$ref"}:
                can.append((o["$ref"], duong))
            for k, v in o.items():
                di(v, f"{duong}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                di(v, f"{duong}[{i}]")

    di(goc)
    hong = [(r, d) for r, d in can if r not in co]
    for r, d in hong[:10]:
        print(f"   ✗ {d} trỏ tới {r} — không có phần tử nào mang _id này")
    if not hong:
        print(f"   [ok] {len(can)} tham chiếu, tất cả đều trỏ đúng")
    return len(hong)


def kiem_id_trung(goc) -> int:
    dem: dict[str, int] = {}

    def di(o):
        if isinstance(o, dict):
            if "_id" in o:
                dem[o["_id"]] = dem.get(o["_id"], 0) + 1
            for v in o.values():
                di(v)
        elif isinstance(o, list):
            for v in o:
                di(v)

    di(goc)
    trung = [k for k, v in dem.items() if v > 1]
    for k in trung[:10]:
        print(f"   ✗ _id {k} xuất hiện {dem[k]} lần")
    if not trung:
        print(f"   [ok] {len(dem)} phần tử, không _id nào trùng")
    return len(trung)


def kiem_use_case(goc) -> int:
    """Mỗi use case phải có đúng một flowchart, và ngược lại."""
    ucm = next(e for e in goc["ownedElements"]
               if e.get("_type") == "UMLModel" and e.get("name") == "UseCase")
    uc = {e["name"] for e in ucm["ownedElements"]
          if e["_type"] == "UMLUseCase"}
    fc = {ten for _, ten, _, _ in SO_DO}
    loi = 0
    for t in sorted(uc - fc):
        print(f"   ✗ use case “{t}” chưa có flowchart")
        loi += 1
    for t in sorted(fc - uc):
        print(f"   ✗ flowchart “{t}” không khớp use case nào trong .mdj")
        loi += 1
    if not loi:
        print(f"   [ok] {len(uc)} use case, {len(fc)} flowchart, khớp từng tên")
    return loi


def kiem_bo_cuc() -> int:
    loi = 0
    for ma, _, khoi, canh in SO_DO:
        hop = fl.dat_cho(khoi)
        duong = fl.dung_canh(canh, hop)
        x = fl.mot_dinh(khoi, canh)
        x += [f"chồng hình: {a} và {b}" for a, b in fl.chong_nhau(hop)]
        x += [f"đường {a}→{b} xuyên khối {m}"
              for a, b, m in fl.xuyen_khoi(duong, hop)]
        x += [f"khối {k} tràn chữ: {fl.chu_tran(h)}"
              for k, h in hop.items() if fl.chu_tran(h)]
        for t in x:
            print(f"   ✗ {ma}: {t}")
        loi += len(x)
    if not loi:
        print(f"   [ok] {len(SO_DO)} sơ đồ, không chồng hình, "
              "không đường xuyên khối, không tràn chữ")
    return loi


def _bam(goc, ten: str) -> str:
    e = next((x for x in goc["ownedElements"] if x.get("name") == ten), None)
    return json.dumps(e, ensure_ascii=False, sort_keys=True)


def main() -> int:
    fl.in_utf8()
    bo = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    bo.add_argument("--ghi", action="store_true",
                    help="thực sự ghi vào .mdj; không có thì chỉ soát")
    bo.add_argument("--chap-nhan-ghi-de", action="store_true",
                    help="cho phép dựng lại nhánh Flowchart đã có — "
                         "mọi chỉnh tay trong StarUML ở nhánh đó sẽ MẤT")
    ts = bo.parse_args()

    if not MDJ.exists():
        sys.exit(f"Không thấy {MDJ}")
    goc = json.loads(MDJ.read_text(encoding="utf-8"))
    cu = {t: _bam(goc, t) for t in NHANH_CU}

    print(f"Soát 18 flowchart với {MDJ.name}")
    print("=" * 72)

    print("\n1. Bố cục")
    loi = kiem_bo_cuc()

    print("\n2. Khớp với sơ đồ Use case")
    loi += kiem_use_case(goc)

    print("\n3. Endpoint còn phải bổ sung vào đặc tả API")
    de_xuat = [(ma, k[4]) for ma, _, khoi, _ in SO_DO for k in khoi
               if DAU_DE_XUAT in k[4]]
    for ma, t in de_xuat:
        print(f"   ! {ma}  {t.replace(chr(10), ' ')[:66]}")
    print(f"   {len(de_xuat)} endpoint chưa có trong "
          "docs/API_SPECIFICATION.md")

    # ── Dựng nhánh mới ──
    da_co = next((e for e in goc["ownedElements"]
                  if e.get("name") == TEN_MODEL), None)
    moi = {"_type": "UMLModel", "_id": mid("R"), "name": TEN_MODEL,
           "ownedElements": [dung_so_do(*s) for s in SO_DO]}
    for con in moi["ownedElements"]:
        con["_parent"] = {"$ref": moi["_id"]}
    # Nhánh đã có thì chỉ CHẶN LÚC GHI, không chặn lúc soát: script này cũng
    # là bộ kiểm chạy cùng các bộ kiểm khác, và một bộ kiểm trả mã thoát 1
    # chỉ vì công việc đã làm xong là một bộ kiểm báo động giả.
    if da_co:
        if ts.ghi and not ts.chap_nhan_ghi_de:
            print(f"\nDỪNG — nhánh “{TEN_MODEL}” đã có trong tệp. Dựng lại "
                  "sẽ xóa mọi chỉnh tay trong StarUML ở nhánh đó.\n"
                  "Muốn dựng lại: thêm --chap-nhan-ghi-de.")
            return 1
        goc["ownedElements"][goc["ownedElements"].index(da_co)] = moi
    else:
        goc["ownedElements"].append(moi)

    print("\n4. Toàn vẹn tệp sau khi thêm")
    loi += kiem_id_trung(goc)
    loi += kiem_tham_chieu(goc)

    print("\n5. Bốn nhánh cũ phải nguyên vẹn")
    for t in NHANH_CU:
        if _bam(goc, t) != cu[t]:
            print(f"   ✗ nhánh “{t}” đã bị đổi — script này chỉ được THÊM")
            loi += 1
    if all(_bam(goc, t) == cu[t] for t in NHANH_CU):
        print(f"   [ok] {', '.join(repr(t) for t in NHANH_CU)} "
              "giống hệt trước khi chạy")

    print("\n" + "=" * 72)
    if loi:
        print(f"{loi} lỗi — KHÔNG ghi gì.")
        return 1

    tong_khoi = sum(len(s[2]) for s in SO_DO)
    tong_noi = sum(len(s[3]) for s in SO_DO)
    print(f"{len(SO_DO)} sơ đồ · {tong_khoi} khối · {tong_noi} đường nối "
          "— không lỗi nào.")
    if not ts.ghi:
        print("Đây là chế độ soát. Thêm --ghi để ghi vào .mdj.")
        return 0

    sl = MDJ.with_suffix(".mdj.bak_flowchart")
    if not sl.exists():
        shutil.copy2(MDJ, sl)
        print(f"Đã sao lưu -> {sl.name}")
    MDJ.write_text(json.dumps(goc, ensure_ascii=False, indent="\t"),
                   encoding="utf-8")
    print(f"Đã ghi {MDJ}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
