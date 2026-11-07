#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm phần học máy — **không cần CSDL**.

Vì sao có tệp này. Các script trong `ml/` đã được chạy thử trên CSDL nháp,
nhưng phép chạy thử đó chỉ đi qua những ca mà dữ liệu thật tình cờ có. Những
chỗ dễ sai nhất lại là **ca biên**: cả tập chỉ có một mức năng lượng, người
dùng vuốt toàn `neutral`, một người không có món nào đáng gợi ý, tập huấn
luyện chỉ có một lớp. Dữ liệu thật hiện không có ca nào trong số đó, nên
chúng phải được dựng bằng tay.

Mọi phép kiểm ở đây chạy trên hàm thuần, nên tệp này chạy được ngay sau khi
clone, không cần MySQL và không cần tín hiệu người dùng.

Các chỉ số xếp hạng được đối chiếu với **giá trị tính bằng tay**, không phải
với kết quả của chính đoạn mã đang kiểm. Một bài kiểm so mã với chính nó thì
chỉ phát hiện được thay đổi, không phát hiện được sai.

Chạy:
    python tools/check_ml.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml import scoring  # noqa: E402
from ml.build_dataset import (  # noqa: E402
    Mau,
    chia_theo_nguoi,
    chong_nhan_doi,
    nhan_split,
    nhan_tu_sao,
)
from ml.f1_filter import LyDoLoai  # noqa: E402
from ml.dataset import NGUONG_THICH  # noqa: E402
from ml.han_muc import (  # noqa: E402
    MotHanMuc,
    TongChat,
    TrangThaiHanMuc,
    mon_khong_vua,
)
from ml.db import in_utf8  # noqa: E402
from ml.evaluate import (  # noqa: E402
    _dcg,
    chi_so_xep_hang,
    map_toan_danh_sach,
)
from ml.features import (  # noqa: E402
    FEATURE_VERSION,
    KhongGianDacTrung,
    Mon,
    cosine_similarity,
    lam_tron_kcal,
)
from ml.rocchio import alpha, dung_ho_so, giai_doan, ho_so_rong  # noqa: E402

from ml.popularity import SAO_DUONG, tu_tap_mau, wilson_chan_duoi  # noqa: E402

from datetime import date, datetime  # noqa: E402

import numpy as np  # noqa: E402

SAI_SO = 1e-9

_dat = 0
_loi: list[str] = []


def kiem(dieu_kien: bool, mo_ta: str) -> None:
    global _dat
    if dieu_kien:
        _dat += 1
    else:
        _loi.append(mo_ta)
        print(f"  ✗ {mo_ta}")


def gan(thuc_te: float, mong_doi: float, mo_ta: str) -> None:
    kiem(
        abs(thuc_te - mong_doi) < SAI_SO,
        f"{mo_ta}: được {thuc_te!r}, mong đợi {mong_doi!r}",
    )


def gan4(thuc_te: float, mong_doi: float, mo_ta: str) -> None:
    """So ở 4 chữ số thập phân — đúng độ chính xác của `DECIMAL(5,4)`.

    Dùng cho những giá trị mà số đối chiếu được tính tay và ghi tròn 4 chữ
    số. So khít hơn thế là so với cách tôi làm tròn khi viết tài liệu, không
    phải so với công thức.
    """
    kiem(
        abs(round(thuc_te, 4) - mong_doi) < 1e-9,
        f"{mo_ta}: được {round(thuc_te, 4)!r}, mong đợi {mong_doi!r}",
    )


def nem(ham, loai, mo_ta: str) -> None:
    try:
        ham()
    except loai:
        kiem(True, mo_ta)
        return
    except Exception as e:  # pragma: no cover
        kiem(False, f"{mo_ta}: ném {type(e).__name__} thay vì {loai.__name__}")
        return
    kiem(False, f"{mo_ta}: không ném gì")


def _mon(**ghi_de) -> Mon:
    """Món mẫu. Mặc định: 10 g đạm, 20 g bột đường, 5 g béo."""
    tham_so = dict(
        id="m1", name="Món thử", category="Cơm", dish_role="main",
        spice_level=0, kcal=200, protein=10.0, carb=20.0, fat=5.0,
        sugar=4.0, sodium=300.0, fiber=2.0,
    )
    tham_so.update(ghi_de)
    return Mon(**tham_so)  # type: ignore[arg-type]


# ── 1. Làm tròn năng lượng ────────────────────────────────────────────


def kiem_lam_tron() -> None:
    print("1. Làm tròn kcal — phải giống `num.round()` của Dart")
    # `round()` của Python cho 2 ở đây; Dart cho 3. Đây là cả lý do hàm tồn tại.
    kiem(lam_tron_kcal(2.5) == 3, "lam_tron_kcal(2.5) = 3 (Python round cho 2)")
    kiem(lam_tron_kcal(3.5) == 4, "lam_tron_kcal(3.5) = 4")
    kiem(lam_tron_kcal(2.4) == 2, "lam_tron_kcal(2.4) = 2")
    kiem(lam_tron_kcal(0.5) == 1, "lam_tron_kcal(0.5) = 1")
    kiem(lam_tron_kcal(-2.5) == -3, "lam_tron_kcal(-2.5) = -3 (ra xa số không)")
    kiem(round(2.5) == 2, "xác nhận round() của Python thật sự làm tròn về số chẵn")


# ── 2. Vector đặc trưng ───────────────────────────────────────────────


