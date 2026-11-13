#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nạp tập mô phỏng vào CSDL: 50 người, 2250 lượt vuốt, hồ sơ Rocchio.

Chỗ chặn đường mà tệp này mở. `ml/build_dataset.py` trả về 0 mẫu vì CSDL
chưa có người dùng nào, nên `train.py`, `evaluate.py` và cả bảng so sánh của
Chương 3 đều không chạy được. Tệp này là bước thiếu giữa hai tệp CSV ở
`data/survey/mo_phong/` và các bảng mà đường ống đọc.

Khác `import_swipes.py` ở đâu: tệp kia nhập **một phiếu giấy của một người
thật**, có khối `# khóa: giá trị` đã khai sẵn `ngay_sinh`, `chieu_cao_cm`,
`muc_van_dong`, `muc_tieu`. Tệp này nhập **50 hồ sơ máy** từ
`ObesityDataSet`, và tệp nguồn đó **không có** bốn trường ấy — nó có `Age`
thập phân, `Height` theo mét, `FAF` liên tục 0–3 và `NObeyesdad` 7 nhãn. Bốn
phép quy đổi dưới đây là toàn bộ phần phải tự quyết, nên mỗi phép đều ghi rõ
căn cứ và ghi rõ cái nó **không** làm được.

## Bốn phép quy đổi

**1. `Age` thập phân → `date_of_birth`.** 31/50 hồ sơ có tuổi không nguyên
(21,47 · 36,84…) vì 75% `ObesityDataSet` là dòng SMOTE nội suy. Lược đồ lưu
ngày sinh, không lưu tuổi — đúng, vì tuổi là đại lượng dẫn xuất đổi theo
ngày. Phép quy đổi: làm tròn tuổi, rồi đặt ngày sinh vào khoảng 1–300 ngày
**trước** mốc sinh nhật năm nay, lệch theo chỉ số người để 50 hồ sơ không
cùng một ngày sinh. Lùi lại ít nhất một ngày là bắt buộc: đặt đúng mốc thì
`tuoi()` trả về `n` hay `n − 1` tùy giờ chạy.

Phép quy đổi tự kiểm: `tuoi(ngay_sinh, ngay_nap) == round(Age)` được `assert`
cho cả 50 dòng. Không có phép tự kiểm đó thì một lỗi lệch-một ở đây đi
thẳng vào BMR của cả 50 người và không gì báo ra.

**2. `Height` mét → `height_cm`.** Nhân 100. Cột `health_profiles.bmi` là cột
`VIRTUAL` tính theo `height_cm`, nên sau phép nhân này CSDL tự cho ra BMI
đúng — khoảng 16,2–44,1. Cột `BMI` trong `f1_training_dataset_50_users.csv`
thì sai 10 000 lần vì nó áp công thức dành cho cm vào giá trị đã là mét;
tệp này **không đọc cột đó**.

**3. `FAF` 0–3 → `activity_level` 5 bậc.** `FAF` gốc là câu hỏi bốn lựa chọn
(0 = không tập · 1 = 1–2 ngày · 2 = 2–4 ngày · 3 = 4–5 ngày mỗi tuần), và
giá trị thập phân chỉ là sản phẩm của SMOTE. Nên phép quy đổi là **làm tròn
về câu trả lời nguyên gốc gần nhất**, rồi ánh xạ sang bậc có cùng tần suất
trong `SYSTEM_ARCHITECTURE.md` §3.1.

**`very_active` không bao giờ xuất hiện, và đó là tính chất của bộ câu hỏi
nguồn chứ không phải lỗi.** Bậc cao nhất của `FAF` là "4–5 ngày mỗi tuần",
còn `very_active` là "lao động nặng hoặc tập hai buổi mỗi ngày" — thang đo
nguồn **không với tới** bậc đó. Gán `very_active` cho `FAF = 3` sẽ nhân hạn
mức năng lượng với 1,900 thay vì 1,725, tức bơm thêm ~10% calo cho một nhóm
người mà dữ liệu không nói gì về họ.

**4. `NObeyesdad` 7 nhãn → `goal` 4 bậc.** `Insufficient_Weight` →
`gain_weight`; `Normal_Weight` → `maintain`; hai bậc `Overweight` và ba bậc
`Obesity` → `lose_weight`.

