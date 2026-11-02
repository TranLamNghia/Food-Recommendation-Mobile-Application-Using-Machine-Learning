# -*- coding: utf-8 -*-
"""Chấm điểm một món cho một người — bốn giai đoạn, một chỗ duy nhất.

Vì sao tệp này tách riêng. Điểm ưa thích được tính ở **hai nơi khác nhau**:

    ml/evaluate.py  — khi đánh giá, để báo cáo con số trong Chương 3
    ml/serve.py     — khi phục vụ, để sinh thực đơn cho người dùng thật

Nếu hai nơi tự cài công thức riêng thì con số báo cáo không còn nói về hệ
thống đang chạy. Và đó là loại lệch **không ai phát hiện ra**: cả hai bên đều
chạy, đều trả về số trong [0, 1], chỉ là chúng mô tả hai hệ thống khác nhau.
Nên mọi công thức chấm điểm nằm ở đây, và cả hai bên đều gọi vào.

Mọi hàm ở đây là **hàm thuần**: nhận số, trả số, không chạm CSDL. Nhờ vậy
`tools/check_ml.py` kiểm được chúng mà không cần CSDL, và kiểm được cả những
ca biên mà dữ liệu thật không có.

Thang điểm chung là [0, 1] cho cả bốn giai đoạn. Đây là điều kiện để công
thức trộn `α·ML + (1−α)·cosin` có nghĩa — hai số cùng thang thì trộn được,
khác thang thì phép trộn là vô nghĩa dù vẫn ra một con số.
"""

from __future__ import annotations

from typing import Sequence

from .features import cosine_similarity
from .rocchio import alpha

#: Tỷ lệ trộn giữa độ phổ biến và độ khớp macro ở Giai đoạn 0.
#:
#: Một tỷ lệ **đặt tay**, nêu ra thành hằng số có tên thay vì giấu trong một
#: biểu thức. Nửa–nửa vì ở Giai đoạn 0 hệ thống chưa biết gì về người này:
#: không có cơ sở nào để tin độ phổ biến hơn độ khớp dinh dưỡng hay ngược lại.
TRONG_SO_PHO_BIEN_GIAI_DOAN_0 = 0.5

#: Điểm trung tính. Trả về khi không có cơ sở nào để xếp món này trên hay
#: dưới món khác — hồ sơ sở thích rỗng, hoặc không có mô hình nào hoạt động.
#: Dùng 0,5 chứ không dùng 0: điểm 0 nghĩa là "không thích", khác hoàn toàn
#: với "chưa biết", và hạ mọi món xuống 0 sẽ làm Bước 4 mất hết thông tin xếp
#: hạng.
DIEM_TRUNG_TINH = 0.5


def diem_pho_bien(do_pho_bien: float) -> float:
    """Giai đoạn đối chứng tầm thường — chỉ độ phổ biến, bỏ qua cá nhân hóa.

    `foods.popularity_score` vốn đã nằm trong [0, 1] (`DECIMAL(5,4)`), nên
    không cần quy đổi gì. Kẹp lại để một dòng dữ liệu lỗi không đẩy điểm ra
    ngoài thang chung.
    """
    return min(1.0, max(0.0, do_pho_bien))


def do_khop_macro(
    v_mon: Sequence[float], muc_tieu_macro_pct: Sequence[float]
) -> float:
    """Món này khớp tỷ lệ macro mục tiêu của người dùng đến đâu, trong [0, 1].

        khớp = 1 − (tổng sai lệch tuyệt đối) / 2

    Chia 2 vì hai vector tỷ lệ đều cộng lại bằng 1, nên tổng sai lệch tuyệt
    đối giữa chúng tối đa là 2 — chia 2 đưa về đúng [0, 1] mà không phải kẹp.

    Ba chiều đầu của vector món là tỷ lệ **năng lượng** từ đạm / bột đường /
    béo, và `health_profiles.target_*_pct` cũng là tỷ lệ năng lượng, nên hai
    bên so được trực tiếp sau khi chia 100.
    """
    if len(v_mon) < 3:
        raise ValueError("vector món phải có ít nhất 3 chiều macro")
    if len(muc_tieu_macro_pct) != 3:
        raise ValueError("mục tiêu macro phải gồm đúng 3 phần trăm")

    tong_pct = sum(muc_tieu_macro_pct)
    if tong_pct <= 0:
        return DIEM_TRUNG_TINH
    # Chuẩn hóa về tổng 1 thay vì chia cứng cho 100: `chk_macro_sum` bắt tổng
    # phải bằng 100, nhưng nếu ràng buộc đó có ngày bị nới thì phép so vẫn
    # đúng thay vì lệch âm thầm.
    mt = [x / tong_pct for x in muc_tieu_macro_pct]
    lech = sum(abs(a - b) for a, b in zip(v_mon[:3], mt))
    return max(0.0, 1 - lech / 2)


def diem_luat(
    v_mon: Sequence[float],
    muc_tieu_macro_pct: Sequence[float],
    do_pho_bien: float,
) -> float:
    """Giai đoạn 0 — chưa có tín hiệu nào về khẩu vị.

    Trộn độ phổ biến với độ khớp macro mục tiêu. Phần lọc bệnh lý **không**
    nằm ở đây: `F1` áp cho mọi giai đoạn như nhau nên nó không phân biệt được
    giai đoạn nào hơn, và gộp nó vào hàm chấm điểm sẽ trộn lẫn một quyết định
    về **an toàn** với một quyết định về **sở thích**. Hai thứ đó phải tách
    nhau, nếu không thì khi phải giải thích vì sao một món bị bỏ sẽ không gỡ
    ra được là do bệnh lý hay do khẩu vị.
    """
    w = TRONG_SO_PHO_BIEN_GIAI_DOAN_0
    return w * diem_pho_bien(do_pho_bien) + (1 - w) * do_khop_macro(
        v_mon, muc_tieu_macro_pct
    )


def diem_noi_dung(p_u: Sequence[float], v_mon: Sequence[float]) -> float:
    """Giai đoạn 1 — `(1 + cos(p_u, vᵢ)) / 2`.

    Hồ sơ rỗng trả về điểm trung tính, đúng như `PreferenceProfile.score`
    phía Dart: khi mọi trọng số bằng 0 thì góc không xác định, và mọi món
    phải nhận cùng một điểm để thứ tự do các tiêu chí khác quyết định.
    """
    if not any(p_u):
        return DIEM_TRUNG_TINH
    return (1 + cosine_similarity(p_u, v_mon)) / 2


def tron(diem_ml: float, diem_noi_dung_: float, n_signals: int) -> float:
    """Chuyển tiếp mượt — `α·ML + (1−α)·cosin`, α theo `n_signals`.

    Không chuyển đột ngột khi vừa vượt ngưỡng, vì người dùng sẽ thấy thực đơn
    đổi bất thường ngay trong một ngày.
    """
    a = alpha(n_signals)
    return a * diem_ml + (1 - a) * diem_noi_dung_