def kiem_vector() -> None:
    print("2. Vector đặc trưng món")

    m = _mon()
    # Tỷ lệ NĂNG LƯỢNG: 10·4 = 40, 20·4 = 80, 5·9 = 45, tổng 165.
    dam, bot, beo = m.macro_share
    gan(dam, 40 / 165, "tỷ lệ đạm là tỷ lệ năng lượng, không phải tỷ lệ gam")
    gan(bot, 80 / 165, "tỷ lệ bột đường")
    gan(beo, 45 / 165, "tỷ lệ béo")
    gan(dam + bot + beo, 1.0, "ba tỷ lệ macro cộng lại bằng 1")
    # Nếu ai dịch thành tỷ lệ gam thì tỷ lệ đạm sẽ là 10/35 — khác hẳn.
    kiem(abs(dam - 10 / 35) > 0.01, "tỷ lệ đạm KHÁC tỷ lệ gam 10/35")

    rong = _mon(protein=0, carb=0, fat=0)
    kiem(rong.macro_share == (0.0, 0.0, 0.0), "món không có macro cho (0, 0, 0)")

    # Nồng độ đường: đường trên mỗi gam món, KHÔNG chia cho bột đường.
    gan(
        _mon(sugar=20, serving_size_g=200).nong_do_duong,
        0.1,
        "nồng độ đường = đường / khối lượng suất",
    )
    gan(
        _mon(sugar=0, serving_size_g=200).nong_do_duong,
        0.0,
        "không có đường thì nồng độ = 0",
    )
    gan(
        _mon(sugar=5, serving_size_g=0).nong_do_duong,
        0.0,
        "khẩu phần 0 g thì trả 0, không chia cho 0",
    )
    # Đây là cả lý do đổi mẫu số ở v2: món ít bột đường KHÔNG còn bị đẩy lên
    # ngọt tối đa. Trứng luộc thật: 0,6 g bột đường, 2 g đường, suất 120 g.
    trung = _mon(sugar=2.0, carb=0.6, serving_size_g=120)
    chuoi = _mon(sugar=35.5, carb=35.5, serving_size_g=200)
    kiem(
        trung.nong_do_duong < chuoi.nong_do_duong / 5,
        f"trứng luộc ({trung.nong_do_duong:.4f}) ngọt kém hẳn chuối sứ "
        f"({chuoi.nong_do_duong:.4f})",
    )
    # Công thức cũ `sugar/carb` thì hai món này BẰNG NHAU ở mức 1,0.
    kiem(
        min(1, trung.sugar / trung.carb) == min(1, chuoi.sugar / chuoi.carb),
        "xác nhận công thức v1 cho hai món đó bằng điểm nhau",
    )

    # Không gian hai nhóm món, giá trị trải rộng.
    ds = [
        _mon(id="a", category="Cơm", kcal=100, sodium=0, fiber=0, sugar=0),
        _mon(
            id="b", category="Món nước", kcal=300, sodium=600, fiber=10,
            sugar=40, serving_size_g=200,
        ),
    ]
    kg = KhongGianDacTrung.tu_mon(ds)
    kiem(kg.length == 10, f"số chiều = 8 + 2 nhóm (được {kg.length})")
    kiem(len(kg.labels) == kg.length, "số nhãn khớp số chiều")
    kiem(
        kg.categories == ["Cơm", "Món nước"],
        f"nhóm món được sắp xếp (được {kg.categories})",
    )

    va = kg.encode(ds[0])
    vb = kg.encode(ds[1])
    gan(va[3], 0.0, "năng lượng nhỏ nhất → 0")
    gan(vb[3], 1.0, "năng lượng lớn nhất → 1")
    gan(va[4], 0.0, "nồng độ đường nhỏ nhất → 0")
    gan(vb[4], 1.0, "nồng độ đường lớn nhất → 1")
    gan(sum(va[8:]), 1.0, "đúng một chiều one-hot được bật")
    gan(va[8], 1.0, "món nhóm 'Cơm' bật chiều đầu")
    gan(vb[9], 1.0, "món nhóm 'Món nước' bật chiều sau")
    gan(va[7], 0.0, "mức cay 0 → 0")
    gan(kg.encode(_mon(spice_level=3))[7], 1.0, "mức cay 3 → 1")

    # Ca biên: cả tập chỉ có một mức năng lượng → mẫu số bằng 0.
    mot_muc = [_mon(id="x", kcal=200), _mon(id="y", kcal=200)]
    kg1 = KhongGianDacTrung.tu_mon(mot_muc)
    gan(kg1.encode(mot_muc[0])[3], 0.5, "khoảng năng lượng bằng 0 → 0,5")
    gan(kg1.encode(mot_muc[0])[4], 0.5, "khoảng nồng độ đường bằng 0 → 0,5")

    # Món thuộc nhóm không có trong không gian: cả khối one-hot bằng 0.
    la = kg.encode(_mon(id="z", category="Nhóm chưa có"))
    gan(sum(la[8:]), 0.0, "nhóm lạ thì không bật chiều nào")

    nem(
        lambda: KhongGianDacTrung.tu_mon([]),
        ValueError,
        "dựng không gian từ tập rỗng thì ném ValueError",
    )

    # Lưu rồi nạp lại phải ra đúng không gian cũ.
    lai = KhongGianDacTrung.tu_tham_so(kg.tham_so())
    kiem(
        lai.encode(ds[1]) == vb,
        "nạp lại từ scaler_params cho đúng vector cũ",
    )
    sai_ban = dict(kg.tham_so())
    sai_ban["feature_version"] = "v0-cu"
    nem(
        lambda: KhongGianDacTrung.tu_tham_so(sai_ban),
        ValueError,
        "scaler_params sai phiên bản đặc trưng thì ném ValueError",
    )
    kiem(FEATURE_VERSION == "v2", f"phiên bản đặc trưng hiện tại là v2")


def kiem_cosin() -> None:
    print("3. Độ tương đồng cosin")
    gan(cosine_similarity([1, 0], [1, 0]), 1.0, "hai vector trùng nhau → 1")
    gan(cosine_similarity([1, 0], [-1, 0]), -1.0, "hai vector đối nhau → −1")
    gan(cosine_similarity([1, 0], [0, 1]), 0.0, "hai vector vuông góc → 0")
    gan(cosine_similarity([0, 0], [1, 1]), 0.0, "vector độ dài 0 → 0, không chia 0")
    nem(
        lambda: cosine_similarity([1, 0], [1, 0, 0]),
        ValueError,
        "hai vector khác số chiều thì ném ValueError",
    )


# ── 4. Rocchio ────────────────────────────────────────────────────────