**`healthy_eating` không bao giờ xuất hiện, và cũng là tính chất của nguồn.**
Nó là một lựa chọn người dùng **tự khai** ("tôi không đặt nặng cân nặng"),
không suy ra được từ một nhãn phân loại cân nặng. Suy ra thì tệp này đang
bịa một ý định mà không ai phát biểu.

## Những gì tệp này KHÔNG ghi, và vì sao

`user_conditions` **trống cho cả 50 người.** `ObesityDataSet` có 17 cột và
không cột nào là bệnh lý, dị ứng hay chế độ ăn — nên Bộ lọc F1 loại 0/2250
lượt. Tệp này vẫn **gọi** F1 chứ không bỏ qua, để khi có bước gán bệnh lý mô
phỏng thì đường đi đã đúng sẵn; hiện giờ nó chỉ in ra con số 0 thật thà.

Vector khẩu vị ẩn `t_u` **không vào CSDL.** Lược đồ không có cột cho nó, và
thêm một cột chỉ dữ liệu mô phỏng mới dùng là làm lược đồ phải gánh một thứ
không thuộc về sản phẩm. Nó ở lại `khau_vi_that.json`, và
`tools/check_mo_phong.py` là chỗ đọc nó.

## Nạp hết rồi mới commit

Cả 50 người nằm trong **một giao dịch**. Một lần nạp dở — 23 người có lượt
vuốt, 27 người không — tệ hơn hẳn một lần chưa nạp: `build_dataset` vẫn chạy
qua nó và âm thầm dựng một tập huấn luyện khuyết.

Chạy
────
    python tools/import_mo_phong.py              # xem trước, không ghi
    python tools/import_mo_phong.py --apply
    python tools/import_mo_phong.py --xoa        # xóa lần nạp trước
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.db import in_utf8, ket_noi  # noqa: E402
from ml.features import FEATURE_VERSION, KhongGianDacTrung, nap_mon  # noqa: E402
from ml.rocchio import alpha, dung_ho_so, giai_doan  # noqa: E402

from tools.gen_buoc1_cases import bmr, han_muc, tdee, tron, tuoi  # noqa: E402

# Dùng lại nguyên bộ của `import_swipes.py` chứ không viết bản thứ hai: phép
# tra bệnh lý, mức độ ghi vào `user_conditions`, phép lọc F1 lúc nhập và giá
# trị băm không dùng được đều phải **giống hệt** giữa hai đường nhập. Hai bản
# cài đặt của cùng một phép lọc là hai chỗ để lệch, và chỗ lệch ở đây có
# nghĩa là F1 lúc nhập loại một tập món khác F1 lúc chạy thật.
from tools.import_swipes import (  # noqa: E402
    BAM_KHONG_DUNG_DUOC,
    SEVERITY_PHIEU,
    LoiPhieu,
    _ly_do_ngan,
    kiem_benh_ly,
    loc_theo_f1,
)
from tools.make_survey_deck import LUA_CHON  # noqa: E402

HANH_VI = ROOT / "data" / "survey" / "mo_phong" / "hanh_vi.csv"
SU_THAT = ROOT / "data" / "survey" / "mo_phong" / "khau_vi_that.json"
HO_SO_NGUON = ROOT / "data" / "survey" / "f1_training_dataset_50_users.csv"

#: Tên miền `.invalid` được RFC 2606 dành riêng và không bao giờ phân giải
#: được. Tiền tố khác `khaosat-` của `import_swipes.py` có chủ ý: hai lần nạp
#: phải phân biệt được nhau, vì `--xoa` dưới đây xóa theo đúng mẫu này và
#: trùng tiền tố thì nó xóa luôn phiếu người thật.
MAU_EMAIL = "mophong-{}@local.invalid"
MAU_EMAIL_LIKE = "mophong-%@local.invalid"

#: `FAF` làm tròn → `activity_level`. Xem phép quy đổi 3 ở đầu tệp.
FAF_SANG_VAN_DONG = {
    0: "sedentary",   # không tập
    1: "light",       # 1–2 ngày mỗi tuần
    2: "moderate",    # 2–4 ngày
    3: "active",      # 4–5 ngày
}

