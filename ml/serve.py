#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phục vụ mô hình — chấm điểm ứng viên cho một người dùng thật.

Đây là việc số 6 của `ML_PIPELINE.md` §12, và là chỗ **bốn giai đoạn gặp
nhau**. Giai đoạn được chọn theo số tín hiệu người dùng đã cho, không phải
theo mô hình nào đang có:

| `n_signals` | Giai đoạn | Chấm điểm bằng | `generation_source` |
|---|---|---|---|
| 0 | `cold` | độ phổ biến + độ khớp macro | `rule_based` |
| 1–29 | `content` | `(1 + cos(p_u, vᵢ)) / 2` | `content_based` |
| 30–100 | `hybrid` | `α·ML + (1−α)·cosin` | `hybrid` |
| > 100 | `ml` | mô hình toàn cục | `ml` |

**Bộ lọc F1 chạy trước, luôn luôn.** Nó là tầng an toàn, không phải một bước
tối ưu: một món vi phạm ràng buộc cứng phải bị loại kể cả khi mô hình cho nó
điểm cao nhất. Nên nó nằm ngoài và nằm trước mọi phép chấm điểm, không phải
một hệ số trừ điểm.

**Hạ cấp có công bố.** Nếu giai đoạn đòi mô hình mà không có mô hình nào
`is_active = 1`, hoặc mô hình đang hoạt động thuộc một phiên bản đặc trưng
khác, thì hệ thống lùi về giai đoạn thấp hơn và **nói ra**. Âm thầm trả về
điểm trung tính thì thực đơn vẫn sinh ra được, trông vẫn bình thường, và
không ai biết phần học máy đã ngừng hoạt động từ bao giờ.

**Ba phép kiểm trước khi dùng một mô hình**, vì cả ba đều thất bại trong im
lặng nếu không kiểm:

1.  `feature_version` của mô hình phải bằng của mã hiện tại — khác là mô hình
    được nạp với một vector khác hẳn.
2.  `ten_dac_trung` lưu trong tệp mô hình phải trùng danh sách dựng từ không
    gian hiện tại — món mới làm phát sinh nhóm mới thì vector dài ra, và
    `StandardScaler` sẽ nhận sai số cột.
3.  Vector sở thích trong `user_preference_profiles` phải đủ số chiều — hồ sơ
    cũ từ trước khi thêm chiều sẽ ngắn hơn.

Chạy:
    python -m ml.serve --user <id>            # gợi ý 20 món hàng đầu
    python -m ml.serve --user <id> --giai-thich
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np

from . import scoring
from .dataset import HoSoNguoi, dung_hang_dac_trung, nap_ho_so_nguoi, ten_dac_trung
from .db import in_utf8, ket_noi
from .f1_filter import loc_f1
from .features import FEATURE_VERSION, KhongGianDacTrung, Mon, nap_mon
from .rocchio import HoSoSoThich, alpha, giai_doan, ho_so_rong

ROOT = Path(__file__).resolve().parent.parent

#: `meal_plans.generation_source` tương ứng với từng giai đoạn.
NGUON_THEO_GIAI_DOAN = {
    "cold": "rule_based",
    "content": "content_based",
    "hybrid": "hybrid",
    "ml": "ml",
}


# ── Mô hình đang phục vụ ──────────────────────────────────────────────


@dataclass
class MoHinhDangPhucVu:
    model_id: int
    version: str
    algorithm: str
    scaler: Any
    model: Any
    ten_dac_trung: list[str]

    def cham_diem(self, hang: Sequence[Sequence[float]]) -> np.ndarray:
        """Xác suất thuộc lớp "thích" — điểm ưa thích trong [0, 1].

        Dùng `predict_proba` chứ không `predict`: `predict` trả 0 hoặc 1 nên
        mọi món "thích" sẽ hòa điểm và Bước 4 không còn gì để xếp hạng.
        """
        X = self.scaler.transform(np.asarray(hang, dtype=float))
        return self.model.predict_proba(X)[:, 1]


