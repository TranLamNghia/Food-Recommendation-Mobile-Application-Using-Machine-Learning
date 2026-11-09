#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Đánh giá — năm phương án, tám chỉ số, kiểm định chéo theo người dùng.

`ml_evaluations` là bảng quan trọng nhất của phần học máy, và lý do nó tồn
tại là cột `variant`: bảng được thiết kế để **so sánh với các phương án đối
chứng**, không chỉ để báo cáo một con số.

    Không phải  "mô hình đạt nDCG@10 = 0,72"
    mà          "mô hình đạt 0,72 so với 0,51 của phương án xếp theo độ phổ biến"

Năm phương án, xếp theo độ khó vượt qua:

| `variant` | Chấm điểm bằng gì |
|---|---|
| `popularity` | `foods.popularity_score` — bỏ qua cá nhân hóa hoàn toàn |
| `rule_based` | Giai đoạn 0 — độ phổ biến trộn với độ khớp macro mục tiêu |
| `content_based` | Giai đoạn 1 — `(1 + cos(p_u, vᵢ)) / 2` |
| `hybrid` | `α · ML + (1 − α) · cosin`, α theo `n_signals` |
| `ml` | Giai đoạn 2 — `predict_proba` của mô hình toàn cục |

`popularity` là phương án tầm thường **bắt buộc phải vượt qua**: nếu xếp món
theo độ phổ biến cũng cho kết quả tương đương thì không có gì để báo cáo.

**Kiểm định chéo huấn luyện lại từng fold.** Mô hình trong `ml_models` chỉ
được huấn luyện trên **một** lần chia. Nếu đánh giá nó trên cả năm fold thì
bốn fold trong số đó đã nằm trong tập huấn luyện của nó, và con số sẽ bị thổi
phồng. Nên ở đây, với mỗi fold, mô hình được **huấn luyện lại từ đầu** trên
các fold còn lại. `model_id` của dòng kết quả vì vậy định danh **cấu hình**
(thuật toán, phiên bản đặc trưng, phiên bản tập dữ liệu, siêu tham số) chứ
không định danh một tệp `.joblib` cụ thể.

**Chia tập theo người dùng.** Cam kết của đề cương là hiệu quả với *mọi*
người dùng, không phải may mắn ở một lần chia. `fold` lưu kết quả từng lần
gập để báo cáo trung bình ± độ lệch chuẩn. `build_dataset` đã gán fold theo
người, nên cùng một người không bao giờ nằm ở cả hai bên.

**Chỉ số xếp hạng tính trên từng người rồi mới lấy trung bình.** Gộp mọi mẫu
của mọi người thành một danh sách rồi tính `precision@5` là sai: người dùng
không bao giờ thấy một danh sách trộn như vậy. `k_value` tồn tại vì mỗi ngày
họ chỉ thấy 4–6 suất; `precision` trên toàn bộ 318 món thì không nói gì.

Chạy:
    python -m ml.evaluate --dataset d1 --model gb-d1-1            # chạy thử
    python -m ml.evaluate --dataset d1 --model gb-d1-1 --apply
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

from . import popularity, scoring
from .dataset import NGUONG_THICH, TapDacTrung, nap_khong_gian, nap_tap, thong_ke
from .db import in_utf8, ket_noi
from .rocchio import alpha
from .train import SIEU_THAM_SO, _bo_phan_lop

PHUONG_AN = ("popularity", "rule_based", "content_based", "hybrid", "ml")

#: Các mức k được báo cáo. 5 vì mỗi ngày người dùng thấy 4–6 suất; 10 để thấy
#: chỉ số đổi thế nào khi nới danh sách.
CAC_MUC_K = (5, 10)


# ── Chấm điểm từng phương án ──────────────────────────────────────────