#: `NObeyesdad` → `goal`. Xem phép quy đổi 4 ở đầu tệp.
NHAN_SANG_MUC_TIEU = {
    "Insufficient_Weight": "gain_weight",
    "Normal_Weight": "maintain",
    "Overweight_Level_I": "lose_weight",
    "Overweight_Level_II": "lose_weight",
    "Obesity_Type_I": "lose_weight",
    "Obesity_Type_II": "lose_weight",
    "Obesity_Type_III": "lose_weight",
}

GIOI = {"Male": "male", "Female": "female"}

#: Khoảng lệch ngày sinh quanh mốc sinh nhật, xem phép quy đổi 1.
LECH_NGAY_SINH = 300

#: Không gian tên để sinh `users.id` và `interactions.session_id` bằng UUID v5.
#:
#: **Phải là UUID v5, không được là `uuid4()`,** và đây không phải chuyện
#: thẩm mỹ. `ml/build_dataset.py` gán fold bằng
#: `sorted(nguoi, key=sha256(f"{seed}:{user_id}"))` và bốc mẫu `random_neg`
#: bằng `random.Random(f"{seed}:{user_id}")`. Khóa của cả hai là `user_id`,
#: nên với `uuid4()` thì **mỗi lần nạp lại cho ra một cách chia fold khác và
#: một tập mẫu âm khác** — tức mọi con số trong bảng so sánh của Chương 3 đổi
#: sau mỗi lần chạy, mà không ai sửa gì cả.
#:
#: UUID v5 là băm SHA-1 của (không gian tên, tên), nên `U001` luôn cho đúng
#: một `user_id`. Cả chuỗi `--xoa` → `--apply` → `build_dataset` → `train` →
#: `evaluate` vì vậy tái lập được từng chữ số.
#:
#: `uuid.NAMESPACE_URL` với một URL `.invalid` thay vì một UUID bốc tay: tên
#: miền đó được RFC 2606 dành riêng nên không trùng với không gian tên của ai.
KHONG_GIAN_TEN = uuid.uuid5(uuid.NAMESPACE_URL, "https://mophong.local.invalid/")


class LoiNap(Exception):
    """Dữ liệu vào không dùng được. Thông điệp phải nói rõ phải sửa chỗ nào."""


# ── đọc và quy đổi ────────────────────────────────────────────────────────


def lui_nam(moc: date, nam: int) -> date:
    """`moc` lùi `nam` năm. 29/2 lùi về 28/2 vì năm đích có thể không nhuận."""
    try:
        return moc.replace(year=moc.year - nam)
    except ValueError:
        return moc.replace(year=moc.year - nam, day=28)


def ngay_sinh_tu_tuoi(tuoi_nam: int, chi_so: int, hom_nay: date) -> date:
    """Ngày sinh cho ra đúng `tuoi_nam` tuổi vào `hom_nay`."""
    moc = lui_nam(hom_nay, tuoi_nam)
    ngay = moc - timedelta(days=1 + (chi_so * 7) % LECH_NGAY_SINH)
    if tuoi(ngay, hom_nay) != tuoi_nam:
        raise LoiNap(
            f"quy đổi ngày sinh sai: {ngay} cho ra {tuoi(ngay, hom_nay)} tuổi, "
            f"cần {tuoi_nam}. Xem `ngay_sinh_tu_tuoi`."
        )
    return ngay