def nap_mo_hinh_hoat_dong(
    cn, kg: KhongGianDacTrung
) -> tuple[MoHinhDangPhucVu | None, str | None]:
    """Nạp mô hình `is_active = 1`. Trả về `(mô hình, lý do không nạp được)`.

    Trả về lý do thành chuỗi thay vì ném ngoại lệ, vì không có mô hình **là
    một trạng thái hợp lệ** của hệ thống: Giai đoạn 0 và 1 chạy không cần mô
    hình nào. Ném ngoại lệ ở đây sẽ làm sập cả đường sinh thực đơn của những
    người dùng vốn không cần tới mô hình.
    """
    with cn.cursor() as cur:
        cur.execute(
            "SELECT id, version, algorithm, feature_version, artifact_path "
            "FROM ml_models WHERE is_active = 1"
        )
        ds = cur.fetchall()

    if not ds:
        return None, "không có mô hình nào is_active = 1"
    if len(ds) > 1:
        # `is_active` không có ràng buộc duy nhất ở mức lược đồ, nên tình
        # huống này có thể xảy ra nếu ai đó cập nhật bằng tay. Từ chối chọn
        # bừa: chọn bừa là một quyết định không tái lập được.
        ten = ", ".join(d["version"] for d in ds)
        return None, f"có {len(ds)} mô hình cùng is_active = 1 ({ten})"

    d = ds[0]
    if d["feature_version"] != FEATURE_VERSION:
        return None, (
            f"mô hình {d['version']!r} thuộc phiên bản đặc trưng "
            f"{d['feature_version']!r}, mã hiện tại là {FEATURE_VERSION!r}"
        )

    tep = ROOT / d["artifact_path"]
    if not tep.exists():
        return None, f"thiếu tệp mô hình {d['artifact_path']}"

    goi = joblib.load(tep)
    ten_hien_tai = ten_dac_trung(kg)
    if list(goi.get("ten_dac_trung", [])) != ten_hien_tai:
        return None, (
            f"mô hình {d['version']!r} được huấn luyện trên "
            f"{len(goi.get('ten_dac_trung', []))} đặc trưng, không gian hiện "
            f"tại có {len(ten_hien_tai)} — danh mục món đã đổi, phải huấn "
            f"luyện lại"
        )

    return (
        MoHinhDangPhucVu(
            model_id=int(d["id"]),
            version=d["version"],
            algorithm=d["algorithm"],
            scaler=goi["scaler"],
            model=goi["model"],
            ten_dac_trung=ten_hien_tai,
        ),
        None,
    )


# ── Hồ sơ sở thích hiện tại ───────────────────────────────────────────


def nap_ho_so_so_thich(
    cn, user_id: str, kg: KhongGianDacTrung
) -> tuple[HoSoSoThich, str | None]:
    """Đọc `user_preference_profiles`. Trả về `(hồ sơ, cảnh báo)`.

    Ở đây dùng vector **hiện tại**, không dùng ảnh chụp — và điều đó đúng.
    Ảnh chụp chỉ cần khi *dựng tập huấn luyện*, nơi dùng vector hiện tại sẽ
    là rò rỉ dữ liệu vì nó đã bị cập nhật bởi chính tín hiệu đang làm nhãn.
    Lúc suy luận thì không có nhãn nào để rò rỉ: vector hiện tại chính là tất
    cả những gì hệ thống biết về người này.
    """
    with cn.cursor() as cur:
        cur.execute(
            "SELECT feature_version, weights, sum_abs_weight, n_signals, stage "
            "FROM user_preference_profiles WHERE user_id = %s",
            (user_id,),
        )
        d = cur.fetchone()

    if d is None:
        return ho_so_rong(kg), None

    if d["feature_version"] != FEATURE_VERSION:
        return ho_so_rong(kg), (
            f"hồ sơ sở thích thuộc phiên bản đặc trưng "
            f"{d['feature_version']!r}, bỏ qua và lùi về Giai đoạn 0"
        )

    w = json.loads(d["weights"])
    if isinstance(w, dict):
        w = w.get("weights", [])
    if len(w) != kg.length:
        return ho_so_rong(kg), (
            f"hồ sơ sở thích có {len(w)} chiều nhưng không gian hiện tại có "
            f"{kg.length}, bỏ qua và lùi về Giai đoạn 0"
        )

    return (
        HoSoSoThich(
            weights=tuple(float(x) for x in w),
            sum_abs_weight=float(d["sum_abs_weight"]),
            n_signals=int(d["n_signals"]),
        ),
        None,
    )


