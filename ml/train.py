#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Huấn luyện mô hình toàn cục — ba thuật toán, ghi vào `ml_models`.

Ba thuật toán của `ML_PIPELINE.md` §6.2 và vai trò của từng cái trong đồ án:

| Thuật toán | Vai trò |
|---|---|
| `logistic_regression` | Mốc tuyến tính. Giải thích được qua hệ số, khó quá khớp |
| `random_forest` | Bắt tương tác phi tuyến. Cho `feature_importance` |
| `gradient_boosting` | Thường tốt nhất trên dữ liệu bảng, cần hiệu chỉnh kỹ hơn |

**Bài toán được đặt là phân lớp, không phải hồi quy** — đây là chỗ cần nói rõ
khi bảo vệ. Nhãn là số thực trong [0, 1], nên hồi quy có vẻ tự nhiên hơn.
Nhưng `logistic_regression` là một bộ phân lớp, và cả ba thuật toán phải chấm
điểm **trên cùng một thang** để so sánh được với nhau và với Rocchio. Nên:

· huấn luyện phân lớp nhị phân trên `nhãn ≥ 0,5` (xem `dataset.NGUONG_THICH`);
· **điểm ưa thích là `predict_proba[:, 1]`** — xác suất thuộc lớp "thích",
  nằm sẵn trong [0, 1], cùng thang với `(1 + cos) / 2` của Giai đoạn 1.

Nhờ cách đặt này, `mae` và `rmse` vẫn đo được bằng cách so xác suất với nhãn
*liên tục*, còn `f1` và `auc` đo trên nhãn nhị phân. Tám chỉ số của
`ml_evaluations` dùng được hết mà không phải huấn luyện hai mô hình.

**Hai thứ phải lưu, không phải tùy chọn:**

`scaler_params` — mô hình huấn luyện trên dữ liệu đã chuẩn hóa thì khi suy
luận phải chuẩn hóa **bằng đúng tham số đó**. Tính lại trung bình và độ lệch
trên dữ liệu mới là một lỗi âm thầm làm điểm số lệch dần theo thời gian. Ở
đây `scaler_params` gồm cả tham số `StandardScaler` **và** sáu tham số min–max
của không gian đặc trưng món, vì thiếu nhóm sau thì vector món cũng đã khác.

`feature_version` — đổi một chiều của vector mà không tăng số này thì một mô
hình cũ sẽ được nạp lại với một vector khác, và không ai biết.

Chạy:
    python -m ml.train --dataset d1                 # chạy thử, không ghi
    python -m ml.train --dataset d1 --apply         # huấn luyện cả ba, ghi lại
    python -m ml.train --dataset d1 --apply --kich-hoat gradient_boosting
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from .dataset import NGUONG_THICH, TapDacTrung, nap_khong_gian, nap_tap, thong_ke
from .db import in_utf8, ket_noi
from .features import FEATURE_VERSION

ROOT = Path(__file__).resolve().parent.parent
THU_MUC_MO_HINH = ROOT / "ml" / "artifacts"

#: Siêu tham số. Giữ khiêm tốn và cố định thay vì tìm kiếm trên lưới: với cỡ
#: mẫu của đồ án, một phép tìm siêu tham số sẽ khớp vào chính tập kiểm tra và
#: con số báo cáo mất ý nghĩa. Khi có nhiều dữ liệu hơn thì thêm tập `val`
#: vào đây — cột `split` đã dành sẵn chỗ cho nó.
SIEU_THAM_SO: dict[str, dict[str, Any]] = {
    "logistic_regression": {
        "max_iter": 2000,
        "C": 1.0,
        "solver": "lbfgs",
    },
    "random_forest": {
        "n_estimators": 300,
        # Giới hạn độ sâu và buộc mỗi lá có ít nhất 2 mẫu: với vài nghìn mẫu
        # trên 53 đặc trưng, cây không giới hạn sẽ học thuộc từng mẫu.
        "max_depth": 12,
        "min_samples_leaf": 2,
        "n_jobs": -1,
    },
    "gradient_boosting": {
        "n_estimators": 200,
        "learning_rate": 0.05,
        "max_depth": 3,
        "subsample": 0.9,
    },
}