#
# Bốn hàm dưới đây **không cài công thức nào**: chúng chỉ gọi `ml/scoring.py`
# cho từng mẫu. Đó là chủ ý — `ml/serve.py` gọi đúng những hàm ấy khi phục vụ
# người dùng thật, nên con số báo cáo trong Chương 3 và điểm mà người dùng
# thực sự nhận được do cùng một đoạn mã sinh ra. Nếu mỗi bên tự cài lại công
# thức thì chúng có thể lệch nhau mà không ai phát hiện: cả hai đều chạy, đều
# trả về số trong [0, 1], chỉ là chúng mô tả hai hệ thống khác nhau.


def _diem_pho_bien(
    t: TapDacTrung, chi_so: Sequence[int], pho_bien: dict[str, float]
) -> np.ndarray:
    return np.asarray(
        [scoring.diem_pho_bien(pho_bien.get(t.food_id[i], 0.0)) for i in chi_so],
        dtype=float,
    )


def _diem_luat(
    t: TapDacTrung, chi_so: Sequence[int], pho_bien: dict[str, float]
) -> np.ndarray:
    return np.asarray(
        [
            scoring.diem_luat(
                t.v_mon[i], t.muc_tieu_macro[i], pho_bien.get(t.food_id[i], 0.0)
            )
            for i in chi_so
        ],
        dtype=float,
    )


def _diem_noi_dung(t: TapDacTrung, chi_so: Sequence[int]) -> np.ndarray:
    """Giai đoạn 1, với `p_u` là **ảnh chụp** chứ không phải vector hiện tại."""
    return np.asarray(
        [scoring.diem_noi_dung(t.p_u[i], t.v_mon[i]) for i in chi_so], dtype=float
    )


def _diem_tron(
    diem_ml: np.ndarray, diem_nd: np.ndarray, t: TapDacTrung, chi_so: Sequence[int]
) -> np.ndarray:
    """`α · ML + (1 − α) · cosin`, α tính từ `n_signals` của **từng mẫu**.

    α theo từng mẫu, không theo người: `n_signals` của ảnh chụp tăng dần theo
    thời gian, nên một tín hiệu sớm của cùng một người phải được trộn nhẹ hơn
    một tín hiệu muộn. Trộn theo người là dùng α của tương lai cho quá khứ.
    """
    return np.asarray(
        [
            scoring.tron(float(ml), float(nd), t.n_tin_hieu[i])
            for ml, nd, i in zip(diem_ml, diem_nd, chi_so)
        ],
        dtype=float,
    )


# ── Chỉ số ────────────────────────────────────────────────────────────


def _dcg(loi_ich: Sequence[float]) -> float:
    return sum(g / math.log2(j + 2) for j, g in enumerate(loi_ich))


@dataclass
class ChiSoXepHang:
    precision: float
    recall: float
    ndcg: float
    #: Số người dùng thực sự góp vào trung bình — người không có món nào
    #: đáng gợi ý bị bỏ, và phải nói ra bỏ bao nhiêu.
    so_nguoi: int