# ── Gợi ý ─────────────────────────────────────────────────────────────


@dataclass
class UngVien:
    mon: Mon
    diem: float
    #: Điểm của từng thành phần, giữ lại để giải thích được vì sao món này
    #: được gợi ý. Không dùng khi xếp hạng.
    diem_noi_dung: float
    diem_luat: float
    diem_ml: float | None


@dataclass
class KetQuaGoiY:
    user_id: str
    stage: str
    generation_source: str
    n_signals: int
    alpha: float
    model_id: int | None
    model_version: str | None
    so_mon_truoc_f1: int
    so_mon_sau_f1: int
    ung_vien: list[UngVien]
    #: Những gì đã phải hạ cấp hoặc bỏ qua. Rỗng là tốt.
    canh_bao: list[str] = field(default_factory=list)


def goi_y(
    cn,
    user_id: str,
    *,
    gioi_han: int = 20,
    mon_da_dung: Sequence[str] = (),
) -> KetQuaGoiY:
    """Chấm điểm và xếp hạng ứng viên cho một người dùng.

    `mon_da_dung` là những món đã dùng trong ngày — Bước 4 truyền vào để
    không lặp món trong cùng một thực đơn. Loại ở đây thay vì để Bước 4 tự
    bỏ, để `gioi_han` trả về đúng số món còn dùng được.
    """
    mon, _ = nap_mon(cn)
    kg = KhongGianDacTrung.tu_mon(mon)
    mon_theo_id = {m.id: m for m in mon}

    canh_bao: list[str] = []

    # ── Bước F1: tầng an toàn, chạy trước mọi phép chấm điểm ──
    an_toan = loc_f1(cn, user_id=user_id)
    loai = set(mon_da_dung)
    ds_ung_vien = [
        mon_theo_id[d["id"]]
        for d in an_toan
        if d["id"] in mon_theo_id and d["id"] not in loai
    ]

    # ── Hồ sơ và giai đoạn ──
    ho_so, cb = nap_ho_so_so_thich(cn, user_id, kg)
    if cb:
        canh_bao.append(cb)

    n = ho_so.n_signals
    gd = giai_doan(n)
    a = alpha(n)

    mo_hinh: MoHinhDangPhucVu | None = None
    if gd in ("hybrid", "ml"):
        mo_hinh, ly_do = nap_mo_hinh_hoat_dong(cn, kg)
        if mo_hinh is None:
            canh_bao.append(
                f"Giai đoạn {gd} cần mô hình nhưng {ly_do} — hạ về Giai đoạn 1 "
                f"(content_based)."
            )
            gd = "content"
            a = 0.0

    ho_so_suc_khoe = nap_ho_so_nguoi(cn).get(user_id)
    if ho_so_suc_khoe is None:
        ho_so_suc_khoe = HoSoNguoi(mac_dinh=True)
        canh_bao.append(
            "Người dùng chưa có health_profiles — khối đặc trưng người dùng "
            "và độ khớp macro đang dùng giá trị mặc định."
        )

    # ── Chấm điểm ──
    with cn.cursor() as cur:
        cur.execute(
            "SELECT id, popularity_score FROM foods WHERE owner_id IS NULL "
            "OR owner_id = %s",
            (user_id,),
        )
        pho_bien = {d["id"]: float(d["popularity_score"]) for d in cur.fetchall()}

    diem_ml_tat_ca: np.ndarray | None = None
    if mo_hinh is not None and ds_ung_vien:
        ten = ten_dac_trung(kg)
        hang = [
            dung_hang_dac_trung(
                ho_so_suc_khoe,
                n,
                ho_so.weights,
                kg.encode(m),
                pho_bien.get(m.id, 0.0),
                so_chieu_mong_doi=len(ten),
            )
            for m in ds_ung_vien
        ]
        diem_ml_tat_ca = mo_hinh.cham_diem(hang)

    ung_vien: list[UngVien] = []
    for i, m in enumerate(ds_ung_vien):
        v = kg.encode(m)
        d_luat = scoring.diem_luat(v, ho_so_suc_khoe.muc_tieu_macro,
                                   pho_bien.get(m.id, 0.0))
        d_nd = scoring.diem_noi_dung(ho_so.weights, v)
        d_ml = float(diem_ml_tat_ca[i]) if diem_ml_tat_ca is not None else None

        if gd == "cold":
            diem = d_luat
        elif gd == "content":
            diem = d_nd
        elif gd == "hybrid":
            diem = scoring.tron(d_ml or scoring.DIEM_TRUNG_TINH, d_nd, n)
        else:
            diem = d_ml if d_ml is not None else d_nd

        ung_vien.append(UngVien(m, diem, d_nd, d_luat, d_ml))

    # Hòa điểm phá theo tên món để kết quả tái lập được — ở Giai đoạn 0 với
    # `popularity_score` toàn 0 thì hòa điểm xảy ra rất nhiều.
    ung_vien.sort(key=lambda u: (-u.diem, u.mon.name, u.mon.id))

    return KetQuaGoiY(
        user_id=user_id,
        stage=gd,
        generation_source=NGUON_THEO_GIAI_DOAN[gd],
        n_signals=n,
        alpha=a,
        model_id=mo_hinh.model_id if mo_hinh else None,
        model_version=mo_hinh.version if mo_hinh else None,
        so_mon_truoc_f1=len(mon),
        so_mon_sau_f1=len(ds_ung_vien),
        ung_vien=ung_vien[:gioi_han],
        canh_bao=canh_bao,
    )


