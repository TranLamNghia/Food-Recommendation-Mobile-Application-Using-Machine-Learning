# -*- coding: utf-8 -*-
"""Độ phổ biến của món — chặn dưới Wilson trên tỷ lệ người thích.

Hai cách tính, cùng một công thức, khác nhau ở **phạm vi dữ liệu**:

    tu_csdl()   — từ toàn bộ tín hiệu. Dùng khi phục vụ: `tools/update_popularity.py`
                  ghi kết quả vào `foods.popularity_score`.
    tu_tap_mau()— chỉ từ các fold huấn luyện. Dùng khi đánh giá.

## Vì sao phải có bản thứ hai

Phát hiện khi chạy `tools/check_ml_e2e.py` với nhãn **ngẫu nhiên**: phương án
`popularity` đạt nDCG@5 = 0,796 — gần như hoàn hảo trên dữ liệu không có quy
luật nào. Và AUC của mô hình `ml` nhảy từ 0,48 lên 0,67.

Nguyên nhân chung: `popularity_score` được tính từ **mọi** tín hiệu, kể cả
tín hiệu của những người dùng nằm trong fold kiểm tra. Một món mà chính người
bị kiểm đã thích thì đã góp phần đẩy điểm phổ biến của nó lên — nên "độ phổ
biến" khi đó mang sẵn thông tin về **nhãn** của tập kiểm tra. Rò rỉ này vào
cả hai chỗ:

1.  phương án đối chứng `popularity`, làm nó mạnh lên một cách không thật;
2.  đặc trưng `mon.do_pho_bien` của mô hình, làm chính mô hình rò rỉ theo.

Khi **phục vụ** thì không có rò rỉ: độ phổ biến tính từ quá khứ và dùng cho
người dùng trong tương lai. Rò rỉ chỉ xuất hiện trong phép đánh giá ngoại
tuyến, nơi "quá khứ" và "tương lai" bị cắt theo người dùng chứ không theo
thời gian. Nên bản `tu_tap_mau` tồn tại đúng để dùng trong `ml/evaluate.py`.

## Định nghĩa: đếm NGƯỜI, không đếm lượt

    n_thấy(món)  = số người dùng phân biệt có **bất kỳ** tín hiệu nào về món
    n_thích(món) = số người dùng phân biệt có **ít nhất một** tín hiệu dương

Một người dùng nhiệt tình ăn cùng một món hai mươi lần sẽ một mình đẩy món đó
lên đầu bảng nếu đếm lượt, trong khi "phổ biến" phải có nghĩa là *nhiều
người* thích.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

#: Mức tin cậy 95 % → z = 1,96.
Z = 1.959963984540054

#: Đánh giá từ bao nhiêu sao trở lên được tính là tín hiệu dương.
#: 4 sao, không phải 3: 3 sao mang nhãn 0,500 — đúng điểm trung tính — nên
#: tính nó là "thích" sẽ đẩy mọi món trung bình lên.
SAO_DUONG = 4

#: `meal_plan_items.status` được tính là dương. `suggested` không có mặt:
#: người dùng chưa quyết định gì. `replaced` và `skipped` là tín hiệu âm nên
#: chỉ vào mẫu số.
TRANG_THAI_DUONG = ("kept", "eaten")


def wilson_chan_duoi(so_duong: int, so_mau: int, z: float = Z) -> float:
    """Chặn dưới khoảng tin cậy Wilson cho một tỷ lệ.

                p̂ + z²/2n  −  z·√( p̂(1−p̂)/n + z²/4n² )
        thấp =  ────────────────────────────────────────
                            1 + z²/n

    Vì sao không dùng thẳng `so_duong / so_mau`: một món được đưa cho 2 người
    và cả 2 đều thích sẽ ra tỷ lệ 1,00, đứng trên một món được đưa cho 100
    người và 90 người thích (0,90). Đó là kết luận sai — cỡ mẫu 2 không chứng
    minh được gì. Chặn dưới Wilson trả lời đúng câu cần hỏi: *tỷ lệ thích
    thật sự của món này ít nhất là bao nhiêu?*

        2/2   → 0,3424      90/100 → 0,8256      0/10 → 0,0000
        1/1   → 0,2065      9/10   → 0,5958

    Nhờ vậy món ít dữ liệu bị kéo về 0 một cách tự nhiên, không cần đặt tay
    một ngưỡng "tối thiểu N người" nào.

    Trả 0 khi chưa có mẫu nào. Đó là một lựa chọn, không phải sự thật: 0 ở
    đây nghĩa là "chưa chứng minh được là phổ biến", không phải "không ai
    thích". Lấy trung bình toàn danh mục cho chúng thì sẽ **bịa ra** một độ
    phổ biến mà không ai từng thể hiện.

    Kẹp về [0, 1] vì sai số dấu phẩy động có thể cho ra −1e−17, và cột
    `DECIMAL(5,4)` sẽ từ chối một giá trị âm.
    """
    if so_mau <= 0:
        return 0.0
    if so_duong < 0 or so_duong > so_mau:
        raise ValueError(f"số dương {so_duong} không hợp lệ với cỡ mẫu {so_mau}")

    p = so_duong / so_mau
    z2 = z * z
    tu = p + z2 / (2 * so_mau) - z * math.sqrt(
        p * (1 - p) / so_mau + z2 / (4 * so_mau * so_mau)
    )
    mau = 1 + z2 / so_mau
    return min(1.0, max(0.0, tu / mau))


# ── Từ toàn bộ tín hiệu trong CSDL ────────────────────────────────────

# Mỗi nguồn góp hai tập người dùng: "đã thấy" và "đã tỏ ra thích". Viết bằng
# `UNION` để một người có nhiều tín hiệu về cùng một món chỉ được đếm một
# lần — `COUNT(DISTINCT user_id)` ở ngoài làm phần đó.
SQL_DEM = f"""
WITH da_thay AS (
    SELECT food_id, user_id FROM interactions
    UNION
    SELECT food_id, user_id FROM feedbacks
    UNION
    SELECT food_id, user_id FROM food_diary
    UNION
    SELECT mpi.food_id, mp.user_id
    FROM meal_plan_items mpi
    JOIN meal_plans mp ON mp.id = mpi.meal_plan_id
    WHERE mpi.status <> 'suggested'
),
da_thich AS (
    SELECT food_id, user_id FROM interactions WHERE action = 'like'
    UNION
    SELECT food_id, user_id FROM feedbacks WHERE rating >= {SAO_DUONG}
    UNION
    SELECT food_id, user_id FROM food_diary
    UNION
    SELECT mpi.food_id, mp.user_id
    FROM meal_plan_items mpi
    JOIN meal_plans mp ON mp.id = mpi.meal_plan_id
    WHERE mpi.status IN {TRANG_THAI_DUONG}
)
SELECT f.id, f.name, f.popularity_score AS cu,
       (SELECT COUNT(DISTINCT user_id) FROM da_thay  t WHERE t.food_id = f.id)
           AS n_thay,
       (SELECT COUNT(DISTINCT user_id) FROM da_thich h WHERE h.food_id = f.id)
           AS n_thich