def quy_doi_ho_so(h: dict[str, str], chi_so: int, hom_nay: date) -> dict[str, Any]:
    """Một dòng `ObesityDataSet` → các trường của `health_profiles`."""
    ma = h["user_id"]

    if h["Gender"] not in GIOI:
        raise LoiNap(f"{ma}: `Gender` = {h['Gender']!r}, chỉ nhận Male/Female")
    if h["NObeyesdad"] not in NHAN_SANG_MUC_TIEU:
        raise LoiNap(
            f"{ma}: `NObeyesdad` = {h['NObeyesdad']!r} không có trong bảng quy "
            f"đổi. Bảy nhãn đã biết: {', '.join(sorted(NHAN_SANG_MUC_TIEU))}"
        )

    try:
        tuoi_tho = float(h["Age"])
        cao_m = float(h["Height"])
        can = float(h["Weight"])
        faf = float(h["FAF"])
    except ValueError as e:
        raise LoiNap(f"{ma}: số không đọc được — {e}") from e

    faf_lam_tron = int(round(faf))
    if faf_lam_tron not in FAF_SANG_VAN_DONG:
        raise LoiNap(
            f"{ma}: `FAF` = {faf} làm tròn ra {faf_lam_tron}, ngoài khoảng 0–3"
        )

    tuoi_nam = int(round(tuoi_tho))
    cao_cm = round(cao_m * 100, 2)
    # DECIMAL(5,2) chứa tối đa 999,99. Chiều cao mét bị quên nhân 100 sẽ lọt
    # qua mọi phép kiểm khác và cho ra BMI gấp 10 000 lần — đúng lỗi đang có
    # trong cột `BMI` của tệp nguồn.
    if not 100.0 <= cao_cm <= 250.0:
        raise LoiNap(
            f"{ma}: chiều cao quy đổi ra {cao_cm} cm, ngoài khoảng 100–250. "
            f"`Height` trong tệp nguồn phải tính bằng MÉT."
        )
    if not 20.0 <= can <= 300.0:
        raise LoiNap(f"{ma}: cân nặng {can} kg ngoài khoảng 20–300")
    if not 1 <= tuoi_nam <= 120:
        raise LoiNap(f"{ma}: tuổi quy đổi ra {tuoi_nam}, ngoài khoảng 1–120")

    gioi = GIOI[h["Gender"]]
    van_dong = FAF_SANG_VAN_DONG[faf_lam_tron]
    muc_tieu = NHAN_SANG_MUC_TIEU[h["NObeyesdad"]]
    ngay_sinh = ngay_sinh_tu_tuoi(tuoi_nam, chi_so, hom_nay)

    # Bước 1 lấy từ `gen_buoc1_cases` — bản tham chiếu Python đã được
    # `check_be_parity.py` đối chiếu với C# và Dart. Viết lại ở đây là tạo
    # bản thứ tư của cùng một công thức, tức tạo chỗ thứ tư để lệch.
    d_can = Decimal(str(can))
    d_cao = Decimal(str(cao_cm))
    gt_bmr = bmr(gioi, d_can, d_cao, tuoi_nam)
    gt_tdee = tdee(gt_bmr, van_dong)
    gt_han_muc = han_muc(gt_tdee, gt_bmr, muc_tieu)

    return {
        "user_id": ma,
        "gender": gioi,
        "date_of_birth": ngay_sinh,
        "height_cm": cao_cm,
        "weight_kg": can,
        "activity_level": van_dong,
        "goal": muc_tieu,
        "bmr_kcal": tron(gt_bmr),
        "tdee_kcal": tron(gt_tdee),
        "daily_calories_target": tron(gt_han_muc),
        "_tuoi": tuoi_nam,
        "_nhan_beo": h["NObeyesdad"],
        "_faf": faf,
    }


def doc_ho_so(hom_nay: date) -> list[dict[str, Any]]:
    if not HO_SO_NGUON.exists():
        raise LoiNap(f"không thấy {HO_SO_NGUON}")
    with HO_SO_NGUON.open(encoding="utf-8-sig", newline="") as f:
        hang = list(csv.DictReader(f))
    if not hang:
        raise LoiNap(f"{HO_SO_NGUON} không có dòng dữ liệu nào")
    can = {"user_id", "Gender", "Age", "Height", "Weight", "FAF", "NObeyesdad"}
    thieu = can - set(hang[0])
    if thieu:
        raise LoiNap(f"{HO_SO_NGUON.name} thiếu cột: {', '.join(sorted(thieu))}")

    dau_tien: dict[str, dict[str, str]] = {}
    for h in hang:
        dau_tien.setdefault(h["user_id"], h)
    return [
        quy_doi_ho_so(dau_tien[u], i, hom_nay)
        for i, u in enumerate(sorted(dau_tien))
    ]