def chi_so_xep_hang(
    diem: np.ndarray,
    nhan_lien_tuc: np.ndarray,
    nhan_lop: np.ndarray,
    nguoi: Sequence[str],
    k: int,
) -> ChiSoXepHang:
    """`precision@k`, `recall@k`, `ndcg@k` — tính trên từng người rồi lấy trung bình.

    Người dùng **không có món nào** `nhãn ≥ 0,5` bị bỏ khỏi cả ba chỉ số:
    `recall` của họ là 0/0 không xác định, và tính `precision` cho họ thì
    luôn bằng 0 bất kể mô hình xếp hạng thế nào — đưa vào chỉ làm mọi phương
    án tệ đi cùng một lượng và không phân biệt được gì.

    `ndcg` dùng **lợi ích phân mức** là chính nhãn liên tục, không phải nhãn
    nhị phân: một đánh giá 5 sao (1,000) đáng được xếp trên một suất được giữ
    (0,700), và nDCG nhị phân thì coi hai món đó như nhau.
    """
    theo_nguoi: dict[str, list[int]] = defaultdict(list)
    for i, u in enumerate(nguoi):
        theo_nguoi[u].append(i)

    p_list, r_list, n_list = [], [], []
    for u, idx in theo_nguoi.items():
        if not any(nhan_lop[i] for i in idx):
            continue
        # Xếp giảm dần theo điểm. Hòa điểm thì xếp theo chỉ số để kết quả
        # không phụ thuộc thứ tự duyệt — `popularity` hòa rất nhiều.
        xep = sorted(idx, key=lambda i: (-diem[i], i))
        top = xep[:k]

        dung = sum(int(nhan_lop[i]) for i in top)
        tong_dung = sum(int(nhan_lop[i]) for i in idx)

        p_list.append(dung / min(k, len(idx)))
        r_list.append(dung / tong_dung)

        ly_tuong = sorted((float(nhan_lien_tuc[i]) for i in idx), reverse=True)[:k]
        idcg = _dcg(ly_tuong)
        dcg = _dcg([float(nhan_lien_tuc[i]) for i in top])
        n_list.append(dcg / idcg if idcg > 0 else 0.0)

    if not p_list:
        return ChiSoXepHang(0.0, 0.0, 0.0, 0)
    return ChiSoXepHang(
        float(np.mean(p_list)),
        float(np.mean(r_list)),
        float(np.mean(n_list)),
        len(p_list),
    )


def map_toan_danh_sach(
    diem: np.ndarray, nhan_lop: np.ndarray, nguoi: Sequence[str]
) -> tuple[float, int]:
    """`MAP` — độ chính xác trung bình trên **toàn bộ** danh sách của từng người.

    Không có `k` vì MAP tính tới mọi vị trí: nó phạt một món đáng gợi ý bị
    đẩy xuống cuối, trong khi `precision@5` thì không thấy món đó.
    """
    theo_nguoi: dict[str, list[int]] = defaultdict(list)
    for i, u in enumerate(nguoi):
        theo_nguoi[u].append(i)

    ds = []
    for idx in theo_nguoi.values():
        tong_dung = sum(int(nhan_lop[i]) for i in idx)
        if tong_dung == 0:
            continue
        xep = sorted(idx, key=lambda i: (-diem[i], i))
        da_dung = 0
        tong = 0.0
        for vi_tri, i in enumerate(xep, start=1):
            if nhan_lop[i]:
                da_dung += 1
                tong += da_dung / vi_tri
        ds.append(tong / tong_dung)

    return (float(np.mean(ds)) if ds else 0.0), len(ds)


def chi_so_hoi_quy(
    diem: np.ndarray, nhan: np.ndarray, trong_so: np.ndarray
) -> tuple[float, float]:
    """`mae`, `rmse` — có trọng số theo `sample_weight`.

    Dùng trọng số vì `sample_weight` mã hóa **độ tin cậy** của nhãn: sai 0,3
    trên một đánh giá 5 sao nghiêm trọng hơn sai 0,3 trên một suất bị bỏ,
    nơi chính nhãn đã là phỏng đoán.
    """
    mae = float(np.average(np.abs(diem - nhan), weights=trong_so))
    rmse = float(np.sqrt(np.average((diem - nhan) ** 2, weights=trong_so)))
    return mae, rmse


def chi_so_phan_lop(diem: np.ndarray, nhan_lop: np.ndarray) -> tuple[float, float]:
    """`f1`, `auc`.

    `f1` cần một ngưỡng; dùng `NGUONG_THICH` để đồng nhất với lúc tạo nhãn.
    Lưu ý `popularity` và `rule_based` cho điểm trong một dải hẹp và có thể
    nằm trọn một bên ngưỡng — khi đó `f1` của chúng suy biến, trong khi `auc`
    vẫn đo được vì nó chỉ nhìn **thứ tự**. Đó là lý do báo cáo cả hai.
    """
    du_doan = (diem >= NGUONG_THICH).astype(int)
    f1 = float(f1_score(nhan_lop, du_doan, zero_division=0))
    auc = (
        float(roc_auc_score(nhan_lop, diem))
        if len(set(nhan_lop.tolist())) > 1
        else float("nan")
    )
    return f1, auc


