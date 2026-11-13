#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bộ dựng tập dữ liệu — bảy nguồn tín hiệu → `ml_training_samples`.

`docs/ML_PIPELINE.md` §9 là đặc tả. Mỗi nguồn cho một **nhãn** và một **trọng
số**, và hai cột đó trả lời hai câu khác nhau:

    label          — người dùng thích món này đến mức nào?
    sample_weight  — ta tin con số đó đến mức nào?

Một đánh giá 5 sao sau khi ăn (trọng số 1,0) đáng tin hơn hẳn một suất bị bỏ
không ăn (0,3): bỏ bữa là tín hiệu **nhập nhằng** — có thể do không thích, có
thể do hôm đó không có thời gian nấu.

Ba điều tệp này làm mà đọc SQL không thấy ra:

**1. `profile_snapshot` chống rò rỉ dữ liệu.** Đặc trưng chéo `cos(p_u, vᵢ)`
là đầu vào của mô hình. Nếu dùng `p_u` *hiện tại* — vector đã được cập nhật
bởi chính tín hiệu đang xét — thì đặc trưng đã chứa thông tin về nhãn, và kết
quả đánh giá sẽ rất đẹp mà vô dụng khi chạy thật. Nên hồ sơ Rocchio được
**phát lại theo thứ tự thời gian** cho từng người, và ảnh chụp của một mẫu
chỉ gồm những lượt vuốt **trước** nó.

**2. Chia tập theo NGƯỜI DÙNG, không theo mẫu.** Nếu cùng một người xuất
hiện ở cả tập huấn luyện và tập kiểm tra thì mô hình đã thấy khẩu vị của họ
và con số đánh giá bị thổi phồng.

**3. Món riêng tư không vào tập.** Số liệu dinh dưỡng của chúng do người dùng
tự khai; nhiễm vào mô hình dùng chung là làm hại mọi người dùng khác
(`ML_PIPELINE.md` §4.2).

Chạy:
    python -m ml.build_dataset --version d1              # chạy thử, không ghi
    python -m ml.build_dataset --version d1 --apply      # ghi vào CSDL
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Sequence

from .db import in_utf8, ket_noi
from .f1_filter import dieu_kien_cua_nguoi_dung, ly_do_loai
from .features import KhongGianDacTrung, Mon, nap_mon
from .rocchio import HoSoSoThich, dung_ho_so, ho_so_rong

#: Nhãn và trọng số theo nguồn. `feedback` không có ở đây vì nhãn của nó suy
#: từ số sao — xem `nhan_tu_sao`.
NHAN_THEO_NGUON: dict[str, tuple[float, float]] = {
    #  nguồn            nhãn   trọng số
    "diary": (0.800, 0.900),
    "plan_kept": (0.700, 0.600),
    "plan_replaced": (0.150, 0.600),
    "plan_skipped": (0.300, 0.300),
    "random_neg": (0.100, 0.200),
}

#: Nhãn theo hành động vuốt. `unknown` **không có mặt** — nó bị loại khỏi tập
#: thay vì gán 0,5, vì gán 0,5 là bịa ra một nhãn người dùng chưa từng cung
#: cấp rồi huấn luyện mô hình trên nhãn bịa đó (`ML_PIPELINE.md` §9.2).
NHAN_VUOT: dict[str, float] = {"like": 0.900, "neutral": 0.500, "dislike": 0.000}
TRONG_SO_VUOT = 0.700

#: `meal_plan_items.status` → nguồn. `suggested` không có mặt: người dùng
#: chưa quyết định gì với suất đó nên nó không phải tín hiệu. `eaten` gộp vào
#: `plan_kept` — đã ăn là một dạng giữ suất, chỉ mạnh hơn.
NGUON_THEO_TRANG_THAI = {
    "kept": "plan_kept",
    "eaten": "plan_kept",
    "replaced": "plan_replaced",
    "skipped": "plan_skipped",
}