def doc_hanh_vi(mon_theo_id: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    """`user_id` → danh sách `(food_id, action)` theo đúng thứ tự trong tệp."""
    if not HANH_VI.exists():
        raise LoiNap(
            f"không thấy {HANH_VI}.\n"
            "Sinh trước bằng: python tools/sinh_khau_vi.py --ghi"
        )
    with HANH_VI.open(encoding="utf-8-sig", newline="") as f:
        doc = csv.DictReader(f)
        thieu = {"user_id", "ma_mon", "lua_chon"} - set(doc.fieldnames or ())
        if thieu:
            raise LoiNap(f"{HANH_VI.name} thiếu cột: {', '.join(sorted(thieu))}")
        luot: dict[str, list[tuple[str, str]]] = {}
        thay: dict[str, set[str]] = {}
        for stt, d in enumerate(doc, start=2):
            u = d["user_id"].strip()
            ma = d["ma_mon"].strip()
            chon = d["lua_chon"].strip().lower()
            if chon not in LUA_CHON:
                raise LoiNap(
                    f"  dòng {stt}: `lua_chon` = {chon!r} không hợp lệ; "
                    f"phải là một trong: {', '.join(LUA_CHON)}"
                )
            if ma not in mon_theo_id:
                raise LoiNap(
                    f"  dòng {stt}: `ma_mon` = {ma} không có trong `foods` "
                    f"đang hoạt động. Bộ món đã đổi — sinh lại deck và dữ liệu."
                )
            if ma in thay.setdefault(u, set()):
                raise LoiNap(f"  dòng {stt}: {u} có hai dòng cho cùng món {ma}")
            thay[u].add(ma)
            luot.setdefault(u, []).append((ma, LUA_CHON[chon]))
    if not luot:
        raise LoiNap(f"{HANH_VI.name} không có lượt vuốt nào")
    return luot


def doc_su_that() -> dict[str, Any]:
    if not SU_THAT.exists():
        raise LoiNap(
            f"không thấy {SU_THAT}.\n"
            "Sinh trước bằng: python tools/sinh_khau_vi.py --ghi"
        )
    return json.loads(SU_THAT.read_text(encoding="utf-8"))


# ── Bộ lọc F1 ─────────────────────────────────────────────────────────────


def loc_f1(
    cn,
    su_that: dict[str, Any],
    luot: dict[str, list[tuple[str, str]]],
    mon_theo_id: dict[str, Any],
) -> tuple[
    dict[str, list[tuple[str, str]]],
    dict[str, list[tuple[str, str, list[str]]]],
    dict[str, list[int]],
]:
    """Loại các lượt vi phạm ràng buộc cứng, theo bệnh lý của từng người.

    Chạy **trước** khi dựng vector sở thích, không chỉ trước khi ghi
    `interactions`: lọc sau khi dựng thì vector vẫn mang nguyên phần ràng
    buộc giả dạng khẩu vị, và `n_signals` vẫn đếm cả những lượt đó nên giai
    đoạn cũng bị tính sai.

    Với dữ liệu mô phỏng hiện tại thì `benh_ly` rỗng cho cả 50 người, nên
    hàm này trả về nguyên đầu vào. Nó vẫn đi qua **đúng** đường mà
    `import_swipes.py` đi, để khi có bước gán bệnh lý mô phỏng thì không
    phải viết lại chỗ này — và để hai đường nhập không thể lệch nhau.

    Trả về `(còn lại, bị loại, mã bệnh lý theo người)`.
    """
    moi_ten = sorted(
        {
            b
            for u in luot
            for b in (su_that["nguoi"].get(u, {}).get("benh_ly") or [])
        }
    )
    # Tra một lần cho mọi tên, ở pha kiểm: 50 hồ sơ cùng một mẫu sai thì phải
    # vỡ một lần trước khi ghi, không phải vỡ ở hồ sơ thứ ba mươi.
    kiem_benh_ly(cn, moi_ten)

    giu: dict[str, list[tuple[str, str]]] = {}
    bo: dict[str, list[tuple[str, str, list[str]]]] = {}
    ma_benh: dict[str, list[int]] = {}

    for u, ds in luot.items():
        ten = su_that["nguoi"].get(u, {}).get("benh_ly") or []
        ma_benh[u] = kiem_benh_ly(cn, ten)
        con, loai = loc_theo_f1(cn, ten, ds, mon_theo_id)
        if not con:
            raise LoiNap(
                f"{u}: Bộ lọc F1 loại toàn bộ {len(ds)} lượt — mọi món trong "
                "bộ khảo sát đều vi phạm ràng buộc cứng của người này. Cần "
                "một bộ món khác cho trường hợp này."
            )
        # Đối chiếu với danh sách mà bộ sinh đã ghi vào `khau_vi_that.json`.
        #
        # Hai bên chạy cùng `ly_do_loai` nhưng ở hai thời điểm khác nhau, nên
        # lệch nghĩa là `condition_rules` đã đổi sau khi dữ liệu được sinh —
        # và khi đó dữ liệu mang một ràng buộc khác với ràng buộc mà hệ thống
        # đang thi hành. Nó không gây lỗi ở đâu cả: trình nhập vẫn ghi xong,
        # `build_dataset` vẫn chạy, và phép đo F1 trong `check_mo_phong.py`
        # vẫn in ra một con số — một con số của bộ luật cũ.
        da_ghi = set(su_that["nguoi"].get(u, {}).get("f1_loai") or ())
        vua_tinh = {f for f, _a, _l in loai}
        if da_ghi != vua_tinh:
            raise LoiNap(
                f"{u}: Bộ lọc F1 vừa tính ra {len(vua_tinh)} món bị loại, "
                f"nhưng khau_vi_that.json ghi {len(da_ghi)} món.\n"
                f"`condition_rules` đã đổi sau khi sinh dữ liệu. Sinh lại: "
                "python tools/sinh_khau_vi.py --ghi"
            )

        giu[u] = con
        if loai:
            bo[u] = loai
    return giu, bo, ma_benh


# ── ghi ───────────────────────────────────────────────────────────────────


def dem_da_nap(cn) -> int:
    with cn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) n FROM users WHERE email LIKE %s", (MAU_EMAIL_LIKE,)
        )
        return int(cur.fetchone()["n"])