# ── Chạy một fold ─────────────────────────────────────────────────────


def _huan_luyen_fold(
    t: TapDacTrung, thuat_toan: str, train: Sequence[int], seed: int, X: np.ndarray
):
    y_lop = np.asarray(t.y_lop, dtype=int)
    w = np.asarray(t.sample_weight, dtype=float)

    if len({int(y_lop[i]) for i in train}) < 2:
        return None, None

    scaler = StandardScaler().fit(X[train])
    bo = _bo_phan_lop(thuat_toan, seed)
    bo.fit(scaler.transform(X[train]), y_lop[train], sample_weight=w[train])
    return bo, scaler


def _cot_do_pho_bien(t: TapDacTrung) -> int:
    """Vị trí cột `mon.do_pho_bien` trong ma trận đặc trưng.

    Tra theo **tên** chứ không đếm tay: thêm một chiều vào vector món sẽ đẩy
    cột này sang chỗ khác, và một chỉ số viết cứng sẽ âm thầm ghi đè lên một
    đặc trưng khác.
    """
    return t.ten_dac_trung.index("mon.do_pho_bien")


def danh_gia_mot_fold(
    t: TapDacTrung, thuat_toan: str, fold: int, seed: int
) -> dict[tuple[str, str, int], float]:
    """Trả về `{(phương_án, chỉ_số, k): giá_trị}` cho một fold."""
    train = [i for i, f in enumerate(t.fold) if f != fold]
    # `random_neg` **chỉ dùng để huấn luyện, không dùng để đánh giá.**
    #
    # Mẫu âm ngẫu nhiên là món **chưa từng hiển thị** cho người đó, nên nó
    # không phải một sở thích đã quan sát được mà là một phỏng đoán — §9 cho
    # nó trọng số 0,200, thấp nhất trong bảy nguồn, đúng vì vậy.
    #
    # Giữ nó trong tập đánh giá còn làm hỏng phép so sánh: món chưa ai thấy
    # thì độ phổ biến bằng 0, nên **bất cứ** phương án nào dùng độ phổ biến
    # đều tách được mẫu âm ngẫu nhiên khỏi tín hiệu thật mà không cần biết gì
    # về khẩu vị. Chốt canh rò rỉ bắt được chuyện này: sau khi đã sửa phần
    # độ phổ biến theo fold, `popularity` vẫn đạt nDCG@5 = 0,549 trên nhãn
    # ngẫu nhiên hoàn toàn, chỉ nhờ phân biệt được "món đã hiển thị" với
    # "món chưa hiển thị".
    #
    # Mẫu âm vẫn ở trong tập **huấn luyện**: không có chúng, mô hình chỉ thấy
    # những món hệ thống đã chọn để hiển thị và sẽ học cách tái tạo lại chính
    # bộ lọc của hệ thống thay vì học khẩu vị.
    test = [
        i
        for i, f in enumerate(t.fold)
        if f == fold and t.source[i] != "random_neg"
    ]
    if not test or not train:
        return {}

    # ── Độ phổ biến dựng lại từ RIÊNG fold huấn luyện ──
    #
    # Không dùng `foods.popularity_score`: cột đó được tính từ toàn bộ tín
    # hiệu, kể cả tín hiệu của những người nằm trong fold kiểm tra. Một món mà
    # chính người bị kiểm đã thích thì đã góp phần đẩy điểm phổ biến của nó
    # lên, nên "độ phổ biến" khi đó mang sẵn thông tin về nhãn của tập kiểm
    # tra. Chốt canh rò rỉ bắt được đúng chuyện này: với nhãn ngẫu nhiên hoàn
    # toàn, `popularity` vẫn đạt nDCG@5 = 0,796 và AUC của mô hình nhảy từ
    # 0,48 lên 0,67.
    #
    # Ghi đè luôn vào cột `mon.do_pho_bien` của ma trận đặc trưng, vì mô hình
    # cũng dùng đặc trưng đó và cũng rò rỉ theo.
    pho_bien = popularity.tu_tap_mau(
        t.user_id, t.food_id, t.y, t.source, train, nguong_duong=NGUONG_THICH
    )
    X = np.asarray(t.X, dtype=float)
    X[:, _cot_do_pho_bien(t)] = [pho_bien.get(f, 0.0) for f in t.food_id]

    bo, scaler = _huan_luyen_fold(t, thuat_toan, train, seed, X)

    y = np.asarray([t.y[i] for i in test], dtype=float)
    y_lop = np.asarray([t.y_lop[i] for i in test], dtype=int)
    w = np.asarray([t.sample_weight[i] for i in test], dtype=float)
    nguoi = [t.user_id[i] for i in test]

    diem_nd = _diem_noi_dung(t, test)
    diem_ml = (
        bo.predict_proba(scaler.transform(X[test]))[:, 1]
        if bo is not None
        # Tập huấn luyện của fold này chỉ có một lớp nên không có mô hình.
        # Cho điểm trung tính thay vì bỏ cả fold: các phương án đối chứng
        # vẫn đo được, và dòng `ml` sẽ hiện ra là vô nghĩa chứ không biến mất.
        else np.full(len(test), 0.5)
    )

    diem = {
        "popularity": _diem_pho_bien(t, test, pho_bien),
        "rule_based": _diem_luat(t, test, pho_bien),
        "content_based": diem_nd,
        "hybrid": _diem_tron(diem_ml, diem_nd, t, test),
        "ml": diem_ml,
    }

    ket_qua: dict[tuple[str, str, int], float] = {}
    for pa in PHUONG_AN:
        d = diem[pa]
        mae, rmse = chi_so_hoi_quy(d, y, w)
        f1, auc = chi_so_phan_lop(d, y_lop)
        gt_map, _ = map_toan_danh_sach(d, y_lop, nguoi)

        ket_qua[(pa, "mae", 0)] = mae
        ket_qua[(pa, "rmse", 0)] = rmse
        ket_qua[(pa, "f1", 0)] = f1
        if not math.isnan(auc):
            ket_qua[(pa, "auc", 0)] = auc
        ket_qua[(pa, "map", 0)] = gt_map

        for k in CAC_MUC_K:
            cs = chi_so_xep_hang(d, y, y_lop, nguoi, k)
            ket_qua[(pa, "precision", k)] = cs.precision
            ket_qua[(pa, "recall", k)] = cs.recall
            ket_qua[(pa, "ndcg", k)] = cs.ndcg

    return ket_qua


