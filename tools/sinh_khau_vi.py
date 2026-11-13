# -*- coding: utf-8 -*-
"""Sinh lượt vuốt mô phỏng từ một vector khẩu vị ẩn đã biết trước.

Vì sao tệp này tồn tại
──────────────────────
Tập `f1_user_food_behaviors_50x45.csv` không mang tín hiệu nào: cosine
người–người là +0,0359 trong khi cùng phép đo sau khi xáo ngẫu nhiên từng
người cho +0,0328, tức giá trị thật nằm **trong** dải nhiễu. Phương sai số
lượt `thich` mỗi món chỉ bằng 1,15 lần phương sai nhị thức (sd của tỉ số này
ở 45 món là 0,21). Không mô hình nào học được gì từ đó, nên Chương 3 sẽ chỉ
đo lại mức đa số 41,0%.

Tệp này thay nhiễu bằng **mô phỏng có ground truth**: mỗi người ảo nhận một
vector khẩu vị ẩn `t_u` trong chính không gian 20 chiều mà hệ thống dùng, rồi
lựa chọn được rút ra từ độ gần giữa `t_u` và vector món. Khác biệt với tệp cũ
không phải "có tín hiệu mạnh hơn" mà là **biết trước đáp án**: Chương 3 đo
được `cos(p_u, t_u)` — hồ sơ Rocchio khôi phục lại vector ẩn tới mức nào —
chứ không chỉ đo độ chính xác trên một tập kiểm chẳng ai biết nhãn đúng.

Đây là dữ liệu MÔ PHỎNG và phải được viết đúng như vậy trong báo cáo. Nó
chứng minh **mô hình chạy đúng** (khôi phục được cái đã biết), không chứng
minh **người Việt ăn gì**. Hai câu đó khác nhau, và chỉ câu đầu mới đo được
bằng dữ liệu sinh ra.

Mô hình sinh
────────────
1.  **5 khẩu vị nguyên mẫu** `c_1..c_5`: tâm của 5 cụm k-means trên chính 45
    vector món. Lấy từ dữ liệu món chứ không bốc tay, vì hồ sơ Rocchio
    `p_u = Σ w·v / Σ|w|` là một **trung bình có dấu của vector món** — nó chỉ
    biểu diễn được những hướng nằm trong vùng mà vector món phủ tới. Một
    `t_u` bốc đều trong [0,1]^20 sẽ nằm ngoài vùng đó, và cosine khôi phục sẽ
    thấp vì lý do hình học, không phải vì mô hình học kém.

2.  **Vector ẩn của từng người**: `t_u = c_{z1} + λ·c_{z2} + σ·N(0, I) + δ_u`,
    với `z1` là nguyên mẫu chính và `z2 ≠ z1` là nguyên mẫu phụ.
    `z1` chia vòng tròn nên đúng 10 người mỗi nguyên mẫu — bốc đa thức có
    thể để trống một nguyên mẫu ở n = 50, và khi đó phép đo cụm mất nghĩa.

    **Vì sao phải trộn hai nguyên mẫu.** Bản đầu dùng đúng một: `t_u = c_z`.
    Nhưng k-means chạy trên *món*, và một cụm món không phải một khẩu vị
    người. Cụm `Đồ uống` chỉ có 4 trong 45 món, nên 10 người thuộc cụm đó
    thành người "chỉ thích nước ép, không thích 16 món chính" — không có
    người thật nào như vậy. Và hệ quả đo được: `cos(p_u, t_u)` của chính 10
    người đó là 0,02–0,37 trong khi những người khác đạt 0,92–0,95, vì hồ sơ
    Rocchio khi ấy bị phần `không thích` chi phối và trỏ **ra xa** khẩu vị
    thật thay vì trỏ vào nó.

    Trộn một nguyên mẫu phụ với trọng số λ = 0,5 vừa đúng với người thật hơn
    — ai cũng có một gu món chính cộng một gu món phụ — vừa bỏ được trường
    hợp suy biến đó, mà **không** làm nhẹ bài toán: `z1` vẫn chia vòng tròn
    nên cấu trúc cụm cho lọc cộng tác vẫn còn nguyên.

3.  **`δ_u` — phần hồ sơ sức khỏe chi phối khẩu vị.** Chỉ hai cột của
    ObesityDataSet nói về *thức ăn*, nên chỉ hai cột đó được phép tác động:
    `FAVC` (ăn thức ăn nhiều năng lượng thường xuyên) đẩy chiều `Tỷ lệ béo`
    và `Năng lượng`; `FCVC` (tần suất ăn rau, 1–3) đẩy chiều `Chất xơ`. Các
    cột còn lại — `MTRANS`, `TUE`, `SMOKE`… — không liên quan tới khẩu vị,
    và nối chúng vào là tự tạo ra một phát hiện không có thật.

    Biên độ cố tình nhỏ (mặc định 0,10 trên thang [0,1]) để nguyên mẫu vẫn
    là phần chi phối. Nếu hồ sơ chi phối khẩu vị thì bài toán gợi ý biến
    thành bài toán hồi quy trên hồ sơ, và Bước 2 trở thành vô dụng — tức là
    mô phỏng đã tự trả lời mất câu hỏi mà đồ án đặt ra.

4.  **`chua_biet` độc lập với khẩu vị.** "Chưa từng ăn" là tính chất của
    *món* — món lạ thì nhiều người chưa ăn — nên mỗi món nhận một xu hướng
    `q_i ~ Beta` trung bình 0,16, rồi mỗi người rút Bernoulli(`q_i`). Cho
    `chua_biet` phụ thuộc khẩu vị là sai cả về nghĩa lẫn về hệ quả: nó biến
    dữ liệu thiếu thành *missing not at random*, và khi đó vector Rocchio
    lệch có hệ thống dù công thức đúng.

5.  **Ba mức còn lại rút bằng ordered logit.** `y* = β·z(s) + ε`, với
    `s = cos(t_u, v_i)`, `z` là chuẩn hóa toàn cục, `ε ~ Logistic(0,1)`. Hai
    điểm cắt lấy đúng tại phân vị của `y*` ứng với tỉ lệ biên của tệp gốc
    (`khong_thich` 25,8%, `binh_thuong` 33,2%, `thich` 41,0% trong số lượt đã
    đánh), nên phân bố biên **trùng tệp gốc** và hai tệp so được với nhau.

    `ε` chính là nhiễu nhãn, không cần thêm bước đảo nhãn: β điều khiển tỉ số
    giữa tín hiệu và nhiễu. β quá lớn thì bài toán thành tách tuyến tính
    hoàn hảo và mọi mô hình đều đạt ~100% — một kết quả không nói lên gì.

Chạy
────
    python tools/sinh_khau_vi.py                       # xem trước, không ghi
    python tools/sinh_khau_vi.py --ghi
    python tools/check_mo_phong.py                     # kiểm có tín hiệu thật

Cần CSDL — chỉ để đọc `conditions` và `condition_rules` cho phần ràng buộc ở
mục 6 dưới đây. Vector món thì đã nằm sẵn trong `survey_deck.json`.

6.  **Ràng buộc sức khỏe, và nhiễu lẫn mà chúng tạo ra.** `ObesityDataSet`
    không có cột bệnh lý nào, nên nếu không gán gì thì Bộ lọc F1 loại 0/2250
    lượt và **tầng an toàn của cả hệ thống không có một dòng bằng chứng nào**
    trong Chương 3.

    Mỗi người được gán bệnh lý / dị ứng / chế độ ăn theo `HAN_MUC_DIEU_KIEN`,
    **độc lập hoàn toàn với `t_u`** — điều kiện bắt buộc của phép đo, vì
    ràng buộc tương quan với khẩu vị thì không tách được phần F1 gỡ ra khỏi
    phần khẩu vị thật. Sau đó, với mỗi món mà F1 không cho người đó ăn, lựa
    chọn bị **ghi đè thành `khong_thich`** (xác suất 0,85, phần còn lại là
    `chua_biet`).

    Phép ghi đè đó chính là **nhiễu lẫn mà F1-lúc-nhập tồn tại để gỡ**:
    phiếu giấy dùng một bộ món cố định nên người ăn thuần chay buộc phải
    đánh giá cả phở bò, và mô hình đọc `khong_thich` đó là "không thích phở"
    thay vì "ăn thuần chay". `t_u` thì **không đổi** — nó vẫn là vector khẩu
    vị thật. Nhờ vậy `check_mo_phong.py` đo được đúng câu hỏi: lọc F1 trước
    khi dựng vector có đưa `p_u` về gần `t_u` hơn không.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _env import in_utf8  # noqa: E402

from ml.db import ket_noi  # noqa: E402

# `SEVERITY_PHIEU` phải là **cùng một giá trị** với mức độ mà trình nhập ghi
# vào `user_conditions`: phiếu giấy không hỏi mức độ, nên nếu bộ sinh dùng
# `mild` mà trình nhập ghi `moderate` thì F1 lúc sinh loại một tập món khác
# F1 lúc nhập, trên cùng một người. Với `Gút`, khác biệt đó là 0 món đối lại
# 11 món, vì `condition_rules.severity_min` gác từng quy tắc.
from tools.import_swipes import SEVERITY_PHIEU  # noqa: E402
DECK = ROOT / "data" / "survey" / "survey_deck.json"
HO_SO = ROOT / "data" / "survey" / "f1_training_dataset_50_users.csv"
RA_THU_MUC = ROOT / "data" / "survey" / "mo_phong"
RA_HANH_VI = RA_THU_MUC / "hanh_vi.csv"
RA_SU_THAT = RA_THU_MUC / "khau_vi_that.json"

#: Tên 20 chiều, đúng thứ tự `KhongGianDacTrung.encode`: 8 chiều cố định rồi
#: one-hot nhóm món theo thứ tự `sorted()`. Phần one-hot được **suy lại từ
#: chính deck** trong `nhan_chieu()` chứ không gõ tay, vì thứ tự phụ thuộc
#: tập 318 món trong CSDL — gõ tay thì nó đúng tới lần ai đó thêm một nhóm.
NHAN_CO_DINH = (
    "Tỷ lệ đạm",
    "Tỷ lệ bột đường",
    "Tỷ lệ béo",
    "Năng lượng",
    "Vị ngọt",
    "Vị mặn",
    "Chất xơ",
    "Mức cay",
)

#: Chiều mà `FAVC`/`FCVC` được phép đẩy. Khóa là tên chiều, không phải chỉ số:
#: chỉ số 2 hôm nay là `Tỷ lệ béo`, và sẽ không còn là nó nếu tập chiều đổi.
CHIEU_FAVC = ("Tỷ lệ béo", "Năng lượng")
CHIEU_FCVC = ("Chất xơ",)

#: Tỉ lệ biên của tệp gốc, trong số lượt **đã đánh** (bỏ `chua_biet`):
#: 488 / 628 / 774 trên 1890. Giữ nguyên để hai tệp so được với nhau.
TI_LE_BIEN = {"khong_thich": 488 / 1890, "binh_thuong": 628 / 1890}

#: Tỉ lệ `chua_biet` của tệp gốc: 360 / 2250.
TI_LE_CHUA_BIET = 360 / 2250

#: Độ tập trung của `Beta` sinh xu hướng `chua_biet` từng món. Càng lớn thì
#: các món càng giống nhau; 6,0 cho khoảng xấp xỉ 0,03–0,40, tức có món hầu
#: như ai cũng từng ăn và có món hơn một phần ba chưa ăn.
BETA_CHUA_BIET = 6.0

MUC = ("khong_thich", "binh_thuong", "thich", "chua_biet")

#: Số người được gán mỗi điều kiện, trên 50 người.
#:
#: **Đây là phép lấy mẫu PHÂN TẦNG có chủ ý, không phải tỉ lệ dịch tễ.** Tỉ
#: lệ thật ở Việt Nam cho 50 người sẽ ra 1–2 người có ràng buộc cứng, và với
#: 1–2 người thì không đo được gì về Bộ lọc F1 — tầng an toàn của cả hệ
#: thống sẽ không có một dòng bằng chứng nào trong Chương 3. Nên tập này
#: **cố ý giàu ràng buộc**: 20/50 người có ít nhất một ràng buộc cứng.
#:
#: Điều này PHẢI được ghi vào báo cáo đúng như vậy. Nó làm tập mẫu không còn
#: đại diện cho dân số về tỉ lệ bệnh, và mọi con số kiểu "x% người dùng bị
#: loại y món" đọc từ tập này đều vô nghĩa. Thứ đo được là **cơ chế**: khi
#: một người có ràng buộc, F1 có gỡ đúng phần ràng buộc ra khỏi khẩu vị
#: không.
#:
#: Số món bị loại khỏi bộ 45 món, đo bằng `ly_do_loai` ở mức `moderate`:
#:
#:     Ăn thuần chay 24 · Ăn chay 24 · Gút 11 · Dị ứng hải sản 11
#:     Dị ứng đậu nành 5 · Dị ứng trứng 3 · Dị ứng đậu phộng 2
#:     Không dung nạp gluten 2
#:     Đái tháo đường 0 · Tăng huyết áp 0 · Bệnh thận 0 · Rối loạn mỡ máu 0
#:
#: Bốn dòng cuối loại **0 món** vì quy tắc của chúng là ngưỡng mềm theo ngày
#: (`scope = 'per_day'`), do Bước 4 pha 5 thi hành chứ không phải F1. Chúng
#: vẫn được gán — chúng là nhóm phổ biến nhất và chúng chạy tầng quy tắc
#: mềm — nhưng phép so "có F1 / không F1" chỉ dựa trên tám dòng đầu.
HAN_MUC_DIEU_KIEN = {
    # Bệnh chuyển hóa: gán theo nguy cơ từ BMI và tuổi, xem `gan_dieu_kien`.
    "Tăng huyết áp": 12,
    "Đái tháo đường": 7,
    "Rối loạn mỡ máu": 8,
    # Ràng buộc cứng: gán độc lập với khẩu vị.
    "Gút": 5,
    "Dị ứng hải sản": 5,
    "Dị ứng đậu nành": 3,
    "Dị ứng trứng": 2,
    "Dị ứng đậu phộng": 2,
    "Không dung nạp gluten": 2,
    "Ăn chay": 4,
    "Ăn thuần chay": 2,
}

#: Gán theo điểm nguy cơ tính từ hồ sơ, không bốc đều. Giá trị là trọng số
#: của (z-score BMI, z-score tuổi, hệ số nam giới).
#:
#: Tương quan BMI → đái tháo đường / tăng huyết áp là tương quan **thật**, và
#: đưa nó vào làm phần hồ sơ sức khỏe của tập này có nghĩa thay vì chỉ để
#: trang trí. Nhưng nó là tương quan **tôi tiêm vào**, nên phải ghi ra: không
#: ai được đọc tập này rồi kết luận "BMI cao thì dễ đái tháo đường" như một
#: phát hiện.
NGUY_CO = {
    "Tăng huyết áp": (1.0, 0.6, 0.0),
    "Đái tháo đường": (1.0, 0.3, 0.0),
    "Rối loạn mỡ máu": (1.0, 0.2, 0.0),
    "Gút": (0.6, 0.2, 1.0),
}

#: Hai chế độ ăn loại trừ nhau: thuần chay đã bao hàm chay, nên gán cả hai là
#: dư thừa và còn làm `user_conditions` tự mâu thuẫn.
CHE_DO_AN = ("Ăn chay", "Ăn thuần chay")

#: Tối đa bao nhiêu ràng buộc CỨNG trên một người. Không chặn thì một người
#: có thể nhận thuần chay + hải sản + gút và bị F1 loại gần hết bộ món — khi
#: đó họ không còn đóng góp được tín hiệu khẩu vị nào, và trình nạp sẽ dừng.
TOI_DA_RANG_BUOC_CUNG = 2

#: Người có ràng buộc cứng vẫn phải còn lại ít nhất bấy nhiêu lượt dùng được
#: sau khi F1 lọc. Dưới mức này thì bộ món không phù hợp với người đó, và
#: giữ họ lại là giữ một hồ sơ khuyết.
TOI_THIEU_LUOT_CON = 15

#: Xác suất một món bị F1 loại được người trả lời đánh `khong_thich`.
#:
#: Đây là **nhiễu lẫn mà F1-lúc-nhập tồn tại để gỡ**. Phiếu giấy dùng một bộ
#: món cố định cho mọi người, nên người ăn thuần chay buộc phải đánh giá cả
#: phở bò — và họ đánh `khong_thich`. Mô hình đọc đó là "không thích phở"
#: thay vì "ăn thuần chay".
#:
#: Không phải 1,0: có món họ chưa từng ăn nên đánh `chua_biet`. Phần còn lại
#: `1 − 0,85` rơi vào `chua_biet`, không rơi vào `thich` — người ăn thuần
#: chay không đánh `thich` cho phở bò.
XAC_SUAT_LOAI_THANH_KHONG_THICH = 0.85


# ── đại số vector, viết tay để tệp này không cần numpy ────────────────────


def cong(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [x + y for x, y in zip(a, b)]


def nhan(a: Sequence[float], k: float) -> list[float]:
    return [x * k for x in a]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def khoang_cach_binh_phuong(a: Sequence[float], b: Sequence[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


# ── nạp đầu vào ───────────────────────────────────────────────────────────


def nap_deck(duong_dan: Path) -> list[dict[str, Any]]:
    deck = json.loads(duong_dan.read_text(encoding="utf-8"))
    mon = sorted(deck["mon"], key=lambda m: m["thu_tu"])
    if not mon:
        raise SystemExit(f"{duong_dan} không có món nào.")
    d = len(mon[0]["vector"])
    for m in mon:
        if len(m["vector"]) != d:
            raise SystemExit(
                f"món {m['name']!r} có vector {len(m['vector'])} chiều, "
                f"các món khác {d} chiều — deck hỏng."
            )
    return mon


def nhan_chieu(mon: list[dict[str, Any]]) -> list[str]:
    """Tên 20 chiều, phần one-hot suy từ deck."""
    d = len(mon[0]["vector"])
    ten = list(NHAN_CO_DINH) + [f"nhóm #{i}" for i in range(len(NHAN_CO_DINH), d)]
    for m in mon:
        nong = [i for i in range(len(NHAN_CO_DINH), d) if m["vector"][i] == 1.0]
        if len(nong) == 1:
            ten[nong[0]] = f"Nhóm: {m['category']}"
    return ten


def nap_ho_so(duong_dan: Path) -> list[dict[str, str]]:
    """Một dòng mỗi người, lấy dòng đầu gặp của mỗi `user_id`."""
    with duong_dan.open(encoding="utf-8-sig", newline="") as f:
        hang = list(csv.DictReader(f))
    if not hang:
        raise SystemExit(f"{duong_dan} không có dòng dữ liệu nào.")
    thieu = {"user_id", "FAVC", "FCVC", "source_profile_row"} - set(hang[0])
    if thieu:
        raise SystemExit(f"{duong_dan} thiếu cột: {', '.join(sorted(thieu))}")
    theo_nguoi: dict[str, dict[str, str]] = {}
    for h in hang:
        theo_nguoi.setdefault(h["user_id"], h)
    return [theo_nguoi[u] for u in sorted(theo_nguoi)]


# ── k-means trên vector món, để lấy khẩu vị nguyên mẫu ────────────────────


def kmeans(
    diem: list[Sequence[float]], k: int, *, seed: int, so_lan: int = 30
) -> tuple[list[list[float]], list[int]]:
    """Lloyd với khởi tạo k-means++, chạy lại nhiều lần và giữ lần tốt nhất.

    Chạy lại là cần: Lloyd hội tụ về cực tiểu địa phương, nên một lần chạy
    duy nhất cho ra tâm khác nhau theo seed — và khi đó "5 khẩu vị nguyên
    mẫu" không còn là một đại lượng của dữ liệu mà là của hạt giống.
    """
    rnd = random.Random(seed)
    d = len(diem[0])
    tot: tuple[float, list[list[float]], list[int]] | None = None

    for _ in range(so_lan):
        # k-means++: tâm đầu bốc đều, các tâm sau bốc theo D² tới tâm gần nhất.
        tam = [list(diem[rnd.randrange(len(diem))])]
        while len(tam) < k:
            w = [min(khoang_cach_binh_phuong(p, c) for c in tam) for p in diem]
            tong = sum(w)
            if tong == 0.0:
                tam.append(list(diem[rnd.randrange(len(diem))]))
                continue
            moc = rnd.random() * tong
            acc = 0.0
            for p, wi in zip(diem, w):
                acc += wi
                if acc >= moc:
                    tam.append(list(p))
                    break

        gan: list[int] = [0] * len(diem)
        for _buoc in range(100):
            moi = [
                min(range(k), key=lambda j: khoang_cach_binh_phuong(p, tam[j]))
                for p in diem
            ]
            if moi == gan and _buoc:
                break
            gan = moi
            for j in range(k):
                thuoc = [p for p, g in zip(diem, gan) if g == j]
                if thuoc:
                    tam[j] = [sum(p[i] for p in thuoc) / len(thuoc) for i in range(d)]
                else:
                    # Cụm rỗng: dời tâm tới điểm xa tâm của nó nhất, thay vì
                    # bỏ cụm. Bỏ thì k thực tế nhỏ hơn k đã khai.
                    xa = max(
                        range(len(diem)),
                        key=lambda i: khoang_cach_binh_phuong(diem[i], tam[gan[i]]),
                    )
                    tam[j] = list(diem[xa])

        sse = sum(khoang_cach_binh_phuong(p, tam[g]) for p, g in zip(diem, gan))
        if tot is None or sse < tot[0]:
            tot = (sse, [list(c) for c in tam], list(gan))

    assert tot is not None
    return tot[1], tot[2]


# ── sinh ──────────────────────────────────────────────────────────────────


def _z(gt: list[float]) -> list[float]:
    tb = sum(gt) / len(gt)
    sd = math.sqrt(sum((x - tb) ** 2 for x in gt) / max(1, len(gt) - 1)) or 1.0
    return [(x - tb) / sd for x in gt]


def gan_dieu_kien(
    ho_so: list[dict[str, str]], rnd: random.Random
) -> dict[str, list[str]]:
    """Gán bệnh lý / dị ứng / chế độ ăn cho từng người theo `HAN_MUC_DIEU_KIEN`.

    Dùng **hạn mức chính xác** chứ không bốc xác suất: với n = 50 và tỉ lệ
    0,04 thì bốc xác suất ra 0, 1, 2 hay 4 người tùy hạt giống, và khi đó số
    người có ràng buộc là thuộc tính của hạt giống chứ không phải của thiết
    kế. Hạn mức cho đúng con số đã khai, mọi lần chạy.

    Bốn điều kiện trong `NGUY_CO` được gán cho những người có **điểm nguy cơ
    cao nhất** (BMI, tuổi, giới) cộng một lượng nhiễu; phần còn lại gán độc
    lập hoàn toàn. Nhiễu là cần: không có nó thì tập người tăng huyết áp
    chính là tập 12 người BMI cao nhất, một quan hệ hàm số mà mô hình nào
    cũng học được hoàn hảo và không giống thực tế ở chỗ nào cả.

    Ràng buộc **độc lập với khẩu vị** ở mọi trường hợp: điểm nguy cơ chỉ đọc
    hồ sơ sức khỏe, không đọc `vector_khau_vi`. Đây là điều kiện bắt buộc của
    cả phép đo — nếu ràng buộc tương quan với khẩu vị thì không tách được
    phần F1 gỡ ra khỏi phần khẩu vị thật.
    """
    ma = [h["user_id"] for h in ho_so]
    bmi = _z([float(h["Weight"]) / (float(h["Height"]) ** 2) for h in ho_so])
    tuoi = _z([float(h["Age"]) for h in ho_so])
    nam = [1.0 if h["Gender"] == "Male" else 0.0 for h in ho_so]

    ra: dict[str, list[str]] = {u: [] for u in ma}
    cung: dict[str, int] = {u: 0 for u in ma}
    co_che_do: set[str] = set()

    # Thứ tự gán: chế độ ăn trước (loại 24/45 món, nặng nhất), rồi các ràng
    # buộc cứng khác, rồi bệnh chuyển hóa (loại 0 món nên không tranh chỗ).
    # Gán thứ nặng nhất trước thì `TOI_DA_RANG_BUOC_CUNG` chặn đúng chỗ cần
    # chặn; gán ngược lại thì người đã có hai dị ứng nhẹ sẽ loại mất suất ăn
    # chay, và hạn mức chế độ ăn không đạt.
    thu_tu_gan = (
        list(CHE_DO_AN)
        + [
            k
            for k in HAN_MUC_DIEU_KIEN
            if k not in CHE_DO_AN and k not in NGUY_CO
        ]
        + [k for k in NGUY_CO]
    )

    for ten in thu_tu_gan:
        can = HAN_MUC_DIEU_KIEN.get(ten, 0)
        if not can:
            continue
        cung_them = ten not in NGUY_CO or ten == "Gút"

        if ten in NGUY_CO:
            w_bmi, w_tuoi, w_nam = NGUY_CO[ten]
            diem = {
                u: w_bmi * bmi[i]
                + w_tuoi * tuoi[i]
                + w_nam * nam[i]
                + rnd.gauss(0.0, 1.0)
                for i, u in enumerate(ma)
            }
            xep = sorted(ma, key=lambda u: -diem[u])
        else:
            xep = list(ma)
            rnd.shuffle(xep)

        da_gan = 0
        for u in xep:
            if da_gan >= can:
                break
            if ten in CHE_DO_AN and u in co_che_do:
                continue
            if cung_them and cung[u] >= TOI_DA_RANG_BUOC_CUNG:
                continue
            ra[u].append(ten)
            da_gan += 1
            if cung_them:
                cung[u] += 1
            if ten in CHE_DO_AN:
                co_che_do.add(u)
        if da_gan < can:
            raise SystemExit(
                f"không gán đủ {can} người cho {ten!r} (chỉ được {da_gan}) — "
                f"nới TOI_DA_RANG_BUOC_CUNG hoặc giảm hạn mức trong "
                f"HAN_MUC_DIEU_KIEN."
            )

    return {u: sorted(v) for u, v in ra.items()}


def f1_loai_theo_nguoi(
    cn, benh_theo_nguoi: dict[str, list[str]], ma_mon: list[str]
) -> dict[str, list[str]]:
    """Với mỗi người, danh sách món mà Bộ lọc F1 không cho họ ăn.

    Gọi thẳng `ml.f1_filter` — cùng một hàm mà `import_swipes.py`,
    `import_mo_phong.py` và `ml/serve.py` gọi. Viết lại phép lọc ở đây thì
    bộ sinh và trình nạp sẽ lệch nhau, và chỗ lệch đó nghĩa là dữ liệu mô
    phỏng mang một ràng buộc khác với ràng buộc mà hệ thống thi hành.
    """
    from ml.f1_filter import dieu_kien_theo_ten, ly_do_loai

    ra: dict[str, list[str]] = {}
    nho: dict[tuple[str, ...], list[str]] = {}
    for u, ten in benh_theo_nguoi.items():
        khoa = tuple(ten)
        if khoa not in nho:
            if not ten:
                nho[khoa] = []
            else:
                dk = dieu_kien_theo_ten(cn, list(ten), severity=SEVERITY_PHIEU)
                bl = ly_do_loai(cn, dieu_kien=dk, chi_mon_chung=True)
                nho[khoa] = [m for m in ma_mon if bl.get(m)]
        ra[u] = list(nho[khoa])
    return ra


def day_theo_ho_so(
    h: dict[str, str], ten_chieu: list[str], bien_do: float
) -> list[float]:
    """`δ_u` — phần hồ sơ sức khỏe đẩy vector khẩu vị."""
    d = [0.0] * len(ten_chieu)
    chi_so = {t: i for i, t in enumerate(ten_chieu)}

    if (h.get("FAVC") or "").strip().lower() == "yes":
        for t in CHIEU_FAVC:
            d[chi_so[t]] += bien_do

    # FCVC chạy 1–3, mốc giữa là 2. Lệch khỏi mốc giữa bao nhiêu thì đẩy
    # chiều chất xơ bấy nhiêu — ăn ít rau (FCVC = 1) thì đẩy xuống.
    try:
        fcvc = float(h.get("FCVC") or 2.0)
    except ValueError:
        fcvc = 2.0
    for t in CHIEU_FCVC:
        d[chi_so[t]] += bien_do * max(-1.0, min(1.0, fcvc - 2.0))

    return d


def sinh(
    *,
    cn,
    mon: list[dict[str, Any]],
    ho_so: list[dict[str, str]],
    so_nguyen_mau: int,
    lam_phu: float,
    sigma: float,
    beta: float,
    bien_do_ho_so: float,
    seed: int,
) -> dict[str, Any]:
    ten_chieu = nhan_chieu(mon)
    vec = [m["vector"] for m in mon]
    tam, gan_mon = kmeans(vec, so_nguyen_mau, seed=seed)

    # Nhãn cho từng nguyên mẫu: ba món gần tâm nhất. Một nguyên mẫu không đọc
    # được thì không viết được vào báo cáo.
    nhan_nguyen_mau = []
    for j, c in enumerate(tam):
        gan_nhat = sorted(mon, key=lambda m: khoang_cach_binh_phuong(m["vector"], c))
        nhan_nguyen_mau.append(
            {
                "chi_so": j,
                "so_mon_trong_cum": sum(1 for g in gan_mon if g == j),
                "mon_dai_dien": [m["name"] for m in gan_nhat[:3]],
                "tam": [round(x, 6) for x in c],
            }
        )

    rnd = random.Random(seed + 1)

    # Xu hướng `chua_biet` của từng món. Beta(a, b) với a + b = BETA_CHUA_BIET
    # và a / (a + b) = TI_LE_CHUA_BIET.
    a = TI_LE_CHUA_BIET * BETA_CHUA_BIET
    b = BETA_CHUA_BIET - a
    q = [rnd.betavariate(a, b) for _ in mon]

    # Chia vòng tròn trên danh sách đã xáo: cân bằng tuyệt đối giữa các
    # nguyên mẫu, mà vẫn không gán theo thứ tự `user_id`.
    thu_tu = list(range(len(ho_so)))
    rnd.shuffle(thu_tu)
    z = {}
    for vi_tri, i in enumerate(thu_tu):
        z[ho_so[i]["user_id"]] = vi_tri % so_nguyen_mau

    # Ràng buộc sức khỏe. Gán TRƯỚC khi dựng `t_u` và không đọc `t_u`, nên
    # không có đường nào để khẩu vị ảnh hưởng tới ràng buộc hay ngược lại.
    benh_theo_nguoi = gan_dieu_kien(ho_so, rnd)
    ma_mon = [m["id"] for m in mon]
    f1_loai = f1_loai_theo_nguoi(cn, benh_theo_nguoi, ma_mon)

    for u, bo_loai in f1_loai.items():
        con = len(ma_mon) - len(bo_loai)
        if con < TOI_THIEU_LUOT_CON:
            raise SystemExit(
                f"{u} bị F1 loại {len(bo_loai)}/{len(ma_mon)} món, chỉ còn "
                f"{con} lượt dùng được (cần ≥ {TOI_THIEU_LUOT_CON}).\n"
                f"Điều kiện: {', '.join(benh_theo_nguoi[u])}\n"
                f"Giảm TOI_DA_RANG_BUOC_CUNG hoặc hạn mức trong "
                f"HAN_MUC_DIEU_KIEN."
            )

    nguoi: dict[str, dict[str, Any]] = {}
    for h in ho_so:
        u = h["user_id"]
        phu = rnd.choice([j for j in range(so_nguyen_mau) if j != z[u]])
        t = cong(tam[z[u]], nhan(tam[phu], lam_phu))
        t = cong(t, [rnd.gauss(0.0, sigma) for _ in ten_chieu])
        t = cong(t, day_theo_ho_so(h, ten_chieu, bien_do_ho_so))
        nguoi[u] = {
            "nguyen_mau": z[u],
            "nguyen_mau_phu": phu,
            "vector_khau_vi": [round(x, 6) for x in t],
            "benh_ly": benh_theo_nguoi[u],
            "severity": SEVERITY_PHIEU,
            # Món F1 không cho người này ăn. Ghi ra để `check_mo_phong.py`
            # đo được mà không cần CSDL, và để `import_mo_phong.py` đối
            # chiếu lại bằng phép lọc nó tự chạy — hai bên lệch nhau nghĩa
            # là dữ liệu và hệ thống đang hiểu ràng buộc khác nhau.
            "f1_loai": sorted(f1_loai[u]),
        }

    # Độ gần, rồi chuẩn hóa toàn cục. Chuẩn hóa toàn cục chứ không theo từng
    # người: chuẩn hóa theo người sẽ ép mọi người có cùng số lượt `thich`, và
    # mất luôn chuyện người kén ăn khác người dễ ăn.
    s: dict[tuple[str, int], float] = {}
    for h in ho_so:
        u = h["user_id"]
        t = nguoi[u]["vector_khau_vi"]
        for i, m in enumerate(mon):
            s[(u, i)] = cosine(t, m["vector"])
    gt = list(s.values())
    tb = sum(gt) / len(gt)
    sd = math.sqrt(sum((x - tb) ** 2 for x in gt) / (len(gt) - 1)) or 1.0

    # `chua_biet` rút trước và độc lập — nó không được xem `s`.
    chua_biet = {
        (h["user_id"], i): rnd.random() < q[i] for h in ho_so for i in range(len(mon))
    }

    # Ordered logit. Rút `ε` cho mọi cặp rồi lấy phân vị, nên tỉ lệ biên trùng
    # mục tiêu đúng bằng phép dựng, không phải sau vài lần thử seed.
    y: dict[tuple[str, int], float] = {}
    for khoa, gia_tri in s.items():
        if chua_biet[khoa]:
            continue
        # Logistic(0, 1) bằng phép biến đổi nghịch đảo của hàm phân phối.
        # `random()` trả [0, 1) nên 0 là giá trị có thể gặp; kẹp vào trong
        # khoảng mở để `log` không vỡ.
        p = min(max(rnd.random(), 1e-12), 1.0 - 1e-12)
        y[khoa] = beta * (gia_tri - tb) / sd + math.log(p / (1.0 - p))

    sap = sorted(y.values())
    c1 = sap[int(round(TI_LE_BIEN["khong_thich"] * len(sap)))]
    c2 = sap[
        int(round((TI_LE_BIEN["khong_thich"] + TI_LE_BIEN["binh_thuong"]) * len(sap)))
    ]

    hang: list[dict[str, str]] = []
    for h in ho_so:
        u = h["user_id"]
        # Mỗi người một THỨ TỰ KHÁC NHAU, và đây không phải chuyện trình bày.
        #
        # Với một thứ tự cố định cho mọi người, `nguoi.n_tin_hieu` — số tín
        # hiệu đã tích tại thời điểm vuốt, mà `ml/dataset.py` đưa vào làm đặc
        # trưng — trở thành **mã định danh của món**: lượt thứ i luôn là cùng
        # một món với mọi người. Đo trên lần sinh có thứ tự cố định: 42/43
        # mức `n_tin_hieu` chỉ ứng với 1–4 món trong 45, và nhãn trung bình
        # theo từng mức chạy từ 0,25 tới 0,73. Cả ba thuật toán đều bám vào
        # đặc trưng đó mạnh nhất, tức chúng đọc ra món qua cái đếm chứ không
        # qua vector đặc trưng — và lợi thế ấy **không chuyển sang lúc phục
        # vụ thật**, nơi `GET /onboarding/survey` trả bộ món đã lọc F1 theo
        # từng người nên vị trí không còn là món.
        #
        # Xáo thứ tự cũng là thực hành chuẩn của khảo sát (randomize order để
        # tránh hiệu ứng thứ tự), nên phiếu giấy cho người thật cũng nên in
        # mỗi người một thứ tự.
        thu_tu_nguoi = list(range(len(mon)))
        rnd.shuffle(thu_tu_nguoi)
        bi_f1 = set(f1_loai[u])
        for i in thu_tu_nguoi:
            m = mon[i]
            if chua_biet[(u, i)]:
                lc = "chua_biet"
            else:
                yv = y[(u, i)]
                lc = "khong_thich" if yv < c1 else "binh_thuong" if yv < c2 else "thich"
            # Ghi đè SAU khi đã rút theo khẩu vị, không thay cho nó: `t_u`
            # và `y` giữ nguyên là khẩu vị thật, chỉ thứ **được ghi vào
            # phiếu** mới mang ràng buộc. Đó đúng là tình huống phiếu giấy
            # tạo ra, và là tình huống F1-lúc-nhập phải gỡ.
            if m["id"] in bi_f1:
                lc = (
                    "khong_thich"
                    if rnd.random() < XAC_SUAT_LOAI_THANH_KHONG_THICH
                    else "chua_biet"
                )
            hang.append(
                {
                    "user_id": u,
                    "source_profile_row": h["source_profile_row"],
                    "ma_mon": m["id"],
                    "ten_mon": m["name"],
                    "nhom": m["category"],
                    "muc_cay": str(m["spice_level"]),
                    "lua_chon": lc,
                }
            )

    return {
        "hang": hang,
        "su_that": {
            "_doc": (
                "DỮ LIỆU MÔ PHỎNG. `vector_khau_vi` là vector ẩn đã dùng để "
                "sinh lượt vuốt trong hanh_vi.csv; Chương 3 so hồ sơ Rocchio "
                "khôi phục được với chính nó. Không phải dữ liệu người thật."
            ),
            "feature_version": json.loads(DECK.read_text(encoding="utf-8"))[
                "feature_version"
            ],
            "ten_chieu": ten_chieu,
            "tham_so": {
                "seed": seed,
                "so_nguyen_mau": so_nguyen_mau,
                "lam_nguyen_mau_phu": lam_phu,
                "sigma": sigma,
                "beta": beta,
                "bien_do_ho_so": bien_do_ho_so,
                "diem_cat": [round(c1, 6), round(c2, 6)],
                "ti_le_bien_muc_tieu": TI_LE_BIEN,
                "ti_le_chua_biet": TI_LE_CHUA_BIET,
            },
            "nguyen_mau": nhan_nguyen_mau,
            "nguoi": nguoi,
        },
    }


# ── xem trước ─────────────────────────────────────────────────────────────


def xem_truoc(ket_qua: dict[str, Any], mon: list[dict[str, Any]]) -> None:
    hang = ket_qua["hang"]
    st = ket_qua["su_that"]
    print(f"{len(st['nguoi'])} người × {len(mon)} món = {len(hang)} lượt")

    dem = {k: 0 for k in MUC}
    for h in hang:
        dem[h["lua_chon"]] += 1
    print("  phân bố:", "  ".join(f"{k}={dem[k]} ({dem[k]/len(hang):.1%})" for k in MUC))

    print(f"\n{len(st['nguyen_mau'])} khẩu vị nguyên mẫu:")
    for nm in st["nguyen_mau"]:
        trong = [u for u, v in st["nguoi"].items() if v["nguyen_mau"] == nm["chi_so"]]
        print(
            f"  #{nm['chi_so']} · {nm['so_mon_trong_cum']:>2} món · "
            f"{len(trong):>2} người · gần: {', '.join(nm['mon_dai_dien'])}"
        )

    co_rang_buoc = [u for u, v in st["nguoi"].items() if v["f1_loai"]]
    print(
        f"\nràng buộc sức khỏe · {len(co_rang_buoc)}/{len(st['nguoi'])} người "
        f"bị F1 loại ít nhất một món:"
    )
    dem_dk: dict[str, int] = {}
    for v in st["nguoi"].values():
        for b in v["benh_ly"]:
            dem_dk[b] = dem_dk.get(b, 0) + 1
    # Khoảng in ra là TỔNG số món bị loại của từng người mang điều kiện đó,
    # không phải số món do riêng điều kiện đó loại: một người có thể mang
    # hai điều kiện. Dị ứng đậu phộng tự nó loại 2 món; người mang nó mà
    # hiện "12" là người còn một ràng buộc nữa.
    for ten, sl in sorted(dem_dk.items(), key=lambda kv: -kv[1]):
        loai = [len(v["f1_loai"]) for v in st["nguoi"].values() if ten in v["benh_ly"]]
        print(
            f"  {ten:<24} {sl:>2} người · tổng món bị loại của họ: "
            f"{min(loai)}–{max(loai)}"
        )
    tong_loai = sum(len(v["f1_loai"]) for v in st["nguoi"].values())
    print(
        f"  → F1 loại {tong_loai}/{len(hang)} lượt "
        f"({tong_loai / len(hang):.1%}); những lượt này đã bị ghi đè thành "
        f"`khong_thich`\n    trong hanh_vi.csv và sẽ bị trình nhập gỡ ra."
    )

    # Số lượt `thich` theo người: mô phỏng phải cho người kén và người dễ.
    theo_nguoi: dict[str, int] = {}
    for h in hang:
        if h["lua_chon"] == "thich":
            theo_nguoi[h["user_id"]] = theo_nguoi.get(h["user_id"], 0) + 1
    v = sorted(theo_nguoi.values())
    print(
        f"\nsố lượt `thich` mỗi người: {v[0]} … {v[-1]} "
        f"(trung vị {v[len(v)//2]}) — tệp gốc: 10 … 22"
    )


def main() -> int:
    in_utf8()
    bo = argparse.ArgumentParser(description=__doc__)
    bo.add_argument("--ghi", action="store_true", help="ghi ra tệp")
    bo.add_argument("--db", default=None, help="tên CSDL khác, dùng khi chạy thử")
    bo.add_argument("--seed", type=int, default=20261112)
    bo.add_argument("--nguyen-mau", type=int, default=5, dest="nguyen_mau")
    bo.add_argument(
        "--nguyen-mau-phu", type=float, default=0.5, dest="lam_phu",
        help="trọng số λ của nguyên mẫu phụ (0 = chỉ một nguyên mẫu)",
    )
    bo.add_argument("--sigma", type=float, default=0.12)
    bo.add_argument("--beta", type=float, default=2.2)
    bo.add_argument(
        "--anh-huong-ho-so", type=float, default=0.10, dest="bien_do_ho_so"
    )
    t = bo.parse_args()

    if t.nguyen_mau < 2:
        raise SystemExit("--nguyen-mau phải từ 2 trở lên.")
    if t.sigma < 0 or t.beta < 0 or t.bien_do_ho_so < 0 or t.lam_phu < 0:
        raise SystemExit(
            "--sigma, --beta, --anh-huong-ho-so, --nguyen-mau-phu không được âm."
        )

    mon = nap_deck(DECK)
    ho_so = nap_ho_so(HO_SO)
    if t.nguyen_mau > len(mon):
        raise SystemExit(f"--nguyen-mau không vượt quá số món ({len(mon)}).")

    cn = ket_noi(t.db)
    try:
        ket_qua = sinh(
            cn=cn,
            mon=mon,
            ho_so=ho_so,
            so_nguyen_mau=t.nguyen_mau,
            lam_phu=t.lam_phu,
            sigma=t.sigma,
            beta=t.beta,
            bien_do_ho_so=t.bien_do_ho_so,
            seed=t.seed,
        )
    finally:
        cn.close()
    xem_truoc(ket_qua, mon)

    if not t.ghi:
        print("\nXem trước. Thêm --ghi để ghi ra:")
        print(f"  {RA_HANH_VI.relative_to(ROOT)}")
        print(f"  {RA_SU_THAT.relative_to(ROOT)}")
        return 0

    RA_THU_MUC.mkdir(parents=True, exist_ok=True)
    cot = ("user_id", "source_profile_row", "ma_mon", "ten_mon", "nhom", "muc_cay", "lua_chon")
    with RA_HANH_VI.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cot)
        w.writeheader()
        w.writerows(ket_qua["hang"])
    RA_SU_THAT.write_text(
        json.dumps(ket_qua["su_that"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nĐã ghi {RA_HANH_VI.relative_to(ROOT)} và {RA_SU_THAT.relative_to(ROOT)}.")
    print("Kiểm bằng: python tools/check_mo_phong.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
