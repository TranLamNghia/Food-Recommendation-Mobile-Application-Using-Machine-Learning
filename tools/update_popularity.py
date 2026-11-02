#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tính `foods.popularity_score` từ tín hiệu thật.

Việc số 9 của `ML_PIPELINE.md` §12. Cột này hiện bằng 0 ở **cả 318 món** vì
nó mới chỉ có `DEFAULT 0` mà chưa ai tính, và hậu quả nặng hơn vẻ ngoài:
§10.1 đặt `popularity` làm phương án đối chứng **bắt buộc phải vượt qua**,
nên nếu nó bằng nhau ở mọi món thì nó không xếp hạng được gì — mọi món hòa
điểm, và câu hỏi nghiên cứu cốt lõi thành một phép so với nhiễu.

Công thức, định nghĩa "đã thấy / đã thích", và lý do dùng chặn dưới Wilson
đều ở `ml/popularity.py`. Tệp này chỉ là lớp vỏ dòng lệnh.

Lưu ý quan trọng: điểm ghi ở đây tính từ **toàn bộ** tín hiệu, nên nó đúng
cho việc **phục vụ** nhưng không được dùng khi **đánh giá** —
`ml/evaluate.py` tự dựng lại độ phổ biến từ riêng các fold huấn luyện. Xem
phần đầu `ml/popularity.py`.

Chạy:
    python tools/update_popularity.py            # chạy thử, không ghi
    python tools/update_popularity.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.db import in_utf8, ket_noi  # noqa: E402
from ml.popularity import tu_csdl  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    in_utf8()
    bo = argparse.ArgumentParser(description=__doc__)
    bo.add_argument("--db", default=None)
    bo.add_argument("--apply", action="store_true", help="ghi vào foods")
    t = bo.parse_args(argv)

    cn = ket_noi(t.db)
    try:
        dong = tu_csdl(cn)
        co_tin_hieu = sum(1 for d in dong if int(d["n_thay"]) > 0)
        doi = sum(1 for d in dong if abs(d["diem"] - float(d["cu"])) > 1e-9)

        print(f"{len(dong)} món · {co_tin_hieu} món có tín hiệu")
        if co_tin_hieu == 0:
            print(
                "\nChưa có tín hiệu nào từ người dùng — mọi món vẫn nhận 0.\n"
                "Đây KHÔNG phải lỗi: `popularity_score` là đại lượng suy ra từ\n"
                "hành vi, nên nó chỉ có nghĩa sau khi thu được dữ liệu thật\n"
                "(ML_PIPELINE.md §11.3). Cho tới lúc đó, phương án đối chứng\n"
                "`popularity` vẫn suy biến và `ml/evaluate.py` sẽ tiếp tục báo\n"
                "rằng phép so chưa có hiệu lực."
            )
            return 0

        xep = sorted(
            (
                (d["diem"], int(d["n_thich"]), int(d["n_thay"]), d["name"])
                for d in dong
                if int(d["n_thay"]) > 0
            ),
            reverse=True,
        )
        print(f"\n{'điểm':>7}  {'thích/thấy':>11}  món")
        for diem, nt, nx, ten in xep[:10]:
            print(f"{diem:>7.4f}  {nt:>5}/{nx:<5}  {ten}")
        if len(xep) > 10:
            print(f"   … còn {len(xep) - 10} món")

        print(f"\n{doi} món có điểm thay đổi.")
        if not t.apply:
            print("Chạy thử — chưa ghi gì. Thêm --apply để ghi vào foods.")
            return 0

        with cn.cursor() as cur:
            cur.executemany(
                "UPDATE foods SET popularity_score = %s WHERE id = %s",
                [(d["diem"], d["id"]) for d in dong],
            )
        cn.commit()
        print(f"Đã cập nhật popularity_score cho {len(dong)} món.")
        return 0
    finally:
        cn.close()


if __name__ == "__main__":
    raise SystemExit(main())