# ── Ghi và trình bày ──────────────────────────────────────────────────

SQL_XOA = "DELETE FROM ml_evaluations WHERE model_id = %s"
SQL_CHEN = """
INSERT INTO ml_evaluations (model_id, variant, metric, k_value, value, fold)
VALUES (%s, %s, %s, %s, %s, %s)
"""


def ghi(cn, model_id: int, theo_fold: dict[int, dict[tuple[str, str, int], float]]) -> int:
    dong = [
        (model_id, pa, cs, k, round(gt, 5), fold)
        for fold, bang in sorted(theo_fold.items())
        for (pa, cs, k), gt in sorted(bang.items())
    ]
    with cn.cursor() as cur:
        cur.execute(SQL_XOA, (model_id,))
        da_xoa = cur.rowcount
        if dong:
            cur.executemany(SQL_CHEN, dong)
    cn.commit()
    if da_xoa:
        print(f"Đã xóa {da_xoa} dòng đánh giá cũ của mô hình này.")
    return len(dong)


def bang_ket_qua(theo_fold: dict[int, dict[tuple[str, str, int], float]]) -> str:
    """Bảng trung bình ± độ lệch chuẩn qua các fold, xếp theo phương án."""
    gom: dict[tuple[str, str, int], list[float]] = defaultdict(list)
    for bang in theo_fold.values():
        for khoa, gt in bang.items():
            gom[khoa].append(gt)

    cot = [
        ("ndcg", 5), ("ndcg", 10), ("precision", 5), ("recall", 5),
        ("map", 0), ("auc", 0), ("f1", 0), ("mae", 0), ("rmse", 0),
    ]
    tieu_de = "  ".join(
        f"{(cs + ('@' + str(k) if k else '')):>12}" for cs, k in cot
    )
    dong = [f"{'phương án':<14}{tieu_de}"]
    for pa in PHUONG_AN:
        o = []
        for cs, k in cot:
            ds = gom.get((pa, cs, k))
            if not ds:
                o.append(f"{'—':>12}")
            elif len(ds) > 1:
                o.append(f"{np.mean(ds):.3f}±{np.std(ds):.3f}".rjust(12))
            else:
                o.append(f"{ds[0]:.3f}".rjust(12))
        dong.append(f"{pa:<14}" + "  ".join(o))
    return "\n".join(dong)