# ── Giải thích bằng câu, không bằng số ────────────────────────────────
#
# `giai_thich` trả về `"Tỷ lệ đạm (+0.182), Nhóm: Món canh (+0.061)"`. Nhãn
# chiều thì đã là tiếng Việt đọc được, nhưng `+0.182` vô nghĩa với người
# dùng: nó là một số hạng trong tử số của phép cosin, không phải phần trăm,
# không có đơn vị, và độ lớn của nó phụ thuộc cả vào hồ sơ lẫn vào món.
#
# **Thứ tự mới là thông tin.** Nên phần dưới giữ thứ tự và tỷ lệ TƯƠNG ĐỐI
# so với đóng góp lớn nhất, rồi bỏ giá trị tuyệt đối khỏi phần hiện ra.
#
# ## Vì sao chỉ nêu chiều dương, và vì sao câu luôn là "nhiều X"
#
# Mọi chiều của vector món nằm trong [0, 1] — `food_vector_parity_test.dart`
# khẳng định điều đó, và `KhongGianDacTrung._chuan_hoa` kẹp lại. Nên
# `v[i] ≥ 0` luôn, và dấu của `p_u[i]·v[i]` chính là dấu của `p_u[i]`.
#
# Suy ra: một đóng góp DƯƠNG nghĩa là `p_u[i] > 0`, tức là món người này
# thích có giá trị cao ở chiều đó. Câu vì vậy luôn theo chiều "nhiều X",
# không bao giờ là "ít X" — "bạn nghiêng về món ít ngọt" ứng với `p_u` ÂM,
# và đóng góp khi ấy là số âm nên đã bị loại khỏi danh sách này.

#: Nhãn chiều → mệnh đề mô tả món, để dựng câu "Bạn thường chọn món …".
#:
#: Thiếu một nhãn ở đây KHÔNG làm hàm nổ — giao diện vẫn chạy, chỉ là chiều
#: đó không có câu. Nhưng `thieu_menh_de` báo ra và `tools/check_ml.py` gọi
#: nó, nên một chiều mới thêm vào mà quên đặt câu thì phép kiểm sai ngay chứ
#: không âm thầm hiện nhãn kỹ thuật cho người dùng.
MENH_DE_THEO_CHIEU: dict[str, str] = {
    "Tỷ lệ đạm": "nhiều đạm",
    "Tỷ lệ bột đường": "nhiều bột đường",
    "Tỷ lệ béo": "nhiều chất béo",
    "Năng lượng": "nhiều năng lượng",
    "Vị ngọt": "có vị ngọt",
    "Vị mặn": "đậm vị mặn",
    "Chất xơ": "nhiều chất xơ",
    "Mức cay": "có vị cay",
}