def nhan_tu_sao(rating: int) -> float:
    """5★ → 1,000 · 4★ → 0,750 · 3★ → 0,500 · 2★ → 0,250 · 1★ → 0,000."""
    if not 1 <= rating <= 5:
        raise ValueError(f"rating phải trong 1–5, nhận {rating}")
    return round((rating - 1) / 4, 3)


@dataclass
class Mau:
    """Một dòng của `ml_training_samples`, trước khi gán fold và ảnh chụp."""

    user_id: str
    food_id: str
    source: str
    label: float
    sample_weight: float
    collected_at: datetime
    context_meal_type: str | None = None
    #: Id của dòng gốc. Chỉ dùng cho `swipe`, để loại đúng lượt vuốt **của
    #: chính mẫu này** khỏi ảnh chụp hồ sơ mà vẫn giữ các lượt cùng giây.
    nguon_id: str | None = None
    #: `interactions.action` nguyên văn, chỉ có ở mẫu `swipe`. Giữ riêng vì
    #: Rocchio cần *hành động*, trong khi `label` đã là nhãn đã quy đổi —
    #: suy ngược từ nhãn về hành động là một phép tra dễ vỡ khi nhãn đổi.
    action: str | None = None


# ── Thu tín hiệu từng nguồn ───────────────────────────────────────────
#
# Mọi truy vấn đều kèm `f.owner_id IS NULL`: món riêng tư không vào tập huấn
# luyện của mô hình toàn cục.

_CHUNG = "JOIN foods f ON f.id = {cot} AND f.owner_id IS NULL AND f.is_active = 1"


def tu_feedback(cn) -> list[Mau]:
    """`feedbacks` — tín hiệu đáng tin nhất, trọng số 1,0.

    Một người có thể đánh giá cùng một món nhiều lần. Giữ **lần gần nhất**:
    ý kiến mới nhất là ý kiến hiện tại của họ.
    """
    sql = f"""
        SELECT fb.id, fb.user_id, fb.food_id, fb.rating, fb.created_at
        FROM feedbacks fb
        {_CHUNG.format(cot="fb.food_id")}
        ORDER BY fb.created_at, fb.id
    """
    with cn.cursor() as cur:
        cur.execute(sql)
        return [
            Mau(
                user_id=d["user_id"],
                food_id=d["food_id"],
                source="feedback",
                label=nhan_tu_sao(int(d["rating"])),
                sample_weight=1.000,
                collected_at=d["created_at"],
                nguon_id=d["id"],
            )
            for d in cur.fetchall()
        ]


def tu_vuot(cn) -> list[Mau]:
    """`interactions` — lượt vuốt. `unknown` bị loại ngay trong SQL."""
    cho = ", ".join(["%s"] * len(NHAN_VUOT))
    sql = f"""
        SELECT i.id, i.user_id, i.food_id, i.action, i.interacted_at
        FROM interactions i
        {_CHUNG.format(cot="i.food_id")}
        WHERE i.action IN ({cho})
        ORDER BY i.interacted_at, i.id
    """
    with cn.cursor() as cur:
        cur.execute(sql, tuple(NHAN_VUOT))
        return [
            Mau(
                user_id=d["user_id"],
                food_id=d["food_id"],
                source="swipe",
                label=NHAN_VUOT[d["action"]],
                sample_weight=TRONG_SO_VUOT,
                collected_at=d["interacted_at"],
                nguon_id=d["id"],
                action=d["action"],
            )
            for d in cur.fetchall()
        ]


def tu_nhat_ky(cn) -> list[Mau]:
    """`food_diary` — đã ăn thật.

    Hạn chế đã biết: ăn lại nhiều lần là tín hiệu **mạnh hơn** ăn một lần,
    nhưng lược đồ không có cột đếm số lần, và §9.1 quy định `sample_weight`
    mã hóa **độ tin cậy** chứ không mã hóa mức độ thích. Nên ở đây chỉ giữ
    lần gần nhất; số lần lặp bị bỏ. Muốn dùng thì phải thêm cột, không phải
    tự đặt ra một công thức nhân trọng số.
    """
    nhan, trong_so = NHAN_THEO_NGUON["diary"]
    sql = f"""
        SELECT fd.id, fd.user_id, fd.food_id, fd.meal_type,
               fd.created_at, fd.ate_on
        FROM food_diary fd
        {_CHUNG.format(cot="fd.food_id")}
        ORDER BY fd.ate_on, fd.created_at, fd.id
    """
    with cn.cursor() as cur:
        cur.execute(sql)
        return [
            Mau(
                user_id=d["user_id"],
                food_id=d["food_id"],
                source="diary",
                label=nhan,
                sample_weight=trong_so,
                collected_at=d["created_at"],
                context_meal_type=d["meal_type"],
                nguon_id=d["id"],
            )
            for d in cur.fetchall()
        ]