def canh_bao_suy_bien(t: TapDacTrung) -> list[str]:
    """Phát hiện phương án đối chứng **không xếp hạng được gì**.

    Vì sao cần báo. Nếu `popularity_score` bằng nhau ở mọi món thì phương án
    `popularity` không sắp được thứ tự nào: mọi món hòa điểm, và con số
    `precision@5` thu được chỉ phản ánh **cách phá hòa** — ở đây là theo chỉ
    số dòng, tức là ngẫu nhiên. Nó vẫn in ra một số trông bình thường, và đó
    chính là chỗ nguy hiểm: §10.1 đặt `popularity` làm phương án *bắt buộc
    phải vượt qua*, nên một `popularity` suy biến sẽ biến câu hỏi nghiên cứu
    cốt lõi thành một phép so với nhiễu.

    Tương tự, `hybrid` trùng khít `content_based` khi mọi mẫu đều có
    `n_signals < 30` — khi đó α = 0 theo đúng công thức. Đó không phải lỗi,
    nhưng phải nói ra, nếu không hai dòng giống nhau trong bảng kết quả sẽ bị
    đọc thành một lỗi sao chép.
    """
    cb: list[str] = []

    # Kiểm trên độ phổ biến **dựng lại từ tập mẫu**, không kiểm cột
    # `foods.popularity_score`: đó đúng là thứ phép đánh giá dùng tới, và một
    # cột đã được ghi sẵn vẫn có thể suy biến trong phạm vi tập mẫu này.
    pb = popularity.tu_tap_mau(
        t.user_id, t.food_id, t.y, t.source,
        range(len(t)), nguong_duong=NGUONG_THICH,
    )
    muc = set(pb.values())
    if len(muc) <= 1:
        gia_tri = next(iter(muc), 0.0)
        cb.append(
            f"`popularity` SUY BIẾN: mọi món trong tập mẫu cùng độ phổ biến "
            f"{gia_tri:g}. Phương án này hiện không xếp hạng gì — mọi chỉ số "
            f"của nó chỉ là cách phá hòa, nên phép so với nó chưa có hiệu lực."
        )

    a = [alpha(n) for n in t.n_tin_hieu]
    if max(a) == 0:
        cb.append(
            f"`hybrid` trùng khít `content_based`: mọi mẫu có n_signals < 30 "
            f"nên α = 0 (lớn nhất {max(t.n_tin_hieu)} tín hiệu). Đúng công "
            f"thức, không phải lỗi."
        )
    elif min(a) == 1:
        cb.append("`hybrid` trùng khít `ml`: mọi mẫu có n_signals > 100 nên α = 1.")

    return cb