#: Mã ngắn để dựng `ml_models.version` — cột chỉ cho 20 ký tự.
MA_NGAN = {
    "logistic_regression": "lr",
    "random_forest": "rf",
    "gradient_boosting": "gb",
}


def _bo_phan_lop(thuat_toan: str, seed: int):
    ts = dict(SIEU_THAM_SO[thuat_toan])
    if thuat_toan == "logistic_regression":
        return LogisticRegression(random_state=seed, **ts)
    if thuat_toan == "random_forest":
        return RandomForestClassifier(random_state=seed, **ts)
    if thuat_toan == "gradient_boosting":
        return GradientBoostingClassifier(random_state=seed, **ts)
    raise ValueError(f"thuật toán không có: {thuat_toan!r}")


@dataclass
class KetQuaHuanLuyen:
    thuat_toan: str
    version: str
    n_train: int
    n_test: int
    artifact_path: Path
    feature_importance: dict[str, float]
    scaler_params: dict[str, Any]
    #: Vài con số xem nhanh. Số liệu chính thức do `ml/evaluate.py` ghi vào
    #: `ml_evaluations` cùng bốn phương án đối chứng.
    xem_nhanh: dict[str, float]


def _version_moi(cn, thuat_toan: str, dataset: str) -> str:
    """`lr-d1-1`, `lr-d1-2`, … — duy nhất, và đọc là biết của ai."""
    tien_to = f"{MA_NGAN[thuat_toan]}-{dataset}-"
    with cn.cursor() as cur:
        cur.execute(
            "SELECT version FROM ml_models WHERE version LIKE %s", (tien_to + "%",)
        )
        da_co = {d["version"] for d in cur.fetchall()}
    i = 1
    while f"{tien_to}{i}" in da_co:
        i += 1
        if len(f"{tien_to}{i}") > 20:
            raise RuntimeError(
                f"Hết chỗ cho version với tiền tố {tien_to!r} (cột chỉ 20 ký tự)."
            )
    return f"{tien_to}{i}"


def _tach_theo_split(t: TapDacTrung) -> tuple[list[int], list[int]]:
    """Chỉ số của tập huấn luyện và tập kiểm tra theo cột `split`.

    Dùng cột `split` chứ không tự chia lại: lần chia đã được ghi cùng tập dữ
    liệu và **chia theo người dùng**. Tự chia lại ở đây có nguy cơ cắt một
    người làm hai nửa, và khi đó con số đánh giá bị thổi phồng vì mô hình đã
    thấy khẩu vị của chính người bị kiểm.

    `val` gộp vào tập huấn luyện vì bản này **không tìm siêu tham số** nên
    không cần tập thẩm định riêng. Nói rõ ra để không ai tưởng là đã dùng.
    """
    train = [i for i, s in enumerate(t.split) if s in ("train", "val")]
    test = [i for i, s in enumerate(t.split) if s == "test"]
    return train, test


def _quan_trong(bo, ten: Sequence[str]) -> dict[str, float]:
    """`feature_importance` — hệ số với mô hình tuyến tính, độ quan trọng với cây.

    Với mô hình tuyến tính giữ **dấu**: hệ số âm nghĩa là đặc trưng đó đẩy về
    phía "không thích", và đó là thông tin cần cho phần giải thích gợi ý. Với
    cây thì độ quan trọng vốn không có dấu.
    """
    if hasattr(bo, "coef_"):
        gia_tri = bo.coef_[0]
    elif hasattr(bo, "feature_importances_"):
        gia_tri = bo.feature_importances_
    else:  # pragma: no cover
        return {}
    cap = {t: float(g) for t, g in zip(ten, gia_tri)}
    return dict(sorted(cap.items(), key=lambda kv: -abs(kv[1])))