def tu_thuc_don(cn) -> list[Mau]:
    """`meal_plan_items` — giữ suất, đổi suất, bỏ suất.

    Ba nguồn khác nhau nên cùng một cặp (người, món) có thể sinh ba dòng hợp
    lệ: họ giữ suất hôm nay, đổi suất hôm khác. Đó đúng là ba tín hiệu độc
    lập, và `uq_sample` có `source` trong khóa chính vì vậy.
    """
    cho = ", ".join(["%s"] * len(NGUON_THEO_TRANG_THAI))
    sql = f"""
        SELECT mpi.id, mp.user_id, mpi.food_id, mpi.meal_type, mpi.status,
               COALESCE(mpi.replaced_at, mpi.created_at) AS luc
        FROM meal_plan_items mpi
        JOIN meal_plans mp ON mp.id = mpi.meal_plan_id
        {_CHUNG.format(cot="mpi.food_id")}
        WHERE mpi.status IN ({cho})
        ORDER BY luc, mpi.id
    """
    with cn.cursor() as cur:
        cur.execute(sql, tuple(NGUON_THEO_TRANG_THAI))
        ket_qua: list[Mau] = []
        for d in cur.fetchall():
            nguon = NGUON_THEO_TRANG_THAI[d["status"]]
            nhan, trong_so = NHAN_THEO_NGUON[nguon]
            ket_qua.append(
                Mau(
                    user_id=d["user_id"],
                    food_id=d["food_id"],
                    source=nguon,
                    label=nhan,
                    sample_weight=trong_so,
                    collected_at=d["luc"],
                    context_meal_type=d["meal_type"],
                    nguon_id=d["id"],
                )
            )
        return ket_qua


