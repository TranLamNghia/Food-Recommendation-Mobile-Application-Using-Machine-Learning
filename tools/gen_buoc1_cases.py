#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sinh bộ ca thử Bước 1, và bản tham chiếu Python để đối chiếu.

Vì sao cần. Bước 1 — BMI, BMR, TDEE, hạn mức năng lượng, phân bổ macro và
phân bổ bữa — được hiện thực **ba lần** trong đề tài này:

    backend/Api/Nutrition/NutritionTargets.cs        C#, máy chủ
    mobile/lib/data/models/health_profile.dart       Dart, ứng dụng
    tools/gen_buoc1_cases.py (tệp này)               Python, bản tham chiếu

Ba bản chạy ở ba tầng và không bao giờ gặp nhau, nên khi chúng lệch thì
không gì báo ra: ứng dụng hiện một hạn mức, máy chủ sinh thực đơn theo một
hạn mức khác, và cả hai con số đều trông hợp lý. Chuyện đó đã xảy ra: Dart
cứng hóa macro 17/60/23, đặc tả API ghi 15/60/25, và cột `DEFAULT` trong
CSDL cũng 15/60/25 — ba nguồn, hai con số, không ai biết trong nhiều tuần.

Nguồn công thức là `docs/SYSTEM_ARCHITECTURE.md` §3.1. Tệp này KHÔNG được
chép công thức từ C# hay Dart — nó phải viết lại từ tài liệu, nếu không thì
nó chỉ xác nhận rằng ba bản cùng sai một kiểu.

Ca thử phủ: cả ba giới tính (kể cả `other`, không có hằng số Mifflin nào
được công bố), cả năm mức vận động, cả bốn mục tiêu, ràng buộc kẹp về BMR của
`lose_weight`, bốn nhóm BMI, và các ca làm tròn .5.

Chạy:
    python tools/gen_buoc1_cases.py            # ghi data/buoc1_cases.json
    python tools/gen_buoc1_cases.py --in       # in ra, không ghi
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

ROOT = pathlib.Path(__file__).resolve().parent.parent
RA = ROOT / "data" / "buoc1_cases.json"

#: Ngày tham chiếu CỐ ĐỊNH. Tuổi phụ thuộc ngày gọi, nên một bộ ca thử gán
#: cứng ngày sinh mà không gán cứng "hôm nay" sẽ đổi kết quả mỗi năm — và
#: đổi vào đúng một ngày trong năm, nên nó sẽ lọt qua mọi lần chạy khác.
HOM_NAY = "2026-11-08"

HE_SO_VAN_DONG = {
    "sedentary": "1.200",
    "light": "1.375",
    "moderate": "1.550",
    "active": "1.725",
    "very_active": "1.900",
}

#: Điểm giữa các khoảng ở §3.1: sáng 25–30, trưa 35–40, tối 25–30, phụ 5–10.
TY_LE_BUA = {
    "breakfast": "0.275",
    "lunch": "0.375",
    "dinner": "0.275",
    "snack": "0.075",
}

#: Hằng số Mifflin-St Jeor. `other` là TRUNG ĐIỂM hai hằng số kia — một con
#: số suy ra, không có nguồn công bố nào. Xem ghi chú dài trong
#: `NutritionTargets.Bmr`.
HANG_SO_MIFFLIN = {
    "male": Decimal("5"),
    "female": Decimal("-161"),
    "other": (Decimal("5") + Decimal("-161")) / Decimal("2"),
}


def tuoi(ngay_sinh: date, hom_nay: date) -> int:
    nam = hom_nay.year - ngay_sinh.year
    if (hom_nay.month, hom_nay.day) < (ngay_sinh.month, ngay_sinh.day):
        nam -= 1
    return nam


def bmi(can: Decimal, cao: Decimal) -> Decimal:
    m = cao / Decimal(100)
    return can / (m * m)


def nhom_bmi(gt: Decimal) -> str:
    """Ngưỡng châu Á của WHO 2004: 23 và 25, không phải 25 và 30."""
    if gt < Decimal("18.5"):
        return "underweight"
    if gt < Decimal(23):
        return "normal"
    if gt < Decimal(25):
        return "overweight"
    return "obese"


def bmr(gioi: str, can: Decimal, cao: Decimal, tuoi_nam: int) -> Decimal:
    goc = (Decimal(10) * can + Decimal("6.25") * cao
           - Decimal(5) * Decimal(tuoi_nam))
    return goc + HANG_SO_MIFFLIN[gioi]


def tdee(gt_bmr: Decimal, van_dong: str) -> Decimal:
    return gt_bmr * Decimal(HE_SO_VAN_DONG[van_dong])