def kiem_rocchio() -> None:
    print("4. Hồ sơ sở thích Rocchio")

    ds = [
        _mon(id="a", category="Cơm", kcal=100, sodium=0, fiber=0),
        _mon(id="b", category="Món nước", kcal=300, sodium=600, fiber=10),
    ]
    kg = KhongGianDacTrung.tu_mon(ds)
    va, vb = kg.encode(ds[0]), kg.encode(ds[1])

    # Thích a, không thích b: p_u = (1·va − 1·vb) / 2
    h = dung_ho_so(kg, [(ds[0], "like"), (ds[1], "dislike")])
    mong = [(x - y) / 2 for x, y in zip(va, vb)]
    kiem(
        all(abs(a - b) < SAI_SO for a, b in zip(h.weights, mong)),
        "công thức Rocchio: (Σ w·v) / Σ|w|",
    )
    gan(h.sum_abs_weight, 2.0, "mẫu số = Σ|w| = 2")
    kiem(h.n_signals == 2, "đếm 2 tín hiệu")

    # `unknown` bị loại khỏi CẢ tử số lẫn mẫu số.
    h2 = dung_ho_so(
        kg, [(ds[0], "like"), (ds[1], "dislike"), (ds[0], "unknown")]
    )
    gan(h2.sum_abs_weight, 2.0, "`unknown` không làm phình mẫu số")
    kiem(h2.n_signals == 2, "`unknown` không được đếm là tín hiệu")
    kiem(
        all(abs(a - b) < SAI_SO for a, b in zip(h2.weights, h.weights)),
        "thêm một lượt `unknown` không đổi vector",
    )

    # Toàn `neutral`: mẫu số bằng 0 → giữ vector rỗng, KHÔNG chia cho 0.
    h3 = dung_ho_so(kg, [(ds[0], "neutral"), (ds[1], "neutral")])
    kiem(h3.is_empty, "phiên toàn `neutral` cho hồ sơ rỗng")
    gan(h3.sum_abs_weight, 0.0, "mẫu số bằng 0")
    kiem(h3.n_signals == 2, "`neutral` VẪN được đếm là tín hiệu")
    gan(h3.score(kg, ds[0]), 0.5, "hồ sơ rỗng cho mọi món điểm 0,5")

    gan(ho_so_rong(kg).score(kg, ds[0]), 0.5, "hồ sơ rỗng dựng sẵn cũng cho 0,5")
    kiem(len(ho_so_rong(kg).weights) == kg.length, "hồ sơ rỗng đủ số chiều")

    # Thích đúng một món thì cosin với chính nó bằng 1 → điểm 1,0.
    h4 = dung_ho_so(kg, [(ds[0], "like")])
    gan(h4.score(kg, ds[0]), 1.0, "thích đúng một món → món đó được điểm 1,0")

    nem(
        lambda: dung_ho_so(kg, [(ds[0], "ghe")]),
        ValueError,
        "hành động lạ thì ném ValueError",
    )

    kiem(h.to_json()["feature_version"] == FEATURE_VERSION,
         "to_json ghi kèm phiên bản đặc trưng")


def kiem_alpha() -> None:
    print("5. Hệ số trộn α và giai đoạn")
    gan(alpha(0), 0.0, "α(0) = 0")
    gan(alpha(29), 0.0, "α(29) = 0 — dưới n_min")
    gan(alpha(30), 0.0, "α(30) = 0 — đúng tại n_min")
    gan(alpha(65), 0.5, "α(65) = 0,5 — giữa khoảng")
    gan(alpha(100), 1.0, "α(100) = 1 — đúng tại n_max")
    gan(alpha(500), 1.0, "α(500) = 1")
    nem(lambda: alpha(50, 100, 100), ValueError, "n_max ≤ n_min thì ném ValueError")

    kiem(giai_doan(0) == "cold", "0 tín hiệu → cold")
    kiem(giai_doan(10) == "content", "10 tín hiệu → content")
    kiem(giai_doan(30) == "hybrid", "30 tín hiệu → hybrid")
    kiem(giai_doan(101) == "ml", "101 tín hiệu → ml")


# ── 6. Chấm điểm ──────────────────────────────────────────────────────


def kiem_cham_diem() -> None:
    print("6. Chấm điểm bốn giai đoạn")

    gan(scoring.diem_pho_bien(0.4), 0.4, "điểm phổ biến dùng thẳng")
    gan(scoring.diem_pho_bien(1.7), 1.0, "điểm phổ biến bị kẹp về 1")
    gan(scoring.diem_pho_bien(-0.2), 0.0, "điểm phổ biến bị kẹp về 0")

    # Khớp hoàn hảo: tỷ lệ món đúng bằng tỷ lệ mục tiêu.
    gan(
        scoring.do_khop_macro([0.15, 0.60, 0.25], [15, 60, 25]),
        1.0,
        "khớp macro hoàn hảo → 1,0",
    )
    # Lệch tối đa: món toàn đạm, mục tiêu toàn béo → tổng lệch = 2 → khớp 0.
    gan(
        scoring.do_khop_macro([1.0, 0.0, 0.0], [0, 0, 100]),
        0.0,
        "lệch macro tối đa → 0,0",
    )
    # Lệch 0,1 ở hai chiều → tổng lệch 0,2 → khớp 0,9.
    gan(
        scoring.do_khop_macro([0.25, 0.50, 0.25], [15, 60, 25]),
        0.9,
        "tổng lệch 0,2 → khớp 0,9",
    )
    gan(
        scoring.do_khop_macro([0.15, 0.60, 0.25], [0, 0, 0]),
        0.5,
        "mục tiêu macro rỗng → điểm trung tính",
    )
    nem(
        lambda: scoring.do_khop_macro([0.5, 0.5], [15, 60, 25]),
        ValueError,
        "vector món dưới 3 chiều thì ném ValueError",
    )

    # Giai đoạn 0 = nửa phổ biến + nửa khớp macro.
    gan(
        scoring.diem_luat([0.15, 0.60, 0.25], [15, 60, 25], 0.4),
        0.5 * 0.4 + 0.5 * 1.0,
        "điểm luật = 0,5·phổ biến + 0,5·khớp macro",
    )

    # Giai đoạn 1.
    gan(scoring.diem_noi_dung([0, 0, 0], [1, 1, 1]), 0.5,
        "hồ sơ rỗng → điểm trung tính 0,5")
    gan(scoring.diem_noi_dung([1, 0], [1, 0]), 1.0, "cosin 1 → điểm 1,0")
    gan(scoring.diem_noi_dung([1, 0], [-1, 0]), 0.0, "cosin −1 → điểm 0,0")
    gan(scoring.diem_noi_dung([1, 0], [0, 1]), 0.5, "cosin 0 → điểm 0,5")

    # Trộn.
    gan(scoring.tron(1.0, 0.0, 0), 0.0, "α = 0 → lấy trọn điểm nội dung")
    gan(scoring.tron(1.0, 0.0, 500), 1.0, "α = 1 → lấy trọn điểm ML")
    gan(scoring.tron(1.0, 0.0, 65), 0.5, "α = 0,5 → trộn đều")
    gan(scoring.tron(0.8, 0.4, 65), 0.6, "trộn 0,8 và 0,4 ở α = 0,5")