def tu_am_ngau_nhien(
    cn,
    *,
    da_hien: dict[str, set[str]],
    so_moi_nguoi: int | None,
    ty_le: float,
    seed: int,
    moc_thoi_gian: dict[str, datetime],
) -> list[Mau]:
    """`random_neg` — món **chưa từng hiển thị** cho người đó.

    Vì sao cần. Không có mẫu âm, mô hình chỉ thấy những món hệ thống đã chọn
    để hiển thị, và nó học cách tái tạo lại chính bộ lọc của hệ thống thay vì
    học khẩu vị. Nhãn 0,100 với trọng số 0,200: đây là **phỏng đoán** rằng
    người dùng không đặc biệt thích một món lấy ngẫu nhiên, và trọng số thấp
    nói rằng đừng tin phỏng đoán đó quá.

    Chỉ lấy từ món công khai đang hoạt động. Sinh bằng `random.Random(seed)`
    nên chạy lại cho đúng cùng một tập — một tập dữ liệu không tái lập được
    thì không so sánh được hai mô hình với nhau.

    ## Số mẫu âm phải TỈ LỆ theo số tín hiệu, không được cố định

    Bản đầu lấy một số cố định (20) cho mọi người. Nó tạo ra một tương quan
    giả mà ba thuật toán đều bám vào ngay lần chạy đầu có dữ liệu:
    `nguoi.n_tin_hieu` thành **đặc trưng mạnh nhất** của cả ba (hệ số −0,833
    ở hồi quy logistic, độ quan trọng 0,188 và 0,305 ở hai mô hình cây).

    Cơ chế: với số mẫu âm cố định, tỉ lệ mẫu nhãn 0 của một người là
    `20 / (20 + n)` — một hàm **giảm đơn điệu** theo số tín hiệu. Đo trên 50
    người mô phỏng, tỉ lệ `random_neg` chạy từ 0,370 ở `n = 34` xuống 0,318 ở
    `n = 43`, và `corr(n_signals, nhãn)` là +0,215 trong nhóm `swipe` nhưng
    +0,000 trong nhóm `random_neg` — dấu hiệu của tương quan nằm ở **tỉ lệ
    pha trộn giữa hai nguồn**, không nằm trong tín hiệu nào.

    Chỉ phương án `ml` đọc đặc trưng nên chỉ nó được lợi, và phần lợi đó
    **không chuyển sang lúc phục vụ thật** — lúc đó không có bước bốc mẫu âm
    nào. Tức là nó làm hàng `ml` trong bảng so sánh của Chương 3 cao hơn thực
    chất, đúng ở cột mà cả đồ án phải chứng minh.

    Lấy theo tỉ lệ thì `so_am / (so_am + n) = ty_le / (1 + ty_le)` — một hằng
    số, không còn phụ thuộc `n`. `ty_le = 0,5` giữ cân bằng nhãn gần như cũ
    (49,1% nhãn dương với 20 mẫu cố định trên ~39 tín hiệu).

    `so_moi_nguoi` khác `None` thì quay về số cố định. Giữ đường đó vì
    `check_ml_e2e.py` cần một tập mẫu **đếm trước được** để đối chiếu, và một
    bộ kiểm đổi số mẫu theo số tín hiệu của dữ liệu giả thì không khẳng định
    được gì.

    ## Mẫu âm không được lấy món mà Bộ lọc F1 đã chặn

    `ml/serve.py` chạy F1 **trước** mọi phép chấm điểm, nên món bị F1 chặn
    không bao giờ là ứng viên lúc phục vụ. Đưa chúng vào tập huấn luyện là
    huấn luyện trên một phân phối mà mô hình sẽ không bao giờ gặp — và chúng
    là mẫu âm **quá dễ**: người ăn thuần chay thì mọi món thịt đều là nhãn 0,
    đoán được mà không cần biết gì về khẩu vị. Đo trên 50 người mô phỏng
    trước khi chặn: **82/880 mẫu âm (9,3%)** là món mà F1 đã loại cho đúng
    người đó.

    Nó cũng là chuyện phân vai: §4 nói F1 là tầng an toàn đặt trước mọi mô
    hình. Để mô hình học lại cùng phép loại đó là bắt nó làm việc của tầng
    khác, bằng một cơ chế mềm hơn — và đổi lấy một con số đánh giá cao hơn
    thực chất.
    """
    if so_moi_nguoi is None and ty_le <= 0:
        raise ValueError("phải cho `so_moi_nguoi` hoặc `ty_le` dương")
    nhan, trong_so = NHAN_THEO_NGUON["random_neg"]
    with cn.cursor() as cur:
        cur.execute(
            "SELECT id FROM foods WHERE owner_id IS NULL AND is_active = 1 "
            "ORDER BY id"
        )
        tat_ca = [d["id"] for d in cur.fetchall()]

    ket_qua: list[Mau] = []
    # Nhớ theo bộ điều kiện, không theo người: 50 người thường chỉ có vài bộ
    # điều kiện khác nhau, và `ly_do_loai` quét `condition_rules` × `foods`.
    nho_f1: dict[tuple[tuple[int, str], ...], frozenset[str]] = {}
    for user_id in sorted(da_hien):
        dieu_kien = dieu_kien_cua_nguoi_dung(cn, user_id)
        khoa = tuple(sorted((d.condition_id, d.severity) for d in dieu_kien))
        if khoa not in nho_f1:
            nho_f1[khoa] = (
                frozenset(ly_do_loai(cn, dieu_kien=dieu_kien, chi_mon_chung=True))
                if dieu_kien
                else frozenset()
            )
        f1_chan = nho_f1[khoa]

        # Hạt giống trộn thêm mã người dùng: hai người khác nhau nhận hai
        # tập âm khác nhau, nhưng chạy lại thì mỗi người vẫn nhận đúng tập
        # của mình kể cả khi số người dùng thay đổi.
        rng = random.Random(f"{seed}:{user_id}")
        con_lai = [
            f
            for f in tat_ca
            if f not in da_hien[user_id] and f not in f1_chan
        ]
        rng.shuffle(con_lai)
        # Ít nhất 1: một người chỉ có 1 tín hiệu vẫn phải có mẫu âm, nếu
        # không thì mọi mẫu của họ cùng một nhãn.
        lay = (
            so_moi_nguoi
            if so_moi_nguoi is not None
            else max(1, round(ty_le * len(da_hien[user_id])))
        )
        for food_id in con_lai[:lay]:
            ket_qua.append(
                Mau(
                    user_id=user_id,
                    food_id=food_id,
                    source="random_neg",
                    label=nhan,
                    sample_weight=trong_so,
                    collected_at=moc_thoi_gian[user_id],
                )
            )
    return ket_qua