def han_muc(gt_tdee: Decimal, gt_bmr: Decimal, muc_tieu: str) -> Decimal:
    if muc_tieu == "lose_weight":
        # Không bao giờ xuống dưới BMR — ràng buộc an toàn ở §3.1.
        return max(gt_tdee - Decimal(500), gt_bmr)
    if muc_tieu == "gain_weight":
        return gt_tdee + Decimal(500)
    return gt_tdee          # maintain, healthy_eating


def tron(gt: Decimal, le: int = 0) -> float:
    """Làm tròn RA XA 0, như Dart và như `MidpointRounding.AwayFromZero`.

    `Math.Round` của .NET mặc định làm tròn về số CHẴN (2.5 thành 2), còn
    `round()` của Python làm y vậy. Dart thì làm tròn ra xa 0. Khác biệt chỉ
    hiện ra ở đúng những ca .5 — hiếm, nên nó sẽ lọt qua mọi lần thử tay.
    """
    q = Decimal(1) if le == 0 else Decimal(1).scaleb(-le)
    v = gt.quantize(q, rounding=ROUND_HALF_UP)
    return int(v) if le == 0 else float(v)


def mot_ca(ten: str, gioi: str, nam_sinh_lui: int, cao: str, can: str,
           van_dong: str, muc_tieu: str,
           pct=(15, 60, 25), ngay_sinh: str | None = None) -> dict:
    hn = date.fromisoformat(HOM_NAY)
    if ngay_sinh:
        ns = date.fromisoformat(ngay_sinh)
    else:
        ns = date(hn.year - nam_sinh_lui, hn.month, hn.day)

    c, w = Decimal(cao), Decimal(can)
    a = tuoi(ns, hn)
    gt_bmi = bmi(w, c)
    gt_bmr = bmr(gioi, w, c, a)
    gt_tdee = tdee(gt_bmr, van_dong)
    gt_hm = han_muc(gt_tdee, gt_bmr, muc_tieu)
    p, cb, f = pct
    assert p + cb + f == 100, f"{ten}: ba tỷ lệ cộng {p + cb + f}%"

    return {
        "ten": ten,
        "vao": {
            "gender": gioi,
            "dateOfBirth": ns.isoformat(),
            "heightCm": float(c),
            "weightKg": float(w),
            "activityLevel": van_dong,
            "goal": muc_tieu,
            "proteinPct": p,
            "carbsPct": cb,
            "fatPct": f,
            "today": HOM_NAY,
        },
        "ra": {
            "age": a,
            "bmi": tron(gt_bmi, 2),
            "bmiCategory": nhom_bmi(gt_bmi),
            "bmrKcal": tron(gt_bmr),
            "tdeeKcal": tron(gt_tdee),
            "activityFactor": float(HE_SO_VAN_DONG[van_dong]),
            "dailyCaloriesTarget": tron(gt_hm),
            "goalAdjustmentKcal": tron(gt_hm - gt_tdee),
            "proteinG": tron(gt_hm * Decimal(p) / 100 / 4, 1),
            "carbsG": tron(gt_hm * Decimal(cb) / 100 / 4, 1),
            "fatG": tron(gt_hm * Decimal(f) / 100 / 9, 1),
            "mealKcal": {
                bua: tron(gt_hm * Decimal(ty))
                for bua, ty in TY_LE_BUA.items()
            },
        },
    }