def huan_luyen_mot(
    t: TapDacTrung,
    thuat_toan: str,
    *,
    dataset: str,
    version: str,
    seed: int,
    tham_so_khong_gian: dict[str, Any],
    ghi_tep: bool,
) -> KetQuaHuanLuyen:
    train, test = _tach_theo_split(t)
    if not train or not test:
        raise RuntimeError(
            f"Lần chia tham chiếu cho tập rỗng một bên "
            f"(train={len(train)}, test={len(test)}). "
            f"Tập dữ liệu quá ít người dùng — cần ít nhất một người mỗi fold."
        )

    X = np.asarray(t.X, dtype=float)
    y_lop = np.asarray(t.y_lop, dtype=int)
    y = np.asarray(t.y, dtype=float)
    w = np.asarray(t.sample_weight, dtype=float)

    if len(set(y_lop[train].tolist())) < 2:
        raise RuntimeError(
            "Tập huấn luyện chỉ có một lớp — không huấn luyện được bộ phân "
            "lớp. Cần cả tín hiệu thích và không thích."
        )

    # Chuẩn hóa **chỉ khớp trên tập huấn luyện**. Khớp trên toàn bộ là rò rỉ:
    # trung bình và độ lệch khi đó đã mang thông tin của tập kiểm tra.
    scaler = StandardScaler().fit(X[train])
    Xs = scaler.transform(X)

    bo = _bo_phan_lop(thuat_toan, seed)
    bo.fit(Xs[train], y_lop[train], sample_weight=w[train])

    p_test = bo.predict_proba(Xs[test])[:, 1]
    xem_nhanh = {
        "mae": float(np.average(np.abs(p_test - y[test]), weights=w[test])),
        "rmse": float(
            np.sqrt(np.average((p_test - y[test]) ** 2, weights=w[test]))
        ),
        "ty_le_thich_test": float(y_lop[test].mean()),
    }

    tham_so_scaler = {
        "feature_version": FEATURE_VERSION,
        "kieu": "StandardScaler",
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "ten_dac_trung": list(t.ten_dac_trung),
        "khong_gian_dac_trung": tham_so_khong_gian,
        "nguong_thich": NGUONG_THICH,
    }

    duong_dan = THU_MUC_MO_HINH / f"{version}.joblib"
    if ghi_tep:
        THU_MUC_MO_HINH.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "version": version,
                "algorithm": thuat_toan,
                "feature_version": FEATURE_VERSION,
                "dataset_version": dataset,
                "scaler": scaler,
                "model": bo,
                "ten_dac_trung": list(t.ten_dac_trung),
                "khong_gian_dac_trung": tham_so_khong_gian,
            },
            duong_dan,
        )

    return KetQuaHuanLuyen(
        thuat_toan=thuat_toan,
        version=version,
        n_train=len(train),
        n_test=len(test),
        artifact_path=duong_dan,
        feature_importance=_quan_trong(bo, t.ten_dac_trung),
        scaler_params=tham_so_scaler,
        xem_nhanh=xem_nhanh,
    )


