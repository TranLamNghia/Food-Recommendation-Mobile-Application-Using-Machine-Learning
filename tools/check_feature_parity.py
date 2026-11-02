#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm chứng chéo hai bản trích chọn đặc trưng — Python và Dart.

Vì sao cần. Mô hình được huấn luyện bằng `ml/features.py` nhưng chạy thật
bằng `mobile/lib/data/recommender/food_vector.dart`. Nếu hai bản lệch nhau
một chiều thôi thì mô hình học trên một không gian và suy luận trên một
không gian khác. **Lỗi này không bao giờ báo ra**: mô hình vẫn chạy, vẫn trả
về điểm số, chỉ là điểm số sai — nên nó phải bị bắt bằng một phép kiểm chủ
động, không phải bằng việc nhìn kết quả.

Cách làm. Bản Python nạp toàn bộ món từ CSDL, dựng vector, rồi ghi cả **đầu
vào** lẫn **đầu ra mong đợi** vào một tệp mẫu JSON. Bài kiểm Dart đọc tệp đó,
tự dựng không gian đặc trưng từ cùng tập món ấy, và đối chiếu:

    · danh sách nhóm món và số chiều
    · sáu tham số min–max của phép chuẩn hóa
    · từng chiều của từng món

Tệp mẫu được giao nộp cùng mã nguồn, nên bài kiểm Dart chạy được mà không
cần CSDL — chỉ khi dữ liệu món đổi thì mới phải sinh lại.

Chạy:
    python tools/check_feature_parity.py           # sinh mẫu rồi gọi flutter test
    python tools/check_feature_parity.py --chi-sinh  # chỉ sinh tệp mẫu
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.db import in_utf8, ket_noi  # noqa: E402
from ml.features import KhongGianDacTrung, nap_mon  # noqa: E402

MAU = ROOT / "mobile" / "test" / "fixtures" / "food_vector_parity.json"
BAI_KIEM = "test/food_vector_parity_test.dart"


def sinh_mau() -> tuple[Path, int, int]:
    """Nạp món từ CSDL, dựng vector, ghi tệp mẫu. Trả về (đường dẫn, số món, số chiều)."""
    cn = ket_noi()
    try:
        mon, bao_cao = nap_mon(cn)
    finally:
        cn.close()

    bao_cao.in_ra()

    kg = KhongGianDacTrung.tu_mon(mon)

    mau = {
        "_doc": (
            "Tệp sinh tự động bởi tools/check_feature_parity.py — đừng sửa tay. "
            "Chứa đầu vào và vector mong đợi do bản Python dựng, để bài kiểm "
            "Dart đối chiếu từng chiều."
        ),
        "feature_version": kg.tham_so()["feature_version"],
        "sinh_luc": datetime.now().isoformat(timespec="seconds"),
        "scaler": kg.tham_so(),
        "labels": kg.labels,
        "length": kg.length,
        "foods": [
            {
                "id": m.id,
                "name": m.name,
                "category": m.category,
                "dishRole": m.dish_role,
                "spiceLevel": m.spice_level,
                "kcal": m.kcal,
                "protein": m.protein,
                "carb": m.carb,
                "fat": m.fat,
                "sugar": m.sugar,
                "sodium": m.sodium,
                "fiber": m.fiber,
                "servingSizeG": m.serving_size_g,
                "suyRa": list(m.suy_ra),
            }
            for m in mon
        ],
        "vectors": [kg.encode(m) for m in mon],
    }

    MAU.parent.mkdir(parents=True, exist_ok=True)
    MAU.write_text(
        json.dumps(mau, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return MAU, len(mon), kg.length


def chay_bai_kiem_dart() -> int:
    flutter = shutil.which("flutter")
    if flutter is None:
        print(
            "\nKhông thấy `flutter` trong PATH — đã sinh tệp mẫu, "
            "chạy phần Dart bằng tay:\n"
            f"    cd mobile && flutter test {BAI_KIEM}"
        )
        return 0

    print(f"\n$ flutter test {BAI_KIEM}")
    ket_qua = subprocess.run(
        [flutter, "test", BAI_KIEM],
        cwd=ROOT / "mobile",
        text=True,
    )
    return ket_qua.returncode


def main() -> int:
    in_utf8()
    bo_doc = argparse.ArgumentParser(description=__doc__)
    bo_doc.add_argument(
        "--chi-sinh",
        action="store_true",
        help="chỉ sinh tệp mẫu, không gọi flutter test",
    )
    tham_so = bo_doc.parse_args()

    duong_dan, so_mon, so_chieu = sinh_mau()
    print(
        f"\nĐã ghi {duong_dan.relative_to(ROOT)} — "
        f"{so_mon} món × {so_chieu} chiều."
    )

    if tham_so.chi_sinh:
        return 0
    return chay_bai_kiem_dart()


if __name__ == "__main__":
    raise SystemExit(main())