# ── 7. Nhãn và chống nhân đôi ─────────────────────────────────────────


def kiem_nhan() -> None:
    print("7. Nhãn, chống nhân đôi, chia fold")

    gan(nhan_tu_sao(5), 1.0, "5 sao → 1,000")
    gan(nhan_tu_sao(4), 0.75, "4 sao → 0,750")
    gan(nhan_tu_sao(3), 0.5, "3 sao → 0,500")
    gan(nhan_tu_sao(1), 0.0, "1 sao → 0,000")
    nem(lambda: nhan_tu_sao(0), ValueError, "0 sao thì ném ValueError")
    nem(lambda: nhan_tu_sao(6), ValueError, "6 sao thì ném ValueError")
    kiem(nhan_tu_sao(3) == NGUONG_THICH, "3 sao nằm đúng tại ngưỡng thích")

    cu = Mau("u1", "f1", "feedback", 1.0, 1.0, datetime(2026, 1, 1))
    moi = Mau("u1", "f1", "feedback", 0.25, 1.0, datetime(2026, 2, 1))
    khac_nguon = Mau("u1", "f1", "diary", 0.8, 0.9, datetime(2026, 1, 15))
    giu, bo = chong_nhan_doi([cu, moi, khac_nguon])
    kiem(len(giu) == 2, f"gộp còn 2 dòng (được {len(giu)})")
    kiem(bo == 1, "báo đã gộp 1 dòng")
    fb = [m for m in giu if m.source == "feedback"][0]
    gan(fb.label, 0.25, "giữ dòng MỚI NHẤT của cùng nguồn")
    kiem(
        any(m.source == "diary" for m in giu),
        "cùng cặp người–món nhưng khác nguồn thì giữ cả hai",
    )
    # Thứ tự đầu vào không được ảnh hưởng kết quả.
    giu2, _ = chong_nhan_doi([moi, cu, khac_nguon])
    gan(
        [m for m in giu2 if m.source == "feedback"][0].label,
        0.25,
        "đảo thứ tự đầu vào vẫn giữ dòng mới nhất",
    )

    nguoi = [f"u{i:02d}" for i in range(10)]
    gan_fold = chia_theo_nguoi(nguoi, 5, 42)
    dem = [sum(1 for u in nguoi if gan_fold[u] == f) for f in range(5)]
    kiem(dem == [2, 2, 2, 2, 2], f"10 người / 5 fold chia đều (được {dem})")
    kiem(
        chia_theo_nguoi(nguoi, 5, 42) == gan_fold,
        "chia lại cùng hạt giống cho đúng kết quả cũ",
    )
    kiem(
        chia_theo_nguoi(nguoi, 5, 43) != gan_fold,
        "đổi hạt giống thì đổi cách chia",
    )
    # 13 người / 5 fold: lệch nhiều nhất 1.
    nguoi13 = [f"v{i:02d}" for i in range(13)]
    g13 = chia_theo_nguoi(nguoi13, 5, 42)
    d13 = [sum(1 for u in nguoi13 if g13[u] == f) for f in range(5)]
    kiem(max(d13) - min(d13) <= 1, f"13 người / 5 fold lệch ≤ 1 (được {d13})")
    nem(lambda: chia_theo_nguoi(nguoi, 1, 42), ValueError, "1 fold thì ném ValueError")

    vai5 = [nhan_split(f, 5) for f in range(5)]
    kiem(
        vai5 == ["train", "train", "train", "val", "test"],
        f"5 fold → 3 train, 1 val, 1 test (được {vai5})",
    )
    vai2 = [nhan_split(f, 2) for f in range(2)]
    kiem(
        vai2 == ["train", "test"],
        f"2 fold → train/test, KHÔNG có val (được {vai2})",
    )


# ── 8. Chỉ số xếp hạng, đối chiếu với tính tay ────────────────────────