# ── Gộp, chống nhân đôi ───────────────────────────────────────────────


def chong_nhan_doi(mau: Iterable[Mau]) -> tuple[list[Mau], int]:
    """Giữ **một** dòng cho mỗi `(user_id, food_id, source)` — dòng mới nhất.

    `uq_sample (dataset_version, user_id, food_id, source)` là ràng buộc
    tương ứng trong lược đồ. Không có nó thì mỗi lần sinh lại tập dữ liệu sẽ
    nhân đôi toàn bộ mẫu và mô hình huấn luyện trên dữ liệu trùng lặp mà
    không ai biết. Chống ở đây nữa để script báo được **đã gộp bao nhiêu**
    thay vì để CSDL báo lỗi 1062 và dừng.
    """
    giu: dict[tuple[str, str, str], Mau] = {}
    bo = 0
    for m in mau:
        khoa = (m.user_id, m.food_id, m.source)
        cu = giu.get(khoa)
        if cu is None:
            giu[khoa] = m
        else:
            bo += 1
            if m.collected_at >= cu.collected_at:
                giu[khoa] = m
    return list(giu.values()), bo


# ── Ảnh chụp hồ sơ, chống rò rỉ ───────────────────────────────────────


def gan_anh_chup(
    mau: Sequence[Mau],
    luot_vuot: Sequence[Mau],
    kg: KhongGianDacTrung,
    mon_theo_id: dict[str, Mon],
) -> dict[str, dict[str, Any]]:
    """Tính `profile_snapshot` cho từng mẫu — hồ sơ **trước** tín hiệu đó.

    Phát lại lịch sử vuốt của từng người theo thứ tự thời gian, và với mỗi
    mẫu lấy hồ sơ dựng từ những lượt vuốt đứng trước nó.

    Chỗ tinh tế: `DATETIME` của MySQL chỉ tới giây, mà một phiên vuốt
    onboarding sinh hàng chục lượt trong vài giây. Nếu cắt theo
    `thời_gian < thời_gian_mẫu` thì mọi lượt **cùng giây** cũng bị cắt oan;
    nếu cắt theo `<=` thì chính lượt vuốt của mẫu đó lọt vào ảnh chụp — đúng
    cái rò rỉ cần tránh. Nên:

    · mẫu `swipe` — cắt theo `<=` rồi **loại riêng dòng của chính nó** theo
      `nguon_id`, nhờ vậy các lượt cùng giây vẫn được giữ;
    · mẫu nguồn khác — cắt theo `<=`, vì một lượt vuốt cùng giây là tín hiệu
      *khác*, không phải nhãn đang xét.
    """
    vuot_theo_nguoi: dict[str, list[Mau]] = {}
    for v in luot_vuot:
        vuot_theo_nguoi.setdefault(v.user_id, []).append(v)
    for ds in vuot_theo_nguoi.values():
        ds.sort(key=lambda m: (m.collected_at, m.nguon_id or ""))

    anh_chup: dict[str, dict[str, Any]] = {}

    for user_id, ds_mau in _nhom_theo_nguoi(mau).items():
        ds_vuot = vuot_theo_nguoi.get(user_id, [])
        ds_mau.sort(key=lambda m: (m.collected_at, m.nguon_id or ""))

        # Tiền tố tăng dần: các lượt vuốt tới thời điểm đang xét. Dựng lại
        # hồ sơ từ đầu mỗi lần là O(n²) trên mỗi người; với ~30 lượt thì
        # không đáng tối ưu thêm, và dựng lại từ đầu thì chắc chắn trùng kết
        # quả với bản Dart.
        i = 0
        tien_to: list[Mau] = []
        for m in ds_mau:
            while i < len(ds_vuot) and ds_vuot[i].collected_at <= m.collected_at:
                tien_to.append(ds_vuot[i])
                i += 1

            # Loại **đúng dòng gốc** của mẫu này theo id, không loại theo
            # món hay theo thời gian: nhờ vậy các lượt cùng giây vẫn được
            # giữ, và một người vuốt lại cùng một món cũng không bị cắt oan.
            bo_dong = m.nguon_id if m.source == "swipe" else None
            cap = [
                (mon_theo_id[v.food_id], v.action or "neutral")
                for v in tien_to
                if v.nguon_id != bo_dong and v.food_id in mon_theo_id
            ]

            ho_so = dung_ho_so(kg, cap) if cap else ho_so_rong(kg)
            anh_chup[_khoa(m)] = ho_so.to_json()

    return anh_chup