SQL_CHEN = """
INSERT INTO ml_models
    (version, algorithm, feature_version, dataset_version, hyperparams,
     scaler_params, feature_importance, n_train, n_test, artifact_path,
     is_active, note)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def ghi_mo_hinh(cn, kq: KetQuaHuanLuyen, dataset: str, kich_hoat: bool) -> int:
    with cn.cursor() as cur:
        if kich_hoat:
            # Đúng một mô hình được phục vụ. Hạ cờ của mọi mô hình khác
            # trong cùng giao dịch, nếu không sẽ có hai mô hình `is_active`
            # và việc chọn mô hình nào trở thành ngẫu nhiên theo thứ tự dòng.
            cur.execute("UPDATE ml_models SET is_active = 0 WHERE is_active = 1")
        cur.execute(
            SQL_CHEN,
            (
                kq.version,
                kq.thuat_toan,
                FEATURE_VERSION,
                dataset,
                json.dumps(SIEU_THAM_SO[kq.thuat_toan], ensure_ascii=False),
                json.dumps(kq.scaler_params, ensure_ascii=False),
                json.dumps(kq.feature_importance, ensure_ascii=False),
                kq.n_train,
                kq.n_test,
                str(kq.artifact_path.relative_to(ROOT)).replace("\\", "/"),
                1 if kich_hoat else 0,
                f"Huấn luyện từ tập {dataset}, chia theo người dùng.",
            ),
        )
        cur.execute("SELECT LAST_INSERT_ID() AS id")
        return int(cur.fetchone()["id"])


def main(argv: Sequence[str] | None = None) -> int:
    in_utf8()
    bo_doc = argparse.ArgumentParser(description=__doc__)
    bo_doc.add_argument("--dataset", required=True, help="dataset_version cần dùng")
    bo_doc.add_argument("--db", default=None, help="tên CSDL khác, dùng khi chạy thử")
    bo_doc.add_argument(
        "--algorithm",
        default="all",
        choices=["all", *SIEU_THAM_SO],
        help="mặc định huấn luyện cả ba",
    )
    bo_doc.add_argument("--seed", type=int, default=42)
    bo_doc.add_argument(
        "--apply", action="store_true", help="ghi vào ml_models và lưu tệp mô hình"
    )
    bo_doc.add_argument(
        "--kich-hoat",
        default=None,
        choices=list(SIEU_THAM_SO),
        help="đặt is_active = 1 cho thuật toán này (chỉ cùng --apply)",
    )
    t = bo_doc.parse_args(argv)

    if t.kich_hoat and not t.apply:
        print("--kich-hoat chỉ dùng được cùng --apply.", file=sys.stderr)
        return 1

    cn = ket_noi(t.db)
    try:
        kg, mon_theo_id = nap_khong_gian(cn)
        tap = nap_tap(
            cn, dataset_version=t.dataset, kg=kg, mon_theo_id=mon_theo_id
        )
        if not len(tap):
            print(
                f"Tập dữ liệu {t.dataset!r} không có mẫu nào.\n"
                f"Dựng trước bằng: python -m ml.build_dataset "
                f"--version {t.dataset} --apply"
            )
            return 1

        print(thong_ke(tap))
        train, test = _tach_theo_split(tap)
        print(
            f"  lần chia tham chiếu: train+val {len(train)} mẫu / "
            f"test {len(test)} mẫu"
        )
        print()

        thuat_toan = list(SIEU_THAM_SO) if t.algorithm == "all" else [t.algorithm]
        for tt in thuat_toan:
            version = _version_moi(cn, tt, t.dataset) if t.apply else f"{MA_NGAN[tt]}-thu"
            kq = huan_luyen_mot(
                tap,
                tt,
                dataset=t.dataset,
                version=version,
                seed=t.seed,
                tham_so_khong_gian=kg.tham_so(),
                ghi_tep=t.apply,
            )
            print(f"{tt}  ({kq.version})")
            print(
                f"  n_train={kq.n_train}  n_test={kq.n_test}  "
                f"mae={kq.xem_nhanh['mae']:.4f}  rmse={kq.xem_nhanh['rmse']:.4f}"
            )
            top = list(kq.feature_importance.items())[:5]
            print(
                "  đặc trưng mạnh nhất: "
                + ", ".join(f"{k} {v:+.3f}" for k, v in top)
            )

            if t.apply:
                ma = ghi_mo_hinh(cn, kq, t.dataset, kich_hoat=(t.kich_hoat == tt))
                cn.commit()
                duong_dan = str(kq.artifact_path.relative_to(ROOT)).replace(
                    "\\", "/"
                )
                print(
                    f"  đã ghi ml_models.id={ma}, tệp {duong_dan}"
                    + ("  [is_active = 1]" if t.kich_hoat == tt else "")
                )
            print()

        if not t.apply:
            print("Chạy thử — chưa ghi gì. Thêm --apply để lưu mô hình.")
        return 0
    finally:
        cn.close()


if __name__ == "__main__":
    raise SystemExit(main())
