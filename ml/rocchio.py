# -*- coding: utf-8 -*-
"""Hồ sơ sở thích Rocchio — **bản Python của `preference_profile.dart`**.

Giai đoạn 1 của chiến lược khởi đầu nguội:

        p_u  =  Σ w(aᵢ) · vᵢ  /  Σ |w(aᵢ)|
        w: thích = +1 , trung tính = 0 , không thích = −1
        lượt `unknown` bị loại khỏi **cả tử số lẫn mẫu số**

Vì sao bản Python cũng cần. Hai chỗ dùng tới nó mà ứng dụng Flutter không
chạm được:

1.  `profile_snapshot` khi dựng tập huấn luyện — phải là vector **tại thời
    điểm thu tín hiệu**, nên phải phát lại lịch sử vuốt theo thứ tự thời
    gian ở phía máy chủ. Xem `ml/build_dataset.py`.
2.  Phương án đối chứng `content_based` khi đánh giá — chính là phương án mà
    đồ án phải chứng minh hơn `rule_based` và `popularity`.

Lượt `neutral` có trọng số 0 nên không đóng góp vào tử số lẫn mẫu số, **song
vẫn được đếm** vào `n_signals`: nó là một tín hiệu người dùng đã cho, chỉ là
tín hiệu trung tính. Phân biệt này giữ cho `n_signals` đo đúng "đã vuốt bao
nhiêu món", tức là đúng đại lượng mà công thức chuyển giai đoạn α dùng tới.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from .features import FEATURE_VERSION, KhongGianDacTrung, Mon, cosine_similarity

#: `interactions.action` → trọng số Rocchio. `None` nghĩa là loại khỏi phép
#: tính: "tôi chưa biết món này" khác hoàn toàn với "tôi thấy nó bình thường".
#: Gộp `unknown` vào như một giá trị 0 sẽ làm phình mẫu số và kéo vector về
#: gốc, tức làm loãng mọi sở thích thật.
TRONG_SO = {
    "like": 1.0,
    "neutral": 0.0,
    "dislike": -1.0,
    "unknown": None,
}


@dataclass(frozen=True)
class HoSoSoThich:
    """Vector sở thích `p_u` cùng hai đại lượng đi kèm nó trong CSDL."""

    weights: tuple[float, ...]
    sum_abs_weight: float
    n_signals: int

    @property
    def is_empty(self) -> bool:
        """Rỗng khi **mọi trọng số bằng 0**, không phải khi chưa có lượt vuốt.

        Phân biệt này quan trọng vì người dùng có thể khai mục tiêu dinh
        dưỡng trước khi vuốt lượt đầu tiên: hồ sơ khi đó có `n_signals == 0`
        nhưng trọng số khác 0, và vẫn phải xếp hạng được.
        """
        return all(w == 0 for w in self.weights)

    def score(self, kg: KhongGianDacTrung, m: Mon) -> float:
        """Điểm ưa thích trong đoạn [0, 1].

        Cosin nhận giá trị trong [−1, 1]; phép `(1 + cos) / 2` đưa về [0, 1]
        để dùng **chung thang đo** với điểm của mô hình ở Giai đoạn 2 — nhờ
        vậy công thức trộn `α·ML + (1−α)·cosin` không phải quy đổi thang.
        """
        if self.is_empty:
            return 0.5
        return (1 + cosine_similarity(self.weights, kg.encode(m))) / 2

    def to_json(self) -> dict[str, Any]:
        """Dạng ghi vào `user_preference_profiles.weights` / `profile_snapshot`."""
        return {
            "feature_version": FEATURE_VERSION,
            "weights": list(self.weights),
            "sum_abs_weight": self.sum_abs_weight,
            "n_signals": self.n_signals,
        }


def ho_so_rong(kg: KhongGianDacTrung) -> HoSoSoThich:
    return HoSoSoThich(tuple([0.0] * kg.length), 0.0, 0)


def dung_ho_so(
    kg: KhongGianDacTrung,
    luot_vuot: Sequence[tuple[Mon, str]],
) -> HoSoSoThich:
    """Dựng `p_u` từ một dãy lượt vuốt `(món, action)`.

    Mẫu số bằng 0 — cả phiên chỉ toàn `neutral` — thì **giữ vector rỗng**
    thay vì chia cho 0: khi đó mọi món nhận cùng một điểm 0,5 và thứ tự do
    các tiêu chí khác quyết định. Phía Dart làm đúng vậy.
    """
    tong = [0.0] * kg.length
    tong_tri_tuyet_doi = 0.0
    da_dung = 0

    for m, action in luot_vuot:
        if action not in TRONG_SO:
            raise ValueError(
                f"action không hợp lệ: {action!r} — phải thuộc {tuple(TRONG_SO)}"
            )
        w = TRONG_SO[action]
        if w is None:
            continue

        da_dung += 1
        tong_tri_tuyet_doi += abs(w)

        if w != 0.0:
            v = kg.encode(m)
            for i in range(kg.length):
                tong[i] += w * v[i]

    if tong_tri_tuyet_doi > 0:
        tong = [x / tong_tri_tuyet_doi for x in tong]

    return HoSoSoThich(tuple(tong), tong_tri_tuyet_doi, da_dung)


def alpha(n_signals: int, n_min: int = 30, n_max: int = 100) -> float:
    """Hệ số trộn giữa Giai đoạn 1 và Giai đoạn 2.

            α = 0                               nếu n < n_min
                (n − n_min) / (n_max − n_min)    nếu n_min ≤ n ≤ n_max
                1                               nếu n > n_max

    Chuyển dần chứ không chuyển đột ngột, vì người dùng sẽ thấy thực đơn đổi
    bất thường ngay khi vừa vượt ngưỡng.
    """
    if n_max <= n_min:
        raise ValueError("n_max phải lớn hơn n_min")
    if n_signals < n_min:
        return 0.0
    if n_signals > n_max:
        return 1.0
    return (n_signals - n_min) / (n_max - n_min)


def giai_doan(n_signals: int, n_min: int = 30, n_max: int = 100) -> str:
    """Giá trị cho `user_preference_profiles.stage`."""
    if n_signals <= 0:
        return "cold"
    if n_signals < n_min:
        return "content"
    if n_signals <= n_max:
        return "hybrid"
    return "ml"


def do_lech_cosin(a: Sequence[float], b: Sequence[float]) -> float:
    """Khoảng cách góc giữa hai vector, dùng khi so hai hồ sơ với nhau."""
    return math.acos(max(-1.0, min(1.0, cosine_similarity(a, b))))