def _nhom_theo_nguoi(mau: Sequence[Mau]) -> dict[str, list[Mau]]:
    theo: dict[str, list[Mau]] = {}
    for m in mau:
        theo.setdefault(m.user_id, []).append(m)
    return theo


def _khoa(m: Mau) -> str:
    return f"{m.user_id}|{m.food_id}|{m.source}"


# ── Chia tập theo người dùng ──────────────────────────────────────────


def chia_theo_nguoi(
    nguoi: Sequence[str], so_fold: int, seed: int
) -> dict[str, int]:
    """Gán mỗi **người dùng** vào một fold.

    Chia theo người, không theo mẫu: nếu cùng một người xuất hiện ở cả tập
    huấn luyện và tập kiểm tra thì mô hình đã thấy khẩu vị của họ và con số
    đánh giá bị thổi phồng.

    Cách gán: **xếp người dùng theo băm, rồi chia lần lượt vòng tròn.** Băm
    cho một thứ tự xác định không phụ thuộc thứ tự dòng trả về từ CSDL; chia
    vòng tròn bảo đảm **các fold lệch nhau nhiều nhất một người**.

    Bản đầu tôi lấy thẳng `băm % số_fold`, vì như vậy thêm một người mới
    không đổi fold của những người đã có. Nhưng nó **không cân**: với 10
    người và 5 fold, thực tế chạy ra fold 0 có 5 người và **fold 4 không có
    ai** — tập kiểm tra rỗng và không huấn luyện được gì. Tính ổn định ấy
    không đáng giá bằng việc mọi fold đều có người, và nó cũng không cần
    thiết: fold được **lưu cùng từng dòng** theo `dataset_version`, nên dựng
    lại đúng tập người đó thì gán lại đúng như cũ, còn tập người khác thì
    đằng nào cũng là một phiên bản tập dữ liệu khác.
    """
    if so_fold < 2:
        raise ValueError("số fold phải từ 2 trở lên")
    if len(nguoi) < so_fold:
        print(
            f"  Lưu ý: chỉ có {len(nguoi)} người dùng cho {so_fold} fold — "
            f"{so_fold - len(nguoi)} fold sẽ rỗng. Giảm --folds hoặc thu "
            f"thêm dữ liệu."
        )
    theo_bam = sorted(
        nguoi, key=lambda u: hashlib.sha256(f"{seed}:{u}".encode()).hexdigest()
    )
    return {u: i % so_fold for i, u in enumerate(theo_bam)}