def xoa_da_nap(cn) -> int:
    """Xóa người dùng của lần nạp trước. `ON DELETE CASCADE` dọn phần còn lại."""
    with cn.cursor() as cur:
        cur.execute("DELETE FROM users WHERE email LIKE %s", (MAU_EMAIL_LIKE,))
        n = cur.rowcount
    cn.commit()
    return n


def ghi(
    cn,
    ho_so: list[dict[str, Any]],
    luot: dict[str, list[tuple[str, str]]],
    kg: KhongGianDacTrung,
    mon_theo_id: dict[str, Any],
    ma_benh: dict[str, list[int]],
    ngay_nap: date,
) -> list[dict[str, Any]]:
    """Ghi cả 50 người trong MỘT giao dịch."""
    goc = datetime.combine(ngay_nap, datetime.min.time()).replace(hour=9)
    ra: list[dict[str, Any]] = []

    with cn.cursor() as cur:
        for i, hs in enumerate(ho_so):
            ma = hs["user_id"]
            user_id = str(uuid.uuid5(KHONG_GIAN_TEN, f"user:{ma}"))
            session_id = str(uuid.uuid5(KHONG_GIAN_TEN, f"session:{ma}"))
            email = MAU_EMAIL.format(ma)

            cur.execute(
                "INSERT INTO users (id, email, password_hash, display_name, "
                "onboarding_completed_at) VALUES (%s, %s, %s, %s, %s)",
                (
                    user_id,
                    email,
                    BAM_KHONG_DUNG_DUOC,
                    f"Mô phỏng {ma}",
                    datetime.combine(ngay_nap, datetime.min.time()),
                ),
            )
            cur.execute(
                "INSERT INTO health_profiles (id, user_id, gender, "
                "date_of_birth, height_cm, weight_kg, activity_level, goal, "
                "bmr_kcal, tdee_kcal, daily_calories_target) "
                "VALUES (UUID(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    user_id,
                    hs["gender"],
                    hs["date_of_birth"],
                    hs["height_cm"],
                    hs["weight_kg"],
                    hs["activity_level"],
                    hs["goal"],
                    hs["bmr_kcal"],
                    hs["tdee_kcal"],
                    hs["daily_calories_target"],
                ),
            )

            for cid in ma_benh.get(ma, []):
                cur.execute(
                    "INSERT INTO user_conditions (id, user_id, condition_id, "
                    "severity) VALUES (UUID(), %s, %s, %s)",
                    (user_id, cid, SEVERITY_PHIEU),
                )

            # Mỗi người một phiên, các phiên cách nhau 1 phút, trong phiên
            # thì các lượt cách nhau 1 giây và giữ đúng thứ tự trong tệp:
            # `profile_snapshot` khi dựng tập huấn luyện phát lại lịch sử
            # theo thứ tự thời gian, nên thứ tự này là dữ liệu, không phải
            # chi tiết trình bày.
            bat_dau = goc + timedelta(minutes=i)
            for j, (food_id, action) in enumerate(luot[ma]):
                cur.execute(
                    "INSERT INTO interactions (id, user_id, food_id, action, "
                    "session_id, interacted_at) "
                    "VALUES (UUID(), %s, %s, %s, %s, %s)",
                    (
                        user_id,
                        food_id,
                        action,
                        session_id,
                        bat_dau + timedelta(seconds=j),
                    ),
                )

            ho = dung_ho_so(kg, [(mon_theo_id[f], a) for f, a in luot[ma]])
            # `alpha` ghi đúng `alpha(n_signals)`, không ghi 0. `ml/serve.py`
            # tính lại α lúc phục vụ nên số 0 không làm vỡ gì khi chạy, nhưng
            # cột này là thứ các truy vấn thống kê của Chương 3 đọc tới — để
            # 0 thì bảng α trong báo cáo toàn số 0 mà hệ thống thì không chạy
            # bằng 0.
            cur.execute(
                "INSERT INTO user_preference_profiles (user_id, "
                "feature_version, weights, sum_abs_weight, n_signals, stage, "
                "alpha) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    user_id,
                    FEATURE_VERSION,
                    json.dumps(list(ho.weights)),
                    ho.sum_abs_weight,
                    ho.n_signals,
                    giai_doan(ho.n_signals),
                    round(alpha(ho.n_signals), 3),
                ),
            )
            ra.append(
                {
                    "ma": ma,
                    "user_id": user_id,
                    "email": email,
                    "n_signals": ho.n_signals,
                    "stage": giai_doan(ho.n_signals),
                    "alpha": alpha(ho.n_signals),
                }
            )

    cn.commit()
    return ra


