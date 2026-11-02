#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chọn bộ món cho phiên khảo sát khẩu vị, và in ra phiếu để điền.

Việc số 10 của `ML_PIPELINE.md` §12 — nút cổ chai thật của phần học máy. Năm
script trong `ml/` đã chạy được nhưng chưa cho ra con số nào, vì bảy nguồn
tín hiệu đều trống. Việc duy nhất có độ trễ tính theo tuần là **thu dữ liệu**,
và nó cần hai thứ: một bộ món để hỏi, và một cách nhập câu trả lời vào CSDL.
Tệp này làm thứ nhất; `tools/import_swipes.py` làm thứ hai.

## Chọn món thế nào, và vì sao không chọn ngẫu nhiên

Mỗi người chỉ vuốt khoảng 30–40 món, nên mỗi lượt vuốt phải mang về nhiều
thông tin nhất có thể. Rocchio dựng vector sở thích bằng trung bình có dấu
của vector các món, nên nếu bộ món tập trung ở một góc của không gian đặc
trưng thì mọi vector sở thích thu được cũng nằm quanh góc đó — và hệ thống
không phân biệt được hai người có khẩu vị khác nhau.

Thuật toán là **duyệt điểm xa nhất** (farthest-point traversal, còn gọi là
k-center tham lam): mỗi bước thêm món có **khoảng cách nhỏ nhất tới tập đã
chọn là lớn nhất**. Nó cho đảm bảo xấp xỉ 2 lần tối ưu cho bài toán k-center,
và quan trọng hơn với việc này: nó rải món ra khắp không gian thay vì gom
cụm.

Hai điều chỉnh so với bản thuần:

**Phủ đủ nhóm món trước.** Vòng đầu chọn đúng một món cho mỗi nhóm trong 12
nhóm. Nếu để thuật toán tự do, nó sẽ bỏ qua những nhóm nằm giữa không gian
(nhóm `Cơm` chẳng hạn) và dồn vào các nhóm ở biên — trong khi một người dùng
cần được hỏi về cả `Cơm`, vì đó là thứ họ ăn hằng ngày.

**Bắt đầu từ món gần tâm danh mục nhất**, không bắt đầu ngẫu nhiên. Duyệt
điểm xa nhất phụ thuộc điểm khởi đầu, nên chọn ngẫu nhiên sẽ cho một bộ món
khác nhau mỗi lần chạy, và hai người được khảo sát bằng hai bộ khác nhau thì
vector của họ không so được với nhau.

## Hạn chế đã biết, in ra cùng bộ món

Chiều **mức cay** gần như không phủ được: 294/318 món trong danh mục ở mức
cay 0. Thuật toán sẽ nhặt hết số món cay ít ỏi vì chúng nằm xa, nhưng bộ món
vẫn lệch nặng về phía không cay — nên vector sở thích thu được sẽ **yếu ở
chiều cay**. Đây là hạn chế của dữ liệu, không của thuật toán, và phải ghi
vào báo cáo thay vì để người đọc tự phát hiện.

Chạy:
    python tools/make_survey_deck.py                 # 40 món, in ra màn hình
    python tools/make_survey_deck.py --so 36 --ghi   # ghi JSON + phiếu CSV
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.db import in_utf8, ket_noi  # noqa: E402
from ml.features import FEATURE_VERSION, KhongGianDacTrung, Mon, nap_mon  # noqa: E402

THU_MUC = ROOT / "data" / "survey"
TEP_JSON = THU_MUC / "survey_deck.json"
TEP_PHIEU = THU_MUC / "phieu_khao_sat.csv"

#: Bốn lựa chọn của một lượt vuốt, đúng `interactions.action`.
LUA_CHON = {
    "thich": "like",
    "khong_thich": "dislike",
    "binh_thuong": "neutral",
    "chua_biet": "unknown",
}