def cac_ca() -> list[dict]:
    ca: list[dict] = []

    # ── Ca của đặc tả §7.2.3 ─────────────────────────────────────────────
    ca.append(mot_ca("dac-ta-7.2.3", "male", 22, "172", "68.5",
                     "moderate", "maintain"))

    # ── Ba giới tính, cùng mọi thứ còn lại ───────────────────────────────
    for g in ("male", "female", "other"):
        ca.append(mot_ca(f"gioi-{g}", g, 22, "172", "68.5",
                         "moderate", "maintain"))

    # ── Năm mức vận động ─────────────────────────────────────────────────
    for v in HE_SO_VAN_DONG:
        ca.append(mot_ca(f"van-dong-{v}", "female", 30, "160", "55",
                         v, "maintain"))

    # ── Bốn mục tiêu ─────────────────────────────────────────────────────
    for m in ("lose_weight", "maintain", "gain_weight", "healthy_eating"):
        ca.append(mot_ca(f"muc-tieu-{m}", "male", 25, "175", "80",
                         "active", m))

    # ── Kẹp về BMR: giảm cân + ít vận động thì TDEE−500 < BMR ───────────
    # BMR 1655 × 1.2 = 1986; 1986 − 500 = 1486, thấp hơn BMR. Không kẹp thì
    # hệ thống đề xuất ăn dưới mức chuyển hóa cơ bản.
    ca.append(mot_ca("kep-ve-bmr", "male", 22, "172", "68.5",
                     "sedentary", "lose_weight"))
    ca.append(mot_ca("kep-ve-bmr-nu", "female", 60, "150", "45",
                     "sedentary", "lose_weight"))

    # ── Bốn nhóm BMI theo ngưỡng châu Á ─────────────────────────────────
    for ten, cao, can in (("bmi-underweight", "175", "50"),
                          ("bmi-normal", "175", "68"),
                          ("bmi-overweight", "175", "72"),
                          ("bmi-obese", "175", "85")):
        ca.append(mot_ca(ten, "male", 25, cao, can, "moderate", "maintain"))

    # ── Đúng trên ngưỡng 23 và 25 ───────────────────────────────────────
    # 1.75² = 3.0625. 23 × 3.0625 = 70.4375; 25 × 3.0625 = 76.5625.
    ca.append(mot_ca("bmi-dung-23", "male", 25, "175", "70.4375",
                     "moderate", "maintain"))
    ca.append(mot_ca("bmi-dung-25", "male", 25, "175", "76.5625",
                     "moderate", "maintain"))

    # ── Sinh nhật CHƯA tới trong năm nay ─────────────────────────────────
    # Nguồn của 12 phép kiểm sai trong lần chạy đầu của smoke test: ngày
    # sinh 14/11 với hôm nay 08/11 cho tuổi 21, không phải 22.
    ca.append(mot_ca("sinh-nhat-chua-toi", "male", 0, "172", "68.5",
                     "moderate", "maintain", ngay_sinh="2004-11-14"))
    ca.append(mot_ca("sinh-nhat-dung-hom-nay", "male", 0, "172", "68.5",
                     "moderate", "maintain", ngay_sinh="2004-11-08"))
    ca.append(mot_ca("sinh-nhat-vua-qua", "male", 0, "172", "68.5",
                     "moderate", "maintain", ngay_sinh="2004-11-07"))

    # ── Biên của khoảng cho phép ─────────────────────────────────────────
    ca.append(mot_ca("bien-tuoi-13", "female", 13, "150", "40",
                     "light", "healthy_eating"))
    ca.append(mot_ca("bien-tuoi-100", "male", 100, "165", "60",
                     "sedentary", "maintain"))
    ca.append(mot_ca("bien-cao-50", "other", 20, "50", "20",
                     "sedentary", "maintain"))
    ca.append(mot_ca("bien-cao-250", "other", 20, "250", "300",
                     "very_active", "gain_weight"))

    # ── Ca làm tròn .5 ───────────────────────────────────────────────────
    # BMR phải ra đúng x.5 để phân biệt làm tròn về số chẵn với làm tròn ra
    # xa 0. 10×60.05 + 6.25×170 − 5×25 + 5 = 600.5 + 1062.5 − 125 + 5 = 1543
    # — chưa .5. Dùng chiều cao lẻ để tạo .5.
    ca.append(mot_ca("lam-tron-nua", "male", 25, "170.04", "60",
                     "sedentary", "maintain"))

    # ── Bộ ba macro khác mặc định ────────────────────────────────────────
    ca.append(mot_ca("macro-17-60-23", "male", 22, "172", "68.5",
                     "moderate", "maintain", pct=(17, 60, 23)))
    ca.append(mot_ca("macro-20-55-25", "male", 22, "172", "68.5",
                     "moderate", "maintain", pct=(20, 55, 25)))
    ca.append(mot_ca("macro-13-62-25", "female", 40, "158", "52",
                     "light", "lose_weight", pct=(13, 62, 25)))

    return ca


def main(argv: list[str] | None = None) -> int:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="chi_in", action="store_true",
                    help="in ra, không ghi tệp")
    ts = ap.parse_args(argv)

    ca = cac_ca()
    ten = [c["ten"] for c in ca]
    trung = {t for t in ten if ten.count(t) > 1}
    if trung:
        print(f"tên ca bị lặp: {sorted(trung)}", file=sys.stderr)
        return 1

    mau = {
        "_doc": "Ca thử Bước 1. Sinh bởi tools/gen_buoc1_cases.py — đừng "
                "sửa tay. Bản tham chiếu viết lại từ SYSTEM_ARCHITECTURE "
                "§3.1, không chép từ C# hay Dart.",
        "today": HOM_NAY,
        "activityFactor": {k: float(v) for k, v in HE_SO_VAN_DONG.items()},
        "mealShare": {k: float(v) for k, v in TY_LE_BUA.items()},
        "cases": ca,
    }
    chu = json.dumps(mau, ensure_ascii=False, indent=2) + "\n"

    if ts.chi_in:
        print(chu)
        return 0

    RA.parent.mkdir(parents=True, exist_ok=True)
    RA.write_text(chu, encoding="utf-8")
    print(f"{RA.relative_to(ROOT)}: {len(ca)} ca thử")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