def kiem_chi_so() -> None:
    print("8. Chỉ số xếp hạng — đối chiếu giá trị tính tay")

    gan(_dcg([1.0]), 1.0, "DCG một phần tử = g / log2(2) = g")
    gan(_dcg([0.0, 1.0]), 1 / math.log2(3), "DCG vị trí thứ hai chia log2(3)")

    # Ba món của một người. Điểm giảm dần theo đúng thứ tự liệt kê.
    #   món  điểm  nhãn   nhị phân
    #    0   0,9   0,0       0
    #    1   0,8   1,0       1
    #    2   0,7   0,5       1
    diem = np.array([0.9, 0.8, 0.7])
    nhan = np.array([0.0, 1.0, 0.5])
    lop = np.array([0, 1, 1])
    nguoi = ["u1", "u1", "u1"]

    cs = chi_so_xep_hang(diem, nhan, lop, nguoi, 2)
    gan(cs.precision, 0.5, "precision@2 = 1 đúng / 2 vị trí")
    gan(cs.recall, 0.5, "recall@2 = 1 đúng / 2 món đáng gợi ý")
    dcg = 0.0 / math.log2(2) + 1.0 / math.log2(3)
    idcg = 1.0 / math.log2(2) + 0.5 / math.log2(3)
    gan(cs.ndcg, dcg / idcg, "nDCG@2 dùng lợi ích phân mức theo nhãn liên tục")
    kiem(cs.so_nguoi == 1, "đếm 1 người góp vào trung bình")

    cs3 = chi_so_xep_hang(diem, nhan, lop, nguoi, 3)
    gan(cs3.recall, 1.0, "recall@3 = 1,0 khi k phủ hết danh sách")
    gan(cs3.precision, 2 / 3, "precision@3 = 2/3")

    # k lớn hơn số món: mẫu số là số món, không phải k — nếu chia cho k thì
    # precision bị dìm xuống một cách vô cớ.
    cs9 = chi_so_xep_hang(diem, nhan, lop, nguoi, 9)
    gan(cs9.precision, 2 / 3, "k > số món thì precision chia cho số món")

    # Người không có món nào đáng gợi ý bị bỏ khỏi trung bình.
    cs0 = chi_so_xep_hang(
        np.array([0.9, 0.8]), np.array([0.0, 0.1]), np.array([0, 0]), ["u2", "u2"], 2
    )
    kiem(cs0.so_nguoi == 0, "người không có món đáng gợi ý bị bỏ khỏi trung bình")

    # Hai người, một người không có món đáng gợi ý → chỉ người kia được tính.
    cs2 = chi_so_xep_hang(
        np.array([0.9, 0.8, 0.9, 0.8]),
        np.array([0.0, 1.0, 0.0, 0.1]),
        np.array([0, 1, 0, 0]),
        ["u1", "u1", "u2", "u2"],
        1,
    )
    kiem(cs2.so_nguoi == 1, "chỉ người có món đáng gợi ý góp vào trung bình")
    gan(cs2.precision, 0.0, "precision@1 của người đó = 0 (món đúng xếp thứ hai)")

    # MAP trên toàn danh sách: món đúng ở vị trí 2 và 3.
    gt_map, so = map_toan_danh_sach(diem, lop, nguoi)
    gan(gt_map, (1 / 2 + 2 / 3) / 2, "MAP = trung bình của 1/2 và 2/3")
    kiem(so == 1, "MAP đếm 1 người")

    # Xếp hạng hoàn hảo → MAP = 1.
    gt_hoan_hao, _ = map_toan_danh_sach(
        np.array([0.9, 0.8, 0.7]), np.array([1, 1, 0]), nguoi
    )
    gan(gt_hoan_hao, 1.0, "xếp hạng hoàn hảo → MAP = 1,0")

    # Hòa điểm phải được phá theo chỉ số, không theo thứ tự duyệt — nếu không
    # thì phương án `popularity` (hòa rất nhiều) cho kết quả khác nhau mỗi lần.
    hoa = np.array([0.5, 0.5, 0.5])
    a, _ = map_toan_danh_sach(hoa, lop, nguoi)
    b, _ = map_toan_danh_sach(hoa, lop, nguoi)
    gan(a, b, "hòa điểm cho kết quả tái lập được")


# ── 9. Độ phổ biến ────────────────────────────────────────────────────


def kiem_pho_bien() -> None:
    print("9. Chặn dưới Wilson cho `popularity_score`")

    # Giá trị đối chiếu tính riêng từ công thức Wilson, không lấy từ mã.
    gan4(wilson_chan_duoi(2, 2), 0.3424, "2/2 → 0,3424 chứ không phải 1,00")
    gan4(wilson_chan_duoi(1, 1), 0.2065, "1/1 → 0,2065")
    gan4(wilson_chan_duoi(90, 100), 0.8256, "90/100 → 0,8256")
    gan4(wilson_chan_duoi(9, 10), 0.5958, "9/10 → 0,5958")

    # Điều quan trọng nhất: cỡ mẫu nhỏ KHÔNG được đứng trên cỡ mẫu lớn.
    kiem(
        wilson_chan_duoi(2, 2) < wilson_chan_duoi(90, 100),
        "món 2/2 bị xếp DƯỚI món 90/100 — đây là cả lý do dùng Wilson",
    )
    # Tỷ lệ thuần sẽ cho kết luận ngược lại.
    kiem(2 / 2 > 90 / 100, "xác nhận tỷ lệ thuần cho kết luận ngược")

    gan(wilson_chan_duoi(0, 10), 0.0, "0 người thích / 10 người thấy → 0")
    gan(wilson_chan_duoi(0, 0), 0.0, "chưa có tín hiệu nào → 0")

    # Cùng tỷ lệ, cỡ mẫu lớn hơn thì điểm cao hơn — chặn dưới siết lại dần.
    kiem(
        wilson_chan_duoi(5, 10)
        < wilson_chan_duoi(50, 100)
        < wilson_chan_duoi(500, 1000),
        "cùng tỷ lệ 50 %, cỡ mẫu lớn hơn thì điểm cao hơn",
    )
    kiem(
        wilson_chan_duoi(500, 1000) < 0.5,
        "chặn dưới luôn nhỏ hơn tỷ lệ quan sát",
    )

    # Mọi giá trị phải nằm trong [0, 1] — cột là DECIMAL(5,4) UNSIGNED.
    kiem(
        all(
            0.0 <= wilson_chan_duoi(a, b) <= 1.0
            for b in range(1, 40)
            for a in range(b + 1)
        ),
        "mọi tổ hợp tới 40 mẫu đều cho giá trị trong [0, 1]",
    )
    nem(
        lambda: wilson_chan_duoi(5, 2),
        ValueError,
        "số người thích lớn hơn cỡ mẫu thì ném ValueError",
    )
    kiem(SAO_DUONG == 4, "ngưỡng sao dương là 4, không phải 3 (3 sao = trung tính)")

    print("10. Độ phổ biến dựng lại từ fold huấn luyện — chống rò rỉ")

    #  i  người  món   nhãn   nguồn        fold
    #  0   u1     fA   0,9    swipe         0   ← huấn luyện
    #  1   u2     fA   0,9    swipe         0   ← huấn luyện
    #  2   u3     fA   0,9    swipe         1   ← KIỂM TRA, phải bị bỏ
    #  3   u1     fB   0,0    swipe         0   ← huấn luyện
    #  4   u1     fC   0,1    random_neg    0   ← phải bị bỏ khỏi phép đếm
    nguoi = ["u1", "u2", "u3", "u1", "u1"]
    mon = ["fA", "fA", "fA", "fB", "fC"]
    nhan = [0.9, 0.9, 0.9, 0.0, 0.1]
    nguon = ["swipe", "swipe", "swipe", "swipe", "random_neg"]
    train = [0, 1, 3, 4]

    pb = tu_tap_mau(nguoi, mon, nhan, nguon, train, nguong_duong=0.5)
    gan4(pb["fA"], 0.3424, "fA: 2/2 người trong fold huấn luyện → Wilson 2/2")
    gan(pb["fB"], 0.0, "fB: 0/1 người thích → 0")
    kiem("fC" not in pb, "`random_neg` không vào phép đếm — món chưa từng hiển thị")

    # Nếu tính trên CẢ fold kiểm tra thì fA thành 3/3 — cao hơn hẳn. Chính
    # khoảng chênh này là phần rò rỉ mà `ml/evaluate.py` phải loại bỏ.
    pb_ro_ri = tu_tap_mau(
        nguoi, mon, nhan, nguon, range(len(nguoi)), nguong_duong=0.5
    )
    gan4(pb_ro_ri["fA"], 0.4385, "nếu gộp cả fold kiểm tra thì fA lên 3/3")
    kiem(
        pb_ro_ri["fA"] > pb["fA"],
        "gộp fold kiểm tra làm độ phổ biến cao lên — đúng là rò rỉ",
    )

    kiem(
        tu_tap_mau(nguoi, mon, nhan, nguon, [], nguong_duong=0.5) == {},
        "fold huấn luyện rỗng → không món nào có điểm",
    )
    # Một người ăn cùng món nhiều lần chỉ được đếm MỘT lần.
    lap = tu_tap_mau(
        ["u1"] * 20, ["fA"] * 20, [0.9] * 20, ["diary"] * 20,
        range(20), nguong_duong=0.5,
    )
    gan4(lap["fA"], 0.2065, "20 lượt của cùng một người chỉ tính là 1 người")