# ── báo cáo ───────────────────────────────────────────────────────────────


def xem_truoc(
    ho_so: list[dict[str, Any]],
    luot: dict[str, list[tuple[str, str]]],
    kg: KhongGianDacTrung,
    mon_theo_id: dict[str, Any],
) -> None:
    print(f"{len(ho_so)} hồ sơ · {sum(len(v) for v in luot.values())} lượt vuốt")

    for ten, khoa in (
        ("giới tính", "gender"),
        ("mức vận động", "activity_level"),
        ("mục tiêu", "goal"),
    ):
        d = collections.Counter(h[khoa] for h in ho_so)
        print(f"  {ten:<14} " + "  ".join(f"{k}={v}" for k, v in sorted(d.items())))

    bmi = sorted(h["weight_kg"] / (h["height_cm"] / 100) ** 2 for h in ho_so)
    hm = sorted(h["daily_calories_target"] for h in ho_so)
    t = sorted(h["_tuoi"] for h in ho_so)
    print(
        f"  tuổi           {t[0]}–{t[-1]} (trung vị {t[len(t)//2]})\n"
        f"  BMI            {bmi[0]:.1f}–{bmi[-1]:.1f} "
        f"(trung vị {bmi[len(bmi)//2]:.1f})\n"
        f"  hạn mức kcal   {hm[0]}–{hm[-1]} (trung vị {hm[len(hm)//2]})"
    )

    gd = collections.Counter()
    for h in ho_so:
        ho = dung_ho_so(kg, [(mon_theo_id[f], a) for f, a in luot[h["user_id"]]])
        gd[giai_doan(ho.n_signals)] += 1
    print("  giai đoạn      " + "  ".join(f"{k}={v}" for k, v in sorted(gd.items())))

    # Hai bậc không với tới được từ thang đo nguồn — nói ra chứ không để
    # người đọc bảng trên tự đoán vì sao chúng vắng mặt.
    print(
        "\n  `very_active` và `healthy_eating` vắng mặt theo đúng thiết kế: "
        "thang\n  đo `FAF` không với tới bậc trên, và `healthy_eating` là "
        "lựa chọn người\n  dùng tự khai, không suy ra từ nhãn cân nặng. Xem "
        "đầu tệp."
    )