def main(argv: Sequence[str] | None = None) -> int:
    in_utf8()
    bo_doc = argparse.ArgumentParser(description=__doc__)
    bo_doc.add_argument("--dataset", required=True)
    bo_doc.add_argument(
        "--model", required=True, help="`ml_models.version` của cấu hình cần đánh giá"
    )
    bo_doc.add_argument("--db", default=None)
    bo_doc.add_argument("--seed", type=int, default=42)
    bo_doc.add_argument("--apply", action="store_true")
    t = bo_doc.parse_args(argv)

    cn = ket_noi(t.db)
    try:
        with cn.cursor() as cur:
            cur.execute(
                "SELECT id, algorithm, dataset_version, feature_version "
                "FROM ml_models WHERE version = %s",
                (t.model,),
            )
            mh = cur.fetchone()
        if mh is None:
            print(f"Không có mô hình nào có version = {t.model!r}.", file=sys.stderr)
            return 1
        if mh["algorithm"] not in SIEU_THAM_SO:
            print(f"Thuật toán lạ: {mh['algorithm']!r}", file=sys.stderr)
            return 1
        if mh["dataset_version"] != t.dataset:
            print(
                f"Lưu ý: mô hình {t.model!r} được huấn luyện trên tập "
                f"{mh['dataset_version']!r} nhưng đang đánh giá trên "
                f"{t.dataset!r}."
            )

        kg, mon_theo_id = nap_khong_gian(cn)
        tap = nap_tap(cn, dataset_version=t.dataset, kg=kg, mon_theo_id=mon_theo_id)
        if not len(tap):
            print(f"Tập dữ liệu {t.dataset!r} không có mẫu nào.")
            return 1

        print(thong_ke(tap))
        folds = sorted(set(tap.fold))
        print(f"  kiểm định chéo {len(folds)} fold, huấn luyện lại từng fold")

        canh_bao = canh_bao_suy_bien(tap)
        if canh_bao:
            print()
            for c in canh_bao:
                print("  ⚠ " + c)
        print()

        theo_fold: dict[int, dict[tuple[str, str, int], float]] = {}
        for f in folds:
            bang = danh_gia_mot_fold(tap, mh["algorithm"], f, t.seed)
            if not bang:
                print(f"  fold {f}: bỏ qua (một bên rỗng)")
                continue
            theo_fold[f] = bang
            print(
                f"  fold {f}: nDCG@5  "
                + "  ".join(
                    f"{pa}={bang[(pa, 'ndcg', 5)]:.3f}" for pa in PHUONG_AN
                )
            )

        if not theo_fold:
            print("\nKhông fold nào đánh giá được.")
            return 1

        print()
        print(bang_ket_qua(theo_fold))
        print()

        nd = float(
            np.mean([b[("content_based", "ndcg", 5)] for b in theo_fold.values()])
        )
        pb = float(
            np.mean([b[("popularity", "ndcg", 5)] for b in theo_fold.values()])
        )
        print(
            f"Câu hỏi nghiên cứu cốt lõi — khuyến nghị theo nội dung có hơn "
            f"độ phổ biến?\n"
            f"  nDCG@5: content_based {nd:.3f} so với popularity {pb:.3f} "
            f"({nd - pb:+.3f})"
        )
        if any("SUY BIẾN" in c for c in canh_bao):
            print(
                "  → Phép so này CHƯA có hiệu lực: mốc `popularity` đang suy "
                "biến (xem cảnh báo ở trên)."
            )

        if not t.apply:
            so = sum(len(b) for b in theo_fold.values())
            print(
                f"\nChạy thử — chưa ghi gì. Thêm --apply để ghi {so} dòng "
                f"vào ml_evaluations."
            )
            return 0

        n = ghi(cn, int(mh["id"]), theo_fold)
        print(f"\nĐã ghi {n} dòng vào ml_evaluations cho model_id={mh['id']}.")
        return 0
    finally:
        cn.close()


if __name__ == "__main__":
    raise SystemExit(main())