# ── 11. Hạn mức theo ngày ─────────────────────────────────────────────


def kiem_han_muc() -> None:
    print("11. Hạn mức cứng theo ngày — trần, sàn và phần còn lại")

    # Tình huống lấy từ bản thiết kế giao diện, và mọi số là số thật trong
    # `nutrition_rec`. Giữ hai nơi dùng CÙNG con số là có chủ ý: nếu công
    # thức đổi, phép kiểm này sai ngay, chứ không để mockup và mã lệch nhau
    # âm thầm.
    #
    #   đã ăn    Bánh cuốn nóng            natri 807,9   purin  76,2
    #   kế hoạch Cơm gạo lứt + giá đậu nành natri  20,8   purin  96,0
    #            Canh chua chay             natri 458,7   purin  55,9
    #            Cá chiên xù                natri 464,0   purin   2,8
    #            Bắp cải luộc               natri  56,0   purin  44,0
    natri = MotHanMuc(
        benh="Tăng huyết áp",
        chat="sodium_mg",
        comparator="lte",
        nguong=2000.0,
        da_an=807.9,
        da_len_ke_hoach=20.8 + 458.7 + 464.0 + 56.0,
    )
    gan(natri.tong, 1807.4, "natri đã dùng = đã ăn + đã lên kế hoạch")
    gan(natri.con_lai, 192.6, "natri còn lại 192,6 mg")
    kiem(not natri.da_vuot, "1 807,4 / 2 000 thì chưa vượt")
    gan4(natri.ty_le, 0.9037, "tỷ lệ dùng 90,37%")

    purin = MotHanMuc(
        benh="Gút",
        chat="purine_mg",
        comparator="lte",
        nguong=400.0,
        da_an=76.2,
        da_len_ke_hoach=96.0 + 55.9 + 2.8 + 44.0,
    )
    gan(purin.tong, 274.9, "purin đã dùng 274,9 mg")
    gan(purin.con_lai, 125.1, "purin còn lại 125,1 mg")

    # `vua_khong` là phép mà giao diện gọi cho từng ứng viên.
    kiem(
        not natri.vua_khong(1022.3),
        "Phở sốt vang 1 022,3 mg natri KHÔNG vừa phần còn lại 192,6 mg",
    )
    kiem(natri.vua_khong(14.0), "Đậu phụ hấp 14 mg natri thì vừa")
    kiem(natri.vua_khong(192.6), "đúng bằng phần còn lại thì vẫn vừa (lte)")
    kiem(
        not natri.vua_khong(192.7),
        "hơn phần còn lại 0,1 mg là không vừa — biên phải chặt",
    )

    # Vượt trần: `con_lai` KHÔNG được kẹp về 0, vì giao diện cần nói vượt
    # bao nhiêu. Kẹp về 0 thì câu "vượt 222 mg" không viết được.
    da_vuot = MotHanMuc(
        benh="Tăng huyết áp",
        chat="sodium_mg",
        comparator="lte",
        nguong=2000.0,
        da_an=1500.0,
        da_len_ke_hoach=700.0,
    )
    kiem(da_vuot.da_vuot, "2 200 / 2 000 là đã vượt")
    gan(da_vuot.con_lai, -200.0, "vượt thì `con_lai` âm, không bị kẹp về 0")
    kiem(da_vuot.ty_le > 1.0, "tỷ lệ vượt 100% thì không bị kẹp")

    # Hai chiều của ngưỡng không đối xứng. Hỏi sai chiều phải nổ, chứ không
    # trả về một số vô nghĩa — đây là chỗ một ngưỡng sàn thêm vào sau này sẽ
    # âm thầm chặn món nếu cả hai dùng chung một phép trừ.
    san = MotHanMuc(
        benh="Thiếu máu",
        chat="iron_mg",
        comparator="gte",
        nguong=18.0,
        da_an=5.0,
        da_len_ke_hoach=4.0,
    )
    kiem(not san.la_tran, "`gte` không phải trần")
    gan(san.con_thieu, 9.0, "sàn sắt: còn thiếu 9 mg")
    kiem(not san.da_vuot, "không bao giờ `vượt` một cái sàn")
    kiem(san.vua_khong(999.0), "ăn thêm không bao giờ làm hỏng một cái sàn")
    nem(lambda: san.con_lai, ValueError, "hỏi `con_lai` của ngưỡng sàn phải nổ")
    nem(lambda: natri.con_thieu, ValueError, "hỏi `con_thieu` của trần phải nổ")

    # Hai bệnh hạn chế cùng một chất: phải lấy ngưỡng CHẶT NHẤT, không phải
    # ngưỡng đầu tiên gặp. Tăng huyết áp và Bệnh thận đều giới hạn natri.
    than = MotHanMuc(
        benh="Bệnh thận",
        chat="sodium_mg",
        comparator="lte",
        nguong=2000.0,
        da_an=807.9,
        da_len_ke_hoach=1000.0,
    )
    tt = TrangThaiHanMuc(
        user_id="u1",
        ngay=date(2026, 11, 7),
        han_muc=(natri, purin, than),
    )
    kiem(not tt.rong, "có ngưỡng thì không rỗng")
    kiem(len(tt.theo_chat("sodium_mg")) == 2, "natri có hai ngưỡng đang áp")
    chat_nhat = tt.han_muc_chat_nhat("sodium_mg")
    kiem(
        chat_nhat is not None and chat_nhat.benh == "Bệnh thận",
        "lấy ngưỡng natri còn ít dư địa nhất (Bệnh thận: 192,1 < 192,6)",
    )
    kiem(tt.han_muc_chat_nhat("calcium_mg") is None, "chất không bị hạn chế → None")
    kiem(TrangThaiHanMuc(user_id="u1", ngay=date(2026, 11, 7)).rong, "không ngưỡng → rỗng")

    # `mon_khong_vua`: đầu vào là các dòng đã qua F1, nên lý do duy nhất còn
    # lại để bỏ một món là hạn mức hôm nay — và món đó HÔM KHÁC VẪN HỢP.
    tt_toi = TrangThaiHanMuc(
        user_id="u1", ngay=date(2026, 11, 7), han_muc=(natri, purin)
    )
    ung_vien = [
        {"id": "f1", "name": "Phở sốt vang", "sodium_mg": 1022.3, "purine_mg": 12.4},
        {"id": "f2", "name": "Hủ tiếu sa tế", "sodium_mg": 990.0, "purine_mg": 15.0},
        {"id": "f3", "name": "Đậu phụ hấp", "sodium_mg": 14.0, "purine_mg": 136.0},
        {"id": "f4", "name": "Bắp cải luộc", "sodium_mg": 56.0, "purine_mg": 44.0},
    ]
    kq = mon_khong_vua(tt_toi, ung_vien)
    khong_vua = kq.khong_vua
    kiem(set(khong_vua) == {"f1", "f2", "f3"}, "ba món không vừa, Bắp cải luộc thì vừa")
    kiem(kq.vua("f4"), "Bắp cải luộc vừa cả hai hạn mức")
    gan(khong_vua["f1"][0].vuot_bao_nhieu, 1022.3 - 192.6, "Phở vượt 829,7 mg natri")
    kiem(
        khong_vua["f1"][0].chat == "sodium_mg"
        and khong_vua["f1"][0].benh == "Tăng huyết áp",
        "lý do nêu đúng chất và đúng bệnh",
    )

    # Mục đáng giá nhất của cả phần này. Đậu phụ hấp có natri 14 mg — THẤP
    # NHẤT trong mọi ứng viên — nhưng purin 136 mg thì vượt phần purin còn
    # lại 125,1 mg của người bị gút. Một món có thể rất tốt ở chất đang
    # thiếu và vẫn bị chặn bởi một chất khác, nên giao diện không được xếp
    # hạng theo một chất rồi kết luận.
    kiem(
        [l.chat for l in khong_vua["f3"]] == ["purine_mg"],
        "Đậu phụ hấp bị chặn bởi PURIN, không phải natri",
    )
    gan(khong_vua["f3"][0].vuot_bao_nhieu, 136.0 - 125.1, "vượt purin 10,9 mg")
    kiem(
        all(l.chat == "sodium_mg" for l in khong_vua["f2"]),
        "Hủ tiếu sa tế chỉ vướng natri, purin 15 mg thì dư sức",
    )

    # Món thiếu số đo chất bị hạn chế thì KHÔNG được coi là vừa một cách
    # lặng lẽ — nhưng cũng không được coi là vượt. Nó đơn giản là không xét
    # được, và F1 đã lọc trước nên dòng tới đây luôn có số.
    # Món thiếu số đo KHÔNG được kết luận vượt, nhưng cũng KHÔNG được coi là
    # vừa. `purine_mg` khuyết ở 248/318 món, nên gộp nhóm chưa biết vào nhóm
    # vừa sẽ làm trần purin gần như không bao giờ chạm tới.
    kq_thieu = mon_khong_vua(tt_toi, [{"id": "f9", "name": "Món lạ"}])
    kiem(kq_thieu.khong_vua == {}, "món thiếu số đo không bị kết luận vượt")
    kiem(
        kq_thieu.khong_xet_duoc == {"f9": ["sodium_mg", "purine_mg"]},
        "món thiếu số đo vào nhóm `khong_xet_duoc`, nêu đủ hai chất",
    )
    kiem(not kq_thieu.vua("f9"), "`vua()` phải là Sai với món chưa xét được")

    # Vướng một ngưỡng ĐÃ BIẾT thì kết luận được ngay, dù ngưỡng khác khuyết.
    kq_mot_nua = mon_khong_vua(
        tt_toi, [{"id": "f8", "name": "Nửa số", "sodium_mg": 9999.0}]
    )
    kiem(
        set(kq_mot_nua.khong_vua) == {"f8"} and kq_mot_nua.khong_xet_duoc == {},
        "đã chắc chắn vượt thì không xếp vào nhóm chưa biết",
    )

    kq_rong = mon_khong_vua(TrangThaiHanMuc("u1", date(2026, 11, 7)), ung_vien)
    kiem(
        kq_rong.khong_vua == {} and kq_rong.khong_xet_duoc == {},
        "không có ngưỡng nào thì không món nào bị bỏ",
    )

    # ── Cờ đủ dữ liệu ──
    kiem(natri.du_lieu_du, "mọi suất đều có số liệu natri → đủ dữ liệu")
    thieu_sl = MotHanMuc(
        benh="Gút",
        chat="purine_mg",
        comparator="lte",
        nguong=400.0,
        da_an=38.1,
        da_len_ke_hoach=102.5,
        thieu_da_an=1,
        thieu_ke_hoach=3,
    )
    kiem(not thieu_sl.du_lieu_du, "có suất khuyết số liệu → KHÔNG đủ dữ liệu")
    kiem(thieu_sl.so_mon_thieu_so == 4, "đếm đủ 4 suất thiếu số liệu")
    kiem(
        thieu_sl.con_lai > 0,
        "còn lại vẫn tính được, nhưng nó CAO hơn thực tế — cờ `du_lieu_du` "
        "là chỗ duy nhất nói ra điều đó",
    )

    tc = TongChat(tong={"purine_mg": 140.6}, thieu={"purine_mg": 4}, so_suat=6)
    kiem(not tc.du_lieu_du("purine_mg"), "TongChat báo thiếu đúng chất")
    kiem(tc.du_lieu_du("sodium_mg"), "chất không khuyết thì đủ")