def nhan_split(fold: int, so_fold: int) -> str:
    """Vai của một fold trong **lần chia tham chiếu**.

    Cột `split` ghi lần chia mặc định để một lần huấn luyện nhanh có sẵn
    train/val/test mà không phải tự chia. Phần kiểm định chéo thì
    `ml/evaluate.py` tự xoay vòng fold và không dùng cột này.

    Với đúng 2 fold thì không có chỗ cho `val`: chia thành train/test và bỏ
    `val`. Nếu vẫn dành một fold cho `val` thì **không còn fold nào là
    train**, và lần chia tham chiếu trở thành vô dụng mà không báo gì.
    """
    if fold == so_fold - 1:
        return "test"
    if so_fold >= 3 and fold == so_fold - 2:
        return "val"
    return "train"


# ── Ghi vào CSDL ──────────────────────────────────────────────────────

SQL_XOA = "DELETE FROM ml_training_samples WHERE dataset_version = %s"

SQL_CHEN = """
INSERT INTO ml_training_samples
    (dataset_version, user_id, food_id, label, sample_weight, source,
     context_meal_type, split, fold, collected_at, profile_snapshot)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def ghi(
    cn,
    version: str,
    mau: Sequence[Mau],
    fold_theo_nguoi: dict[str, int],
    so_fold: int,
    anh_chup: dict[str, dict[str, Any]],
) -> int:
    """Xóa phiên bản cũ rồi chèn lại toàn bộ. Một giao dịch duy nhất.

    Xóa trước là có chủ ý: sinh lại cùng một `dataset_version` nghĩa là
    "dựng lại tập này", nên kết quả phải là **đúng** tập mới, không phải tập
    mới trộn với phần sót của lần trước.
    """
    dong = [
        (
            version,
            m.user_id,
            m.food_id,
            m.label,
            m.sample_weight,
            m.source,
            m.context_meal_type,
            nhan_split(fold_theo_nguoi[m.user_id], so_fold),
            fold_theo_nguoi[m.user_id],
            m.collected_at,
            json.dumps(anh_chup.get(_khoa(m)), ensure_ascii=False),
        )
        for m in mau
    ]
    with cn.cursor() as cur:
        cur.execute(SQL_XOA, (version,))
        da_xoa = cur.rowcount
        if dong:
            cur.executemany(SQL_CHEN, dong)
    cn.commit()
    if da_xoa:
        print(f"Đã xóa {da_xoa} dòng của phiên bản {version!r} trước đó.")
    return len(dong)


# ── Điều phối ─────────────────────────────────────────────────────────


def dung_tap(
    cn,
    *,
    version: str,
    so_am_moi_nguoi: int | None,
    ty_le_am: float,
    so_fold: int,
    seed: int,
    ap_dung: bool,
) -> int:
    mon, bao_cao = nap_mon(cn)
    bao_cao.in_ra()
    kg = KhongGianDacTrung.tu_mon(mon)
    mon_theo_id = {m.id: m for m in mon}
    print()

    feedback = tu_feedback(cn)
    vuot = tu_vuot(cn)
    nhat_ky = tu_nhat_ky(cn)
    thuc_don = tu_thuc_don(cn)

    # Món đã "hiển thị" cho người dùng: mọi món họ từng vuốt, ăn, đánh giá
    # hoặc nhận trong thực đơn. Mẫu âm ngẫu nhiên phải nằm ngoài tập này.
    da_hien: dict[str, set[str]] = {}
    moc_thoi_gian: dict[str, datetime] = {}
    for m in (*feedback, *vuot, *nhat_ky, *thuc_don):
        da_hien.setdefault(m.user_id, set()).add(m.food_id)
        cu = moc_thoi_gian.get(m.user_id)
        if cu is None or m.collected_at > cu:
            moc_thoi_gian[m.user_id] = m.collected_at

    am = tu_am_ngau_nhien(
        cn,
        da_hien=da_hien,
        so_moi_nguoi=so_am_moi_nguoi,
        ty_le=ty_le_am,
        seed=seed,
        moc_thoi_gian=moc_thoi_gian,
    )

    tat_ca = [*feedback, *vuot, *nhat_ky, *thuc_don, *am]
    tat_ca, da_gop = chong_nhan_doi(tat_ca)
    tat_ca.sort(key=lambda m: (m.user_id, m.source, m.food_id))

    print("Tín hiệu theo nguồn:")
    dem: dict[str, int] = {}
    for m in tat_ca:
        dem[m.source] = dem.get(m.source, 0) + 1
    for nguon in (
        "feedback",
        "swipe",
        "diary",
        "plan_kept",
        "plan_replaced",
        "plan_skipped",
        "random_neg",
    ):
        print(f"  {nguon:14} {dem.get(nguon, 0):6}")
    print(f"  {'—' * 14} {'—' * 6}")
    print(f"  {'tổng':14} {len(tat_ca):6}")
    if da_gop:
        print(f"  (đã gộp {da_gop} dòng trùng cặp người–món–nguồn)")

    if not tat_ca:
        print(
            "\nChưa có tín hiệu nào trong CSDL — không có gì để dựng.\n"
            "Phần học máy chờ dữ liệu thu từ người dùng thật; xem "
            "docs/ML_PIPELINE.md §11.3."
        )
        return 0

    nguoi = sorted({m.user_id for m in tat_ca})
    fold_theo_nguoi = chia_theo_nguoi(nguoi, so_fold, seed)
    print(f"\n{len(nguoi)} người dùng, chia {so_fold} fold theo người:")
    for f in range(so_fold):
        cua_f = [u for u in nguoi if fold_theo_nguoi[u] == f]
        so_mau = sum(1 for m in tat_ca if fold_theo_nguoi[m.user_id] == f)
        print(
            f"  fold {f} [{nhan_split(f, so_fold):5}] "
            f"{len(cua_f):3} người, {so_mau:6} mẫu"
        )

    anh_chup = gan_anh_chup(tat_ca, vuot, kg, mon_theo_id)
    co_vector = sum(1 for v in anh_chup.values() if any(v["weights"]))
    print(
        f"\nẢnh chụp hồ sơ: {len(anh_chup)} mẫu, "
        f"{co_vector} mẫu có vector khác rỗng "
        f"({len(anh_chup) - co_vector} mẫu không có lượt vuốt nào trước đó)"
    )

    if not ap_dung:
        print(
            f"\nChạy thử — chưa ghi gì. Thêm --apply để ghi "
            f"{len(tat_ca)} dòng vào ml_training_samples."
        )
        return 0

    n = ghi(cn, version, tat_ca, fold_theo_nguoi, so_fold, anh_chup)
    print(f"\nĐã ghi {n} dòng vào ml_training_samples, phiên bản {version!r}.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    in_utf8()
    bo = argparse.ArgumentParser(description=__doc__)
    bo.add_argument("--version", required=True, help="giá trị cho dataset_version")
    bo.add_argument("--db", default=None, help="tên CSDL khác, dùng khi chạy thử")
    bo.add_argument(
        "--random-neg", type=int, default=None,
        help="SỐ CỐ ĐỊNH mẫu âm mỗi người; để trống thì lấy theo tỉ lệ",
    )
    bo.add_argument(
        "--random-neg-ty-le", type=float, default=0.5, dest="ty_le_am",
        help="số mẫu âm = tỉ lệ này × số tín hiệu của người đó (mặc định 0,5)",
    )
    bo.add_argument("--folds", type=int, default=5, help="số fold (mặc định 5)")
    bo.add_argument("--seed", type=int, default=42, help="hạt giống (mặc định 42)")
    bo.add_argument(
        "--apply", action="store_true", help="ghi vào CSDL, mặc định chỉ chạy thử"
    )
    t = bo.parse_args(argv)

    if len(t.version) > 20:
        print("dataset_version tối đa 20 ký tự.", file=sys.stderr)
        return 1

    cn = ket_noi(t.db)
    try:
        return dung_tap(
            cn,
            version=t.version,
            so_am_moi_nguoi=t.random_neg,
            ty_le_am=t.ty_le_am,
            so_fold=t.folds,
            seed=t.seed,
            ap_dung=t.apply,
        )
    finally:
        cn.close()


if __name__ == "__main__":
    raise SystemExit(main())