def _khoang_cach(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def chon_bo_mon(
    mon: list[Mon], kg: KhongGianDacTrung, so_can: int
) -> list[Mon]:
    """Duyệt điểm xa nhất, có phủ nhóm món ở vòng đầu.

    Trả về danh sách theo **thứ tự được chọn**: món đầu tiên là món gần tâm
    danh mục nhất, các món sau xa dần. Thứ tự này có ích khi phải cắt bớt
    phiếu — lấy 20 món đầu vẫn là một bộ phủ tốt.
    """
    if so_can < 1:
        raise ValueError("số món phải từ 1 trở lên")
    if so_can > len(mon):
        raise ValueError(f"chỉ có {len(mon)} món, không chọn được {so_can}")

    vec = {m.id: kg.encode(m) for m in mon}

    # Tâm danh mục, để có một điểm khởi đầu xác định.
    tam = [
        sum(vec[m.id][i] for m in mon) / len(mon) for i in range(kg.length)
    ]
    theo_nhom: dict[str, list[Mon]] = {}
    for m in mon:
        theo_nhom.setdefault(m.category, []).append(m)

    da_chon: list[Mon] = []
    con_lai = {m.id: m for m in mon}

    # ── Vòng 1: mỗi nhóm một món, món gần tâm nhóm nhất ──
    #
    # Chọn món gần tâm nhóm chứ không chọn món xa nhất: ở vòng này mục tiêu
    # là **đại diện** cho nhóm, không phải cực trị. Món cực trị của một nhóm
    # dễ là món lạ, và hỏi người dùng về món lạ thì phần lớn câu trả lời sẽ
    # là "chưa biết" — một lượt vuốt không mang thông tin khẩu vị nào.
    for nhom in sorted(theo_nhom):
        ds = theo_nhom[nhom]
        tam_nhom = [
            sum(vec[m.id][i] for m in ds) / len(ds) for i in range(kg.length)
        ]
        tot = min(ds, key=lambda m: (_khoang_cach(vec[m.id], tam_nhom), m.name))
        da_chon.append(tot)
        con_lai.pop(tot.id, None)
        if len(da_chon) >= so_can:
            return da_chon

    # Sắp lại vòng 1 theo khoảng cách tới tâm danh mục, để món đầu phiếu là
    # món "điển hình" nhất.
    da_chon.sort(key=lambda m: (_khoang_cach(vec[m.id], tam), m.name))

    # ── Vòng 2: duyệt điểm xa nhất ──
    kc_nho_nhat = {
        i: min(_khoang_cach(vec[i], vec[m.id]) for m in da_chon)
        for i in con_lai
    }
    while len(da_chon) < so_can and con_lai:
        # Phá hòa theo tên món để kết quả tái lập được.
        chon = max(
            con_lai,
            key=lambda i: (kc_nho_nhat[i], con_lai[i].name),
        )
        m = con_lai.pop(chon)
        da_chon.append(m)
        del kc_nho_nhat[chon]
        for i in con_lai:
            d = _khoang_cach(vec[i], vec[m.id])
            if d < kc_nho_nhat[i]:
                kc_nho_nhat[i] = d

    return da_chon


def _thong_ke(bo: list[Mon], tat_ca: list[Mon]) -> list[str]:
    nhom: dict[str, int] = {}
    cay: dict[int, int] = {}
    vai: dict[str, int] = {}
    for m in bo:
        nhom[m.category] = nhom.get(m.category, 0) + 1
        cay[m.spice_level] = cay.get(m.spice_level, 0) + 1
        vai[m.dish_role] = vai.get(m.dish_role, 0) + 1

    cay_dm: dict[int, int] = {}
    for m in tat_ca:
        cay_dm[m.spice_level] = cay_dm.get(m.spice_level, 0) + 1

    dong = [
        f"{len(bo)} món, phủ {len(nhom)}/{len({m.category for m in tat_ca})} nhóm",
        "  nhóm:  " + "  ".join(f"{k}={v}" for k, v in sorted(nhom.items())),
        "  vai:   " + "  ".join(f"{k}={v}" for k, v in sorted(vai.items())),
        "  cay:   "
        + "  ".join(f"mức {k}={v}" for k, v in sorted(cay.items()))
        + "   (danh mục: "
        + " ".join(f"mức {k}={v}" for k, v in sorted(cay_dm.items()))
        + ")",
    ]
    if cay.get(0, 0) / len(bo) > 0.6:
        dong.append(
            f"  ⚠ {cay.get(0, 0)}/{len(bo)} món ở mức cay 0 — chiều 'Mức cay' "
            f"của vector sở thích sẽ yếu. Hạn chế của dữ liệu "
            f"({cay_dm.get(0, 0)}/{len(tat_ca)} món trong danh mục không cay)."
        )
    return dong


HUONG_DAN = [
    "# PHIẾU KHẢO SÁT KHẨU VỊ",
    "#",
    "# Điền cột `lua_chon` bằng MỘT trong bốn giá trị:",
    "#     thich        — thích món này",
    "#     khong_thich  — không thích",
    "#     binh_thuong  — thấy bình thường",
    "#     chua_biet    — CHƯA TỪNG ĂN món này",
    "#",
    "# `chua_biet` khác `binh_thuong`: lượt `chua_biet` bị loại khỏi phép",
    "# tính vector sở thích, còn `binh_thuong` thì được đếm là một tín hiệu",
    "# trung tính. Chọn `binh_thuong` cho món chưa từng ăn sẽ làm loãng mọi",
    "# sở thích thật — xem ML_PIPELINE.md §5.1.",
    "#",
    "# Điền cả phần thông tin dưới đây rồi nhập bằng:",
    "#     python tools/import_swipes.py --phieu <tệp này>",
    "#",
    "# ho_ten: ",
    "# email: ",
    "# gioi_tinh: male            # male | female | other",
    "# ngay_sinh: 2004-01-01      # YYYY-MM-DD",
    "# chieu_cao_cm: 170",
    "# can_nang_kg: 60",
    "# muc_van_dong: moderate     # sedentary | light | moderate | active | very_active",
    "# muc_tieu: maintain         # lose_weight | maintain | gain_weight | healthy_eating",
    "# benh_ly:                   # cách nhau bằng dấu ;  để trống nếu không có",
    "# ngay_khao_sat: {ngay}",
    "#",
]


def ghi_phieu(bo: list[Mon], duong_dan: Path) -> None:
    duong_dan.parent.mkdir(parents=True, exist_ok=True)
    with duong_dan.open("w", encoding="utf-8-sig", newline="") as f:
        for dong in HUONG_DAN:
            f.write(dong.format(ngay=date.today().isoformat()) + "\n")
        w = csv.writer(f)
        w.writerow(["stt", "ma_mon", "ten_mon", "nhom", "muc_cay", "lua_chon"])
        for i, m in enumerate(bo, start=1):
            w.writerow([i, m.id, m.name, m.category, m.spice_level, ""])


def ghi_json(bo: list[Mon], kg: KhongGianDacTrung, duong_dan: Path) -> None:
    duong_dan.parent.mkdir(parents=True, exist_ok=True)
    duong_dan.write_text(
        json.dumps(
            {
                "_doc": (
                    "Bộ món khảo sát khẩu vị, sinh bởi "
                    "tools/make_survey_deck.py. Thứ tự là thứ tự được chọn: "
                    "món đầu gần tâm danh mục nhất, các món sau xa dần."
                ),
                "feature_version": FEATURE_VERSION,
                "sinh_ngay": date.today().isoformat(),
                "so_mon": len(bo),
                "lua_chon": LUA_CHON,
                "mon": [
                    {
                        "thu_tu": i,
                        "id": m.id,
                        "name": m.name,
                        "category": m.category,
                        "dish_role": m.dish_role,
                        "spice_level": m.spice_level,
                        "kcal": m.kcal,
                        "vector": kg.encode(m),
                    }
                    for i, m in enumerate(bo, start=1)
                ],
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    in_utf8()
    bo_doc = argparse.ArgumentParser(description=__doc__)
    bo_doc.add_argument("--so", type=int, default=40, help="số món (mặc định 40)")
    bo_doc.add_argument("--db", default=None)
    bo_doc.add_argument("--ghi", action="store_true", help="ghi JSON và phiếu CSV")
    t = bo_doc.parse_args()

    cn = ket_noi(t.db)
    try:
        mon, bao_cao = nap_mon(cn)
    finally:
        cn.close()

    kg = KhongGianDacTrung.tu_mon(mon)
    bo = chon_bo_mon(mon, kg, t.so)

    print()
    for d in _thong_ke(bo, mon):
        print(d)
    print()
    print(f"{'#':>3}  {'cay':>3}  món")
    for i, m in enumerate(bo, start=1):
        print(f"{i:>3}  {m.spice_level:>3}  {m.name}  [{m.category}]")

    if not t.ghi:
        print("\nChạy thử — chưa ghi tệp. Thêm --ghi để xuất JSON và phiếu CSV.")
        return 0

    ghi_json(bo, kg, TEP_JSON)
    ghi_phieu(bo, TEP_PHIEU)
    print(f"\nĐã ghi {TEP_JSON.relative_to(ROOT)}")
    print(f"Đã ghi {TEP_PHIEU.relative_to(ROOT)}")
    print(
        "\nChép phiếu cho từng người vào data/survey/da_dien/ rồi nhập:\n"
        "    cp data/survey/phieu_khao_sat.csv data/survey/da_dien/nguoi-01.csv\n"
        "    python tools/import_swipes.py --phieu data/survey/da_dien/nguoi-01.csv\n"
        "\nPhiếu ĐÃ ĐIỀN phải để trong data/survey/da_dien/ — thư mục đó bị\n"
        ".gitignore chặn. Phiếu đã điền chứa họ tên, email, ngày sinh, cân nặng\n"
        "và bệnh lý của người thật, và repo này là repo công khai."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