# ── 12. Lý do bị F1 loại ──────────────────────────────────────────────


def kiem_ly_do_loai() -> None:
    print("12. Phân loại lý do bị F1 loại")

    def _ly_do(**ghi_de) -> LyDoLoai:
        goc = dict(
            food_id="f1",
            name="Món thử",
            dish_role="main",
            rule_type="nutrient_limit",
            benh="Tăng huyết áp",
            severity_min="mild",
        )
        goc.update(ghi_de)
        return LyDoLoai(**goc)

    nhan_cam = _ly_do(rule_type="exclude_tag", the="Giàu purin", benh="Gút")
    nhan_thieu = _ly_do(rule_type="require_tag", the="Món chay", benh="Ăn chay")
    kiem(nhan_cam.bac == "nhan", "nhãn bị cấm → bậc `nhan`")
    kiem(nhan_thieu.bac == "nhan", "thiếu nhãn bắt buộc → bậc `nhan`")

    vuot = _ly_do(nutrient="sodium_mg", comparator="lte", nguong=500.0, gia_tri=879.4)
    kiem(vuot.bac == "nguong_suat", "vượt ngưỡng theo suất → bậc `nguong_suat`")
    gan(vuot.vuot_bao_nhieu, 379.4, "vượt trần: số đo − ngưỡng")

    duoi_san = _ly_do(nutrient="fiber_g", comparator="gte", nguong=5.0, gia_tri=1.2)
    kiem(duoi_san.bac == "nguong_suat", "dưới sàn cũng là `nguong_suat`")
    gan(duoi_san.vuot_bao_nhieu, 3.8, "dưới sàn: ngưỡng − số đo, vẫn là số dương")

    # Phân biệt quan trọng nhất của cả phần này. `loc_f1` loại món thiếu số
    # liệu ở ngưỡng theo suất, và nói với người dùng "món này vượt ngưỡng"
    # khi thật ra là "chúng tôi không biết" là sai sự thật.
    khuyet = _ly_do(nutrient="purine_mg", comparator="lte", nguong=150.0, gia_tri=None)
    kiem(khuyet.thieu_so_lieu, "`nutrient_limit` không có số đo → thiếu số liệu")
    kiem(khuyet.bac == "thieu_so_lieu", "bậc riêng, không gộp vào `nguong_suat`")
    kiem(
        khuyet.vuot_bao_nhieu is None,
        "không có số đo thì không bịa ra một lượng vượt",
    )

    # Bẫy: luật nhãn cũng có `gia_tri` rỗng, nhưng nó KHÔNG phải thiếu số
    # liệu — nó không cần số liệu nào. Gộp hai thứ sẽ làm 181 món bị loại
    # vì nhãn hiện ra như thể hệ thống không biết gì về chúng.
    kiem(
        not nhan_cam.thieu_so_lieu,
        "luật nhãn có `gia_tri` rỗng nhưng KHÔNG phải thiếu số liệu",
    )
    kiem(
        nhan_cam.vuot_bao_nhieu is None,
        "luật nhãn không có lượng vượt — và không được nổ khi hỏi",
    )
    kiem(
        not nhan_thieu.thieu_so_lieu,
        "`require_tag` cũng vậy",
    )

    # Chiều của hai tầng trái nhau, và đó là chủ ý: xem docstring
    # `LyDoLoai.thieu_so_lieu`. Giữ phép kiểm này để ai đổi một bên phải
    # đọc lý do trước.
    kiem(
        khuyet.bac == "thieu_so_lieu",
        "theo SUẤT: thiếu số liệu thì LOẠI (ngược với hạn mức theo NGÀY, "
        "nơi thiếu số liệu thì cộng 0 kèm cờ)",
    )


def main() -> int:
    in_utf8()
    print("Kiểm phần học máy — hàm thuần, không cần CSDL")
    print("=" * 62)
    for ham in (
        kiem_lam_tron,
        kiem_vector,
        kiem_cosin,
        kiem_rocchio,
        kiem_alpha,
        kiem_cham_diem,
        kiem_nhan,
        kiem_chi_so,
        kiem_pho_bien,
        kiem_han_muc,
        kiem_ly_do_loai,
    ):
        ham()
    print("=" * 62)
    if _loi:
        print(f"{_dat} mục đạt, {len(_loi)} MỤC SAI:")
        for x in _loi:
            print("  -", x)
        return 1
    print(f"Tất cả {_dat} mục kiểm đều đạt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