FROM foods f
ORDER BY f.name, f.id
"""


def tu_csdl(cn) -> list[dict[str, Any]]:
    """Đếm người theo từng món trên **toàn bộ** tín hiệu.

    Trả về danh sách dòng kèm `n_thay`, `n_thich` và `diem` đã tính. Không
    ghi gì — `tools/update_popularity.py` quyết định việc ghi.
    """
    with cn.cursor() as cur:
        cur.execute(SQL_DEM)
        dong = cur.fetchall()

    for d in dong:
        d["diem"] = wilson_chan_duoi(int(d["n_thich"]), int(d["n_thay"]))
    return list(dong)


# ── Chỉ từ các fold huấn luyện ────────────────────────────────────────


def tu_tap_mau(
    user_id: Sequence[str],
    food_id: Sequence[str],
    label: Sequence[float],
    source: Sequence[str],
    chi_so: Sequence[int],
    *,
    nguong_duong: float,
    bo_nguon: frozenset[str] = frozenset({"random_neg"}),
) -> dict[str, float]:
    """Độ phổ biến dựng lại **chỉ từ những mẫu được chỉ định**.

    `chi_so` là các vị trí thuộc fold huấn luyện. Mọi mẫu ngoài danh sách đó
    bị bỏ hoàn toàn, nên điểm trả về không mang thông tin nào của fold kiểm
    tra — đó là cả mục đích.

    Dựng lại từ `ml_training_samples` thay vì đọc `foods.popularity_score`:
    bảng mẫu là thứ duy nhất `ml/evaluate.py` nên nhìn, và nó đã mang sẵn
    `label` nên "tín hiệu dương" quy về `label >= nguong_duong`.

    `random_neg` bị loại khỏi phép đếm. Mẫu âm ngẫu nhiên là món **chưa từng
    hiển thị** cho người đó, nên tính nó vào `n_thấy` là nói rằng người dùng
    đã thấy và đã từ chối một món mà họ chưa bao giờ được đưa ra.
    """
    thay: dict[str, set[str]] = {}
    thich: dict[str, set[str]] = {}

    for i in chi_so:
        if source[i] in bo_nguon:
            continue
        f = food_id[i]
        u = user_id[i]
        thay.setdefault(f, set()).add(u)
        if label[i] >= nguong_duong:
            thich.setdefault(f, set()).add(u)

    return {
        f: wilson_chan_duoi(len(thich.get(f, ())), len(nguoi))
        for f, nguoi in thay.items()
    }