#: Tiền tố mà `KhongGianDacTrung.labels` gắn cho chiều one-hot nhóm món.
TIEN_TO_NHOM = "Nhóm: "


@dataclass(frozen=True)
class DongGop:
    """Một chiều góp vào điểm khớp khẩu vị của một món."""

    #: Nhãn kỹ thuật của chiều, giữ lại để gỡ lỗi — KHÔNG hiện cho người dùng.
    chieu: str
    #: `p_u[i] · vᵢ[i]`. Giữ lại để kiểm và gỡ lỗi, không hiện ra.
    gia_tri: float
    #: So với đóng góp lớn nhất **của chính món này**, trong (0, 1].
    #:
    #: Đây là thứ vẽ thành thanh so sánh, nhưng nó chỉ nói thứ tự BÊN TRONG
    #: một món, KHÔNG nói món đó khớp khẩu vị mạnh đến đâu. Chuối tiêu — món
    #: người dùng đã vuốt `dislike` — cho ba tỷ lệ 100% / 91% / 88% trong khi
    #: đóng góp tuyệt đối chỉ +0,0093: chuẩn hóa theo đỉnh của chính nó nên
    #: một món khớp rất yếu vẫn ra ba thanh gần đầy.
    #:
    #: Vì vậy giao diện **phải** hiện điểm khớp tổng (`scoring.diem_noi_dung`)
    #: bên cạnh. Vẽ riêng mấy thanh này là nói với người dùng rằng mọi món
    #: đều khớp mạnh như nhau.
    ty_le: float
    #: Câu cho người dùng. `None` khi chiều này chưa có mệnh đề — giao diện
    #: bỏ qua dòng đó thay vì hiện nhãn kỹ thuật.
    cau: str | None


def _cau_cho_chieu(nhan: str) -> str | None:
    if nhan.startswith(TIEN_TO_NHOM):
        return f"Bạn thích nhóm {nhan[len(TIEN_TO_NHOM):]}"
    menh_de = MENH_DE_THEO_CHIEU.get(nhan)
    return None if menh_de is None else f"Bạn thường chọn món {menh_de}"


def thieu_menh_de(kg: KhongGianDacTrung) -> list[str]:
    """Các chiều chưa có câu cho người dùng.

    Chiều nhóm món luôn có câu vì nó dựng từ tên nhóm, nên danh sách này
    chỉ gồm chiều cố định bị quên trong `MENH_DE_THEO_CHIEU`.
    """
    return [nhan for nhan in kg.labels if _cau_cho_chieu(nhan) is None]


def dong_gop(
    kg: KhongGianDacTrung,
    ho_so: HoSoSoThich,
    m: Mon,
    so: int = 3,
) -> list[DongGop]:
    """`so` chiều đóng góp nhiều nhất vào điểm khớp khẩu vị của món `m`.

    Chỉ nêu chiều **dương**: một chiều âm nghĩa là món bị trừ điểm ở đó, nó
    không phải lý do món được gợi ý. Hồ sơ rỗng trả về danh sách rỗng —
    không có cơ sở nào để nói người này thích gì.
    """
    if ho_so.is_empty:
        return []

    v = kg.encode(m)
    gop = sorted(
        (
            (p * x, nhan)
            for p, x, nhan in zip(ho_so.weights, v, kg.labels)
            if p * x > 0
        ),
        key=lambda t: -t[0],
    )[:so]
    if not gop:
        return []

    lon_nhat = gop[0][0]
    return [
        DongGop(
            chieu=nhan,
            gia_tri=g,
            ty_le=g / lon_nhat,
            cau=_cau_cho_chieu(nhan),
        )
        for g, nhan in gop
    ]