def main() -> int:
    in_utf8()
    bo = argparse.ArgumentParser(description=__doc__)
    bo.add_argument("--db", default=None)
    bo.add_argument("--apply", action="store_true", help="ghi vào CSDL")
    bo.add_argument(
        "--xoa", action="store_true", help="xóa lần nạp trước rồi dừng"
    )
    t = bo.parse_args()

    cn = ket_noi(t.db)
    try:
        if t.xoa:
            n = xoa_da_nap(cn)
            print(f"Đã xóa {n} người dùng mô phỏng (cùng mọi dòng phụ thuộc).")
            return 0

        mon, _ = nap_mon(cn)
        kg = KhongGianDacTrung.tu_mon(mon)
        mon_theo_id = {m.id: m for m in mon}
        ngay_nap = date.today()

        try:
            su_that = doc_su_that()
            if su_that.get("feature_version") != FEATURE_VERSION:
                raise LoiNap(
                    f"lệch phiên bản đặc trưng: dữ liệu mô phỏng sinh trên "
                    f"{su_that.get('feature_version')}, mã hiện là "
                    f"{FEATURE_VERSION}.\nSinh lại: "
                    "python tools/sinh_khau_vi.py --ghi"
                )
            ho_so = doc_ho_so(ngay_nap)
            luot = doc_hanh_vi(mon_theo_id)

            thieu_luot = [h["user_id"] for h in ho_so if h["user_id"] not in luot]
            if thieu_luot:
                raise LoiNap(
                    f"{len(thieu_luot)} người có hồ sơ nhưng không có lượt "
                    f"vuốt nào: {', '.join(thieu_luot[:5])}"
                )
            thua_luot = set(luot) - {h["user_id"] for h in ho_so}
            if thua_luot:
                raise LoiNap(
                    f"{len(thua_luot)} người có lượt vuốt nhưng không có hồ "
                    f"sơ: {', '.join(sorted(thua_luot)[:5])}"
                )
            luot, bi_loai, ma_benh = loc_f1(cn, su_that, luot, mon_theo_id)
        except (LoiNap, LoiPhieu) as e:
            print(f"Không nạp được.\n{e}", file=sys.stderr)
            return 1

        da_co = dem_da_nap(cn)
        if da_co:
            print(
                f"Đã có {da_co} người dùng mô phỏng trong CSDL. Không nạp "
                "chồng lên.\nXóa trước rồi nạp lại: "
                "python tools/import_mo_phong.py --xoa",
                file=sys.stderr,
            )
            return 1

        print(f"Nguồn: {HANH_VI.relative_to(ROOT)}")
        print(f"       {HO_SO_NGUON.relative_to(ROOT)}  (chỉ các cột hồ sơ)")
        print(f"       {SU_THAT.relative_to(ROOT)}  seed {su_that['tham_so']['seed']}")
        print()
        xem_truoc(ho_so, luot, kg, mon_theo_id)
        n_bo = sum(len(v) for v in bi_loai.values())
        n_giu = sum(len(v) for v in luot.values())
        if n_bo:
            # Gom theo lý do, không liệt kê từng món: một người thuần chay bị
            # loại 22 món vì ĐÚNG MỘT quy tắc, và in 22 dòng giống nhau thì
            # che mất chuyện đó.
            theo_ly_do: collections.Counter[str] = collections.Counter()
            for ds in bi_loai.values():
                for _f, _a, ly_do in ds:
                    theo_ly_do[ly_do[0]] += 1
            print(
                f"\n  Bộ lọc F1 loại {n_bo}/{n_bo + n_giu} lượt "
                f"trên {len(bi_loai)} người:"
            )
            for ly, dem_ly in theo_ly_do.most_common():
                print(f"      {ly} → {dem_ly} lượt")
            print(
                "    Những lượt này KHÔNG được ghi và KHÔNG vào vector sở "
                "thích:\n    chúng là ràng buộc, không phải khẩu vị."
            )
        else:
            print(
                f"\n  Bộ lọc F1 loại 0/{n_giu} lượt — `ObesityDataSet` không "
                "có cột bệnh lý\n  nào, nên không ai có ràng buộc cứng."
            )

        if not t.apply:
            print("\nXem trước. Thêm --apply để ghi vào CSDL.")
            return 0

        ra = ghi(cn, ho_so, luot, kg, mon_theo_id, ma_benh, ngay_nap)
        n_luot = sum(len(v) for v in luot.values())
        print(
            f"\nĐã ghi {len(ra)} người · {n_luot} dòng `interactions` · "
            f"{len(ra)} dòng `health_profiles` và "
            f"`user_preference_profiles`."
        )
        print("Bước tiếp: python -m ml.build_dataset --version v1")
        return 0
    finally:
        cn.close()


if __name__ == "__main__":
    raise SystemExit(main())