def cau_giai_thich(
    kg: KhongGianDacTrung,
    ho_so: HoSoSoThich,
    m: Mon,
    so: int = 3,
) -> list[str]:
    """Các câu giải thích, đã bỏ chiều chưa có mệnh đề. Dùng cho giao diện."""
    return [d.cau for d in dong_gop(kg, ho_so, m, so) if d.cau is not None]


def giai_thich(kg: KhongGianDacTrung, ho_so: HoSoSoThich, m: Mon, so: int = 3) -> str:
    """Dạng **gỡ lỗi** của lời giải thích — nhãn kỹ thuật kèm số thô.

    Dùng cho dòng lệnh và khi soi lỗi, KHÔNG dùng cho giao diện: `+0.182`
    là một số hạng trong tử số của phép cosin, vô nghĩa với người dùng.
    Giao diện gọi `cau_giai_thich` hoặc `dong_gop`.

    Thứ tự và phép lọc chiều dương nằm trong `dong_gop`, hàm này chỉ định
    dạng lại — nếu không thì hai bên có thể xếp hạng khác nhau.
    """
    if ho_so.is_empty:
        return "chưa có hồ sơ sở thích"
    gop = dong_gop(kg, ho_so, m, so)
    if not gop:
        return "không chiều nào đóng góp dương"
    return ", ".join(f"{d.chieu} ({d.gia_tri:+.3f})" for d in gop)


def main(argv: Sequence[str] | None = None) -> int:
    in_utf8()
    bo = argparse.ArgumentParser(description=__doc__)
    bo.add_argument("--user", required=True, help="`users.id`")
    bo.add_argument("--db", default=None)
    bo.add_argument("--top", type=int, default=20)
    bo.add_argument(
        "--giai-thich", action="store_true", help="nêu chiều đóng góp của mỗi món"
    )
    t = bo.parse_args(argv)

    cn = ket_noi(t.db)
    try:
        with cn.cursor() as cur:
            cur.execute("SELECT display_name FROM users WHERE id = %s", (t.user,))
            u = cur.fetchone()
        if u is None:
            print(f"Không có người dùng nào có id = {t.user!r}.", file=sys.stderr)
            return 1

        kq = goi_y(cn, t.user, gioi_han=t.top)

        print(f"Người dùng: {u['display_name']}  ({t.user})")
        print(
            f"Giai đoạn {kq.stage} · generation_source = "
            f"{kq.generation_source} · n_signals = {kq.n_signals} · "
            f"α = {kq.alpha:.3f}"
        )
        print(
            f"Mô hình: "
            + (
                f"{kq.model_version} (id={kq.model_id})"
                if kq.model_version
                else "không dùng"
            )
        )
        print(
            f"Bộ lọc F1: {kq.so_mon_truoc_f1} món → {kq.so_mon_sau_f1} món an toàn"
        )
        for c in kq.canh_bao:
            print(f"  ⚠ {c}")
        print()

        if not kq.ung_vien:
            print("Không còn món nào sau bộ lọc F1.")
            return 0

        kg, _ = None, None
        if t.giai_thich:
            mon, _ = nap_mon(cn)
            kg = KhongGianDacTrung.tu_mon(mon)
            ho_so, _ = nap_ho_so_so_thich(cn, t.user, kg)

        print(f"{'#':>3}  {'điểm':>6}  {'nội dung':>9}  {'ML':>6}  món")
        for i, uv in enumerate(kq.ung_vien, start=1):
            ml = f"{uv.diem_ml:.3f}" if uv.diem_ml is not None else "—"
            print(
                f"{i:>3}  {uv.diem:>6.3f}  {uv.diem_noi_dung:>9.3f}  "
                f"{ml:>6}  {uv.mon.name}  [{uv.mon.category}]"
            )
            if t.giai_thich and kg is not None:
                print(f"       vì: {giai_thich(kg, ho_so, uv.mon)}")
        return 0
    finally:
        cn.close()


if __name__ == "__main__":
    raise SystemExit(main())
