#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm phần học máy — **không cần CSDL**.

Vì sao có tệp này. Các script trong `ml/` đã được chạy thử trên CSDL nháp,
nhưng phép chạy thử đó chỉ đi qua những ca mà dữ liệu thật tình cờ có. Những
chỗ dễ sai nhất lại là **ca biên**: cả tập chỉ có một mức năng lượng, người
dùng vuốt toàn `neutral`, một người không có món nào đáng gợi ý, tập huấn
luyện chỉ có một lớp. Dữ liệu thật hiện không có ca nào trong số đó, nên
chúng phải được dựng bằng tay.

Mọi phép kiểm ở đây chạy trên hàm thuần, nên tệp này chạy được day sau khi
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
    Sample,
    assign_folds,
    deduplicate,
    split_label,
    label_from_rating,
)
from ml.f1_filter import (  # noqa: E402
    CITABLE_EVIDENCE,
    EVIDENCE_LEVELS,
    EVIDENCE_LABELS,
    ENFORCED_BY,
    SoftRule,
    ExclusionReason,
    unenforced_rules,
    soft_rules_by_scope,
)
from ml.scoring import penalty  # noqa: E402
from ml.serve import (  # noqa: E402
    PHRASE_BY_DIMENSION,
    CATEGORY_PREFIX,
    explanation_sentences,
    contributions,
    debug_explanation,
    dimensions_without_phrase,
)
from ml.dataset import LIKE_THRESHOLD  # noqa: E402
from ml.daily_limits import (  # noqa: E402
    DailyLimit,
    NutrientTotals,
    DailyLimitStatus,
    classify_foods,
)
from ml.db import use_utf8  # noqa: E402
from ml.evaluate import (  # noqa: E402
    _dcg,
    ranking_metrics,
    mean_average_precision,
)
from ml.features import (  # noqa: E402
    FEATURE_VERSION,
    FeatureSpace,
    Food,
    cosine_similarity,
    round_kcal,
)
from ml.rocchio import alpha, build_profile, stage, empty_profile  # noqa: E402

from ml.popularity import POSITIVE_STARS, from_samples, wilson_lower_bound  # noqa: E402

from datetime import date, datetime  # noqa: E402

import numpy as np  # noqa: E402

SAI_SO = 1e-9

_dat = 0
_loi: list[str] = []


def kiem(conditions: bool, mo_ta: str) -> None:
    global _dat
    if conditions:
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


def _mon(**ghi_de) -> Food:
    """Món mẫu. Mặc định: 10 g đạm, 20 g bột đường, 5 g béo."""
    params = dict(
        id="m1", name="Món thử", category="Cơm", dish_role="main",
        spice_level=0, kcal=200, protein=10.0, carb=20.0, fat=5.0,
        sugar=4.0, sodium=300.0, fiber=2.0,
    )
    params.update(ghi_de)
    return Food(**params)  # type: ignore[arg-type]


# ── 1. Làm tròn năng lượng ────────────────────────────────────────────


def kiem_lam_tron() -> None:
    print("1. Làm tròn kcal — phải giống `num.round()` của Dart")
    # `round()` của Python cho 2 ở đây; Dart cho 3. Đây là cả lý do hàm tồn tại.
    kiem(round_kcal(2.5) == 3, "round_kcal(2.5) = 3 (Python round cho 2)")
    kiem(round_kcal(3.5) == 4, "round_kcal(3.5) = 4")
    kiem(round_kcal(2.4) == 2, "round_kcal(2.4) = 2")
    kiem(round_kcal(0.5) == 1, "round_kcal(0.5) = 1")
    kiem(round_kcal(-2.5) == -3, "round_kcal(-2.5) = -3 (ra xa số không)")
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
        _mon(sugar=20, serving_size_g=200).sugar_density,
        0.1,
        "nồng độ đường = đường / khối lượng suất",
    )
    gan(
        _mon(sugar=0, serving_size_g=200).sugar_density,
        0.0,
        "không có đường thì nồng độ = 0",
    )
    gan(
        _mon(sugar=5, serving_size_g=0).sugar_density,
        0.0,
        "khẩu phần 0 g thì trả 0, không chia cho 0",
    )
    # Đây là cả lý do đổi mẫu số ở v2: món ít bột đường KHÔNG còn bị đẩy lên
    # ngọt tối đa. Trứng luộc thật: 0,6 g bột đường, 2 g đường, suất 120 g.
    trung = _mon(sugar=2.0, carb=0.6, serving_size_g=120)
    chuoi = _mon(sugar=35.5, carb=35.5, serving_size_g=200)
    kiem(
        trung.sugar_density < chuoi.sugar_density / 5,
        f"trứng luộc ({trung.sugar_density:.4f}) ngọt kém hẳn chuối sứ "
        f"({chuoi.sugar_density:.4f})",
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
    kg = FeatureSpace.from_foods(ds)
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
    kg1 = FeatureSpace.from_foods(mot_muc)
    gan(kg1.encode(mot_muc[0])[3], 0.5, "khoảng năng lượng bằng 0 → 0,5")
    gan(kg1.encode(mot_muc[0])[4], 0.5, "khoảng nồng độ đường bằng 0 → 0,5")

    # Món thuộc nhóm không có trong không gian: cả khối one-hot bằng 0.
    la = kg.encode(_mon(id="z", category="Nhóm chưa có"))
    gan(sum(la[8:]), 0.0, "nhóm lạ thì không bật chiều nào")

    nem(
        lambda: FeatureSpace.from_foods([]),
        ValueError,
        "dựng không gian từ tập rỗng thì ném ValueError",
    )

    # Lưu rồi nạp lại phải ra đúng không gian cũ.
    lai = FeatureSpace.from_params(kg.params())
    kiem(
        lai.encode(ds[1]) == vb,
        "nạp lại từ scaler_params cho đúng vector cũ",
    )
    sai_ban = dict(kg.params())
    sai_ban["feature_version"] = "v0-cu"
    nem(
        lambda: FeatureSpace.from_params(sai_ban),
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
    kg = FeatureSpace.from_foods(ds)
    va, vb = kg.encode(ds[0]), kg.encode(ds[1])

    # Thích a, không thích b: p_u = (1·va − 1·vb) / 2
    h = build_profile(kg, [(ds[0], "like"), (ds[1], "dislike")])
    mong = [(x - y) / 2 for x, y in zip(va, vb)]
    kiem(
        all(abs(a - b) < SAI_SO for a, b in zip(h.weights, mong)),
        "công thức Rocchio: (Σ w·v) / Σ|w|",
    )
    gan(h.sum_abs_weight, 2.0, "mẫu số = Σ|w| = 2")
    kiem(h.n_signals == 2, "đếm 2 tín hiệu")

    # `unknown` bị loại khỏi CẢ tử số lẫn mẫu số.
    h2 = build_profile(
        kg, [(ds[0], "like"), (ds[1], "dislike"), (ds[0], "unknown")]
    )
    gan(h2.sum_abs_weight, 2.0, "`unknown` không làm phình mẫu số")
    kiem(h2.n_signals == 2, "`unknown` không được đếm là tín hiệu")
    kiem(
        all(abs(a - b) < SAI_SO for a, b in zip(h2.weights, h.weights)),
        "thêm một lượt `unknown` không đổi vector",
    )

    # Toàn `neutral`: mẫu số bằng 0 → giữ vector rỗng, KHÔNG chia cho 0.
    h3 = build_profile(kg, [(ds[0], "neutral"), (ds[1], "neutral")])
    kiem(h3.is_empty, "phiên toàn `neutral` cho hồ sơ rỗng")
    gan(h3.sum_abs_weight, 0.0, "mẫu số bằng 0")
    kiem(h3.n_signals == 2, "`neutral` VẪN được đếm là tín hiệu")
    gan(h3.score(kg, ds[0]), 0.5, "hồ sơ rỗng cho mọi món điểm 0,5")

    gan(empty_profile(kg).score(kg, ds[0]), 0.5, "hồ sơ rỗng dựng sẵn cũng cho 0,5")
    kiem(len(empty_profile(kg).weights) == kg.length, "hồ sơ rỗng đủ số chiều")

    # Thích đúng một món thì cosin với chính nó bằng 1 → điểm 1,0.
    h4 = build_profile(kg, [(ds[0], "like")])
    gan(h4.score(kg, ds[0]), 1.0, "thích đúng một món → món đó được điểm 1,0")

    nem(
        lambda: build_profile(kg, [(ds[0], "ghe")]),
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

    kiem(stage(0) == "cold", "0 tín hiệu → cold")
    kiem(stage(10) == "content", "10 tín hiệu → content")
    kiem(stage(30) == "hybrid", "30 tín hiệu → hybrid")
    kiem(stage(101) == "ml", "101 tín hiệu → ml")


# ── 6. Chấm điểm ──────────────────────────────────────────────────────


def kiem_cham_diem() -> None:
    print("6. Chấm điểm bốn giai đoạn")

    gan(scoring.popularity_score(0.4), 0.4, "điểm phổ biến dùng thẳng")
    gan(scoring.popularity_score(1.7), 1.0, "điểm phổ biến bị kẹp về 1")
    gan(scoring.popularity_score(-0.2), 0.0, "điểm phổ biến bị kẹp về 0")

    # Khớp hoàn hảo: tỷ lệ món đúng bằng tỷ lệ mục tiêu.
    gan(
        scoring.macro_fit([0.15, 0.60, 0.25], [15, 60, 25]),
        1.0,
        "khớp macro hoàn hảo → 1,0",
    )
    # Lệch tối đa: món toàn đạm, mục tiêu toàn béo → tổng lệch = 2 → khớp 0.
    gan(
        scoring.macro_fit([1.0, 0.0, 0.0], [0, 0, 100]),
        0.0,
        "lệch macro tối đa → 0,0",
    )
    # Lệch 0,1 ở hai chiều → tổng lệch 0,2 → khớp 0,9.
    gan(
        scoring.macro_fit([0.25, 0.50, 0.25], [15, 60, 25]),
        0.9,
        "tổng lệch 0,2 → khớp 0,9",
    )
    gan(
        scoring.macro_fit([0.15, 0.60, 0.25], [0, 0, 0]),
        0.5,
        "mục tiêu macro rỗng → điểm trung tính",
    )
    nem(
        lambda: scoring.macro_fit([0.5, 0.5], [15, 60, 25]),
        ValueError,
        "vector món dưới 3 chiều thì ném ValueError",
    )

    # Giai đoạn 0 = nửa phổ biến + nửa khớp macro.
    gan(
        scoring.rule_score([0.15, 0.60, 0.25], [15, 60, 25], 0.4),
        0.5 * 0.4 + 0.5 * 1.0,
        "điểm luật = 0,5·phổ biến + 0,5·khớp macro",
    )

    # Giai đoạn 1.
    gan(scoring.content_score([0, 0, 0], [1, 1, 1]), 0.5,
        "hồ sơ rỗng → điểm trung tính 0,5")
    gan(scoring.content_score([1, 0], [1, 0]), 1.0, "cosin 1 → điểm 1,0")
    gan(scoring.content_score([1, 0], [-1, 0]), 0.0, "cosin −1 → điểm 0,0")
    gan(scoring.content_score([1, 0], [0, 1]), 0.5, "cosin 0 → điểm 0,5")

    # Trộn.
    gan(scoring.blend(1.0, 0.0, 0), 0.0, "α = 0 → lấy trọn điểm nội dung")
    gan(scoring.blend(1.0, 0.0, 500), 1.0, "α = 1 → lấy trọn điểm ML")
    gan(scoring.blend(1.0, 0.0, 65), 0.5, "α = 0,5 → trộn đều")
    gan(scoring.blend(0.8, 0.4, 65), 0.6, "trộn 0,8 và 0,4 ở α = 0,5")


# ── 7. Nhãn và chống nhân đôi ─────────────────────────────────────────


def kiem_nhan() -> None:
    print("7. Nhãn, chống nhân đôi, chia fold")

    gan(label_from_rating(5), 1.0, "5 sao → 1,000")
    gan(label_from_rating(4), 0.75, "4 sao → 0,750")
    gan(label_from_rating(3), 0.5, "3 sao → 0,500")
    gan(label_from_rating(1), 0.0, "1 sao → 0,000")
    nem(lambda: label_from_rating(0), ValueError, "0 sao thì ném ValueError")
    nem(lambda: label_from_rating(6), ValueError, "6 sao thì ném ValueError")
    kiem(label_from_rating(3) == LIKE_THRESHOLD, "3 sao nằm đúng tại ngưỡng thích")

    cu = Sample("u1", "f1", "feedback", 1.0, 1.0, datetime(2026, 1, 1))
    moi = Sample("u1", "f1", "feedback", 0.25, 1.0, datetime(2026, 2, 1))
    khac_nguon = Sample("u1", "f1", "diary", 0.8, 0.9, datetime(2026, 1, 15))
    giu, bo = deduplicate([cu, moi, khac_nguon])
    kiem(len(giu) == 2, f"gộp còn 2 dòng (được {len(giu)})")
    kiem(bo == 1, "báo đã gộp 1 dòng")
    fb = [m for m in giu if m.source == "feedback"][0]
    gan(fb.label, 0.25, "giữ dòng MỚI NHẤT của cùng nguồn")
    kiem(
        any(m.source == "diary" for m in giu),
        "cùng cặp người–món nhưng khác nguồn thì giữ cả hai",
    )
    # Thứ tự đầu vào không được ảnh hưởng kết quả.
    giu2, _ = deduplicate([moi, cu, khac_nguon])
    gan(
        [m for m in giu2 if m.source == "feedback"][0].label,
        0.25,
        "đảo thứ tự đầu vào vẫn giữ dòng mới nhất",
    )

    nguoi = [f"u{i:02d}" for i in range(10)]
    gan_fold = assign_folds(nguoi, 5, 42)
    dem = [sum(1 for u in nguoi if gan_fold[u] == f) for f in range(5)]
    kiem(dem == [2, 2, 2, 2, 2], f"10 người / 5 fold chia đều (được {dem})")
    kiem(
        assign_folds(nguoi, 5, 42) == gan_fold,
        "chia lại cùng hạt giống cho đúng kết quả cũ",
    )
    kiem(
        assign_folds(nguoi, 5, 43) != gan_fold,
        "đổi hạt giống thì đổi cách chia",
    )
    # 13 người / 5 fold: lệch nhiều nhất 1.
    nguoi13 = [f"v{i:02d}" for i in range(13)]
    g13 = assign_folds(nguoi13, 5, 42)
    d13 = [sum(1 for u in nguoi13 if g13[u] == f) for f in range(5)]
    kiem(max(d13) - min(d13) <= 1, f"13 người / 5 fold lệch ≤ 1 (được {d13})")
    nem(lambda: assign_folds(nguoi, 1, 42), ValueError, "1 fold thì ném ValueError")

    vai5 = [split_label(f, 5) for f in range(5)]
    kiem(
        vai5 == ["train", "train", "train", "val", "test"],
        f"5 fold → 3 train, 1 val, 1 test (được {vai5})",
    )
    vai2 = [split_label(f, 2) for f in range(2)]
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
    label = np.array([0.0, 1.0, 0.5])
    lop = np.array([0, 1, 1])
    nguoi = ["u1", "u1", "u1"]

    cs = ranking_metrics(diem, label, lop, nguoi, 2)
    gan(cs.precision, 0.5, "precision@2 = 1 đúng / 2 vị trí")
    gan(cs.recall, 0.5, "recall@2 = 1 đúng / 2 món đáng gợi ý")
    dcg = 0.0 / math.log2(2) + 1.0 / math.log2(3)
    idcg = 1.0 / math.log2(2) + 0.5 / math.log2(3)
    gan(cs.ndcg, dcg / idcg, "nDCG@2 dùng lợi ích phân mức theo nhãn liên tục")
    kiem(cs.n_users == 1, "đếm 1 người góp vào trung bình")

    cs3 = ranking_metrics(diem, label, lop, nguoi, 3)
    gan(cs3.recall, 1.0, "recall@3 = 1,0 khi k phủ hết danh sách")
    gan(cs3.precision, 2 / 3, "precision@3 = 2/3")

    # k lớn hơn số món: mẫu số là số món, không phải k — nếu chia cho k thì
    # precision bị dìm xuống một cách vô cớ.
    cs9 = ranking_metrics(diem, label, lop, nguoi, 9)
    gan(cs9.precision, 2 / 3, "k > số món thì precision chia cho số món")

    # Người không có món nào đáng gợi ý bị bỏ khỏi trung bình.
    cs0 = ranking_metrics(
        np.array([0.9, 0.8]), np.array([0.0, 0.1]), np.array([0, 0]), ["u2", "u2"], 2
    )
    kiem(cs0.n_users == 0, "người không có món đáng gợi ý bị bỏ khỏi trung bình")

    # Hai người, một người không có món đáng gợi ý → chỉ người kia được tính.
    cs2 = ranking_metrics(
        np.array([0.9, 0.8, 0.9, 0.8]),
        np.array([0.0, 1.0, 0.0, 0.1]),
        np.array([0, 1, 0, 0]),
        ["u1", "u1", "u2", "u2"],
        1,
    )
    kiem(cs2.n_users == 1, "chỉ người có món đáng gợi ý góp vào trung bình")
    gan(cs2.precision, 0.0, "precision@1 của người đó = 0 (món đúng xếp thứ hai)")

    # MAP trên toàn danh sách: món đúng ở vị trí 2 và 3.
    gt_map, count=mean_average_precision(diem, lop, nguoi)
    gan(gt_map, (1 / 2 + 2 / 3) / 2, "MAP = trung bình của 1/2 và 2/3")
    kiem(count== 1, "MAP đếm 1 người")

    # Xếp hạng hoàn hảo → MAP = 1.
    gt_hoan_hao, _ = mean_average_precision(
        np.array([0.9, 0.8, 0.7]), np.array([1, 1, 0]), nguoi
    )
    gan(gt_hoan_hao, 1.0, "xếp hạng hoàn hảo → MAP = 1,0")

    # Hòa điểm phải được phá theo chỉ số, không theo thứ tự duyệt — nếu không
    # thì phương án `popularity` (hòa rất nhiều) cho kết quả khác nhau mỗi lần.
    hoa = np.array([0.5, 0.5, 0.5])
    a, _ = mean_average_precision(hoa, lop, nguoi)
    b, _ = mean_average_precision(hoa, lop, nguoi)
    gan(a, b, "hòa điểm cho kết quả tái lập được")


# ── 9. Độ phổ biến ────────────────────────────────────────────────────


def kiem_pho_bien() -> None:
    print("9. Chặn dưới Wilson cho `popularity_score`")

    # Giá trị đối chiếu tính riêng từ công thức Wilson, không lấy từ mã.
    gan4(wilson_lower_bound(2, 2), 0.3424, "2/2 → 0,3424 chứ không phải 1,00")
    gan4(wilson_lower_bound(1, 1), 0.2065, "1/1 → 0,2065")
    gan4(wilson_lower_bound(90, 100), 0.8256, "90/100 → 0,8256")
    gan4(wilson_lower_bound(9, 10), 0.5958, "9/10 → 0,5958")

    # Điều quan trọng nhất: cỡ mẫu nhỏ KHÔNG được đứng trên cỡ mẫu lớn.
    kiem(
        wilson_lower_bound(2, 2) < wilson_lower_bound(90, 100),
        "món 2/2 bị xếp DƯỚI món 90/100 — đây là cả lý do dùng Wilson",
    )
    # Tỷ lệ thuần sẽ cho kết luận ngược lại.
    kiem(2 / 2 > 90 / 100, "xác nhận tỷ lệ thuần cho kết luận ngược")

    gan(wilson_lower_bound(0, 10), 0.0, "0 người thích / 10 người thấy → 0")
    gan(wilson_lower_bound(0, 0), 0.0, "chưa có tín hiệu nào → 0")

    # Cùng tỷ lệ, cỡ mẫu lớn hơn thì điểm cao hơn — chặn dưới siết lại dần.
    kiem(
        wilson_lower_bound(5, 10)
        < wilson_lower_bound(50, 100)
        < wilson_lower_bound(500, 1000),
        "cùng tỷ lệ 50 %, cỡ mẫu lớn hơn thì điểm cao hơn",
    )
    kiem(
        wilson_lower_bound(500, 1000) < 0.5,
        "chặn dưới luôn nhỏ hơn tỷ lệ quan sát",
    )

    # Mọi giá trị phải nằm trong [0, 1] — cột là DECIMAL(5,4) UNSIGNED.
    kiem(
        all(
            0.0 <= wilson_lower_bound(a, b) <= 1.0
            for b in range(1, 40)
            for a in range(b + 1)
        ),
        "mọi tổ hợp tới 40 mẫu đều cho giá trị trong [0, 1]",
    )
    nem(
        lambda: wilson_lower_bound(5, 2),
        ValueError,
        "số người thích lớn hơn cỡ mẫu thì ném ValueError",
    )
    kiem(POSITIVE_STARS == 4, "ngưỡng sao dương là 4, không phải 3 (3 sao = trung tính)")

    print("10. Độ phổ biến dựng lại từ fold huấn luyện — chống rò rỉ")

    #  i  người  món   nhãn   nguồn        fold
    #  0   u1     fA   0,9    swipe         0   ← huấn luyện
    #  1   u2     fA   0,9    swipe         0   ← huấn luyện
    #  2   u3     fA   0,9    swipe         1   ← KIỂM TRA, phải bị bỏ
    #  3   u1     fB   0,0    swipe         0   ← huấn luyện
    #  4   u1     fC   0,1    random_neg    0   ← phải bị bỏ khỏi phép đếm
    nguoi = ["u1", "u2", "u3", "u1", "u1"]
    mon = ["fA", "fA", "fA", "fB", "fC"]
    label = [0.9, 0.9, 0.9, 0.0, 0.1]
    nguon = ["swipe", "swipe", "swipe", "swipe", "random_neg"]
    train = [0, 1, 3, 4]

    pb = from_samples(nguoi, mon, label, nguon, train, positive_threshold=0.5)
    gan4(pb["fA"], 0.3424, "fA: 2/2 người trong fold huấn luyện → Wilson 2/2")
    gan(pb["fB"], 0.0, "fB: 0/1 người thích → 0")
    kiem("fC" not in pb, "`random_neg` không vào phép đếm — món chưa từng hiển thị")

    # Nếu tính trên CẢ fold kiểm tra thì fA thành 3/3 — cao hơn hẳn. Chính
    # khoảng chênh này là phần rò rỉ mà `ml/evaluate.py` phải loại bỏ.
    pb_ro_ri = from_samples(
        nguoi, mon, label, nguon, range(len(nguoi)), positive_threshold=0.5
    )
    gan4(pb_ro_ri["fA"], 0.4385, "nếu gộp cả fold kiểm tra thì fA lên 3/3")
    kiem(
        pb_ro_ri["fA"] > pb["fA"],
        "gộp fold kiểm tra làm độ phổ biến cao lên — đúng là rò rỉ",
    )

    kiem(
        from_samples(nguoi, mon, label, nguon, [], positive_threshold=0.5) == {},
        "fold huấn luyện rỗng → không món nào có điểm",
    )
    # Một người ăn cùng món nhiều lần chỉ được đếm MỘT lần.
    lap = from_samples(
        ["u1"] * 20, ["fA"] * 20, [0.9] * 20, ["diary"] * 20,
        range(20), positive_threshold=0.5,
    )
    gan4(lap["fA"], 0.2065, "20 lượt của cùng một người chỉ tính là 1 người")


# ── 11. Hạn mức theo ngày ─────────────────────────────────────────────


def kiem_han_muc() -> None:
    print("11. Hạn mức cứng theo ngày — trần, sàn và phần còn lại")

    # Tình huống lấy từ bản thiết kế giao diện, và mọi số là số thật trong
    # `nutrition_rec`. Giữ hai nơi dùng CÙNG con số là có chủ ý: nếu công
    # thức đổi, phép kiểm này sai day, chứ không để mockup và mã lệch nhau
    # âm thầm.
    #
    #   đã ăn    Bánh cuốn nóng            natri 807,9   purin  76,2
    #   kế hoạch Cơm gạo lứt + giá đậu nành natri  20,8   purin  96,0
    #            Canh chua chay             natri 458,7   purin  55,9
    #            Cá chiên xù                natri 464,0   purin   2,8
    #            Bắp cải luộc               natri  56,0   purin  44,0
    natri = DailyLimit(
        condition="Tăng huyết áp",
        nutrient="sodium_mg",
        comparator="lte",
        threshold=2000.0,
        eaten=807.9,
        planned=20.8 + 458.7 + 464.0 + 56.0,
    )
    gan(natri.used, 1807.4, "natri đã dùng = đã ăn + đã lên kế hoạch")
    gan(natri.remaining, 192.6, "natri còn lại 192,6 mg")
    kiem(not natri.is_exceeded, "1 807,4 / 2 000 thì chưa vượt")
    gan4(natri.ratio, 0.9037, "tỷ lệ dùng 90,37%")

    purin = DailyLimit(
        condition="Gút",
        nutrient="purine_mg",
        comparator="lte",
        threshold=400.0,
        eaten=76.2,
        planned=96.0 + 55.9 + 2.8 + 44.0,
    )
    gan(purin.used, 274.9, "purin đã dùng 274,9 mg")
    gan(purin.remaining, 125.1, "purin còn lại 125,1 mg")

    # `fits` là phép mà giao diện gọi cho từng ứng viên.
    kiem(
        not natri.fits(1022.3),
        "Phở sốt vang 1 022,3 mg natri KHÔNG vừa phần còn lại 192,6 mg",
    )
    kiem(natri.fits(14.0), "Đậu phụ hấp 14 mg natri thì vừa")
    kiem(natri.fits(192.6), "đúng bằng phần còn lại thì vẫn vừa (lte)")
    kiem(
        not natri.fits(192.7),
        "hơn phần còn lại 0,1 mg là không vừa — biên phải chặt",
    )

    # Vượt trần: `remaining` KHÔNG được kẹp về 0, vì giao diện cần nói vượt
    # bao nhiêu. Kẹp về 0 thì câu "vượt 222 mg" không viết được.
    is_exceeded = DailyLimit(
        condition="Tăng huyết áp",
        nutrient="sodium_mg",
        comparator="lte",
        threshold=2000.0,
        eaten=1500.0,
        planned=700.0,
    )
    kiem(is_exceeded.is_exceeded, "2 200 / 2 000 là đã vượt")
    gan(is_exceeded.remaining, -200.0, "vượt thì `remaining` âm, không bị kẹp về 0")
    kiem(is_exceeded.ratio > 1.0, "tỷ lệ vượt 100% thì không bị kẹp")

    # Hai chiều của ngưỡng không đối xứng. Hỏi sai chiều phải nổ, chứ không
    # trả về một số vô nghĩa — đây là chỗ một ngưỡng sàn thêm vào sau này sẽ
    # âm thầm chặn món nếu cả hai dùng chung một phép trừ.
    san = DailyLimit(
        condition="Thiếu máu",
        nutrient="iron_mg",
        comparator="gte",
        threshold=18.0,
        eaten=5.0,
        planned=4.0,
    )
    kiem(not san.is_ceiling, "`gte` không phải trần")
    gan(san.shortfall, 9.0, "sàn sắt: còn thiếu 9 mg")
    kiem(not san.is_exceeded, "không bao giờ `vượt` một cái sàn")
    kiem(san.fits(999.0), "ăn thêm không bao giờ làm hỏng một cái sàn")
    nem(lambda: san.remaining, ValueError, "hỏi `remaining` của ngưỡng sàn phải nổ")
    nem(lambda: natri.shortfall, ValueError, "hỏi `shortfall` của trần phải nổ")

    # Hai bệnh hạn chế cùng một chất: phải lấy ngưỡng CHẶT NHẤT, không phải
    # ngưỡng đầu tiên gặp. Tăng huyết áp và Bệnh thận đều giới hạn natri.
    than = DailyLimit(
        condition="Bệnh thận",
        nutrient="sodium_mg",
        comparator="lte",
        threshold=2000.0,
        eaten=807.9,
        planned=1000.0,
    )
    tt = DailyLimitStatus(
        user_id="u1",
        day=date(2026, 11, 7),
        limits=(natri, purin, than),
    )
    kiem(not tt.is_empty, "có ngưỡng thì không rỗng")
    kiem(len(tt.for_nutrient("sodium_mg")) == 2, "natri có hai ngưỡng đang áp")
    chat_nhat = tt.tightest_limit("sodium_mg")
    kiem(
        chat_nhat is not None and chat_nhat.condition == "Bệnh thận",
        "lấy ngưỡng natri còn ít dư địa nhất (Bệnh thận: 192,1 < 192,6)",
    )
    kiem(tt.tightest_limit("calcium_mg") is None, "chất không bị hạn chế → None")
    kiem(DailyLimitStatus(user_id="u1", day=date(2026, 11, 7)).is_empty, "không ngưỡng → rỗng")

    # `classify_foods`: đầu vào là các dòng đã qua F1, nên lý do duy nhất còn
    # lại để bỏ một món là hạn mức hôm nay — và món đó HÔM KHÁC VẪN HỢP.
    tt_toi = DailyLimitStatus(
        user_id="u1", day=date(2026, 11, 7), limits=(natri, purin)
    )
    candidates = [
        {"id": "f1", "name": "Phở sốt vang", "sodium_mg": 1022.3, "purine_mg": 12.4},
        {"id": "f2", "name": "Hủ tiếu sa tế", "sodium_mg": 990.0, "purine_mg": 15.0},
        {"id": "f3", "name": "Đậu phụ hấp", "sodium_mg": 14.0, "purine_mg": 136.0},
        {"id": "f4", "name": "Bắp cải luộc", "sodium_mg": 56.0, "purine_mg": 44.0},
    ]
    kq = classify_foods(tt_toi, candidates)
    does_not_fit = kq.does_not_fit
    kiem(set(does_not_fit) == {"f1", "f2", "f3"}, "ba món không vừa, Bắp cải luộc thì vừa")
    kiem(kq.fits("f4"), "Bắp cải luộc vừa cả hai hạn mức")
    gan(does_not_fit["f1"][0].excess, 1022.3 - 192.6, "Phở vượt 829,7 mg natri")
    kiem(
        does_not_fit["f1"][0].nutrient == "sodium_mg"
        and does_not_fit["f1"][0].condition == "Tăng huyết áp",
        "lý do nêu đúng chất và đúng bệnh",
    )

    # Mục đáng giá nhất của cả phần này. Đậu phụ hấp có natri 14 mg — THẤP
    # NHẤT trong mọi ứng viên — nhưng purin 136 mg thì vượt phần purin còn
    # lại 125,1 mg của người bị gút. Một món có thể rất tốt ở chất đang
    # thiếu và vẫn bị chặn bởi một chất khác, nên giao diện không được xếp
    # hạng theo một chất rồi kết luận.
    kiem(
        [l.nutrient for l in does_not_fit["f3"]] == ["purine_mg"],
        "Đậu phụ hấp bị chặn bởi PURIN, không phải natri",
    )
    gan(does_not_fit["f3"][0].excess, 136.0 - 125.1, "vượt purin 10,9 mg")
    kiem(
        all(l.nutrient == "sodium_mg" for l in does_not_fit["f2"]),
        "Hủ tiếu sa tế chỉ vướng natri, purin 15 mg thì dư sức",
    )

    # Món thiếu số đo chất bị hạn chế thì KHÔNG được coi là vừa một cách
    # lặng lẽ — nhưng cũng không được coi là vượt. Nó đơn giản là không xét
    # được, và F1 đã lọc trước nên dòng tới đây luôn có số.
    # Món thiếu số đo KHÔNG được kết luận vượt, nhưng cũng KHÔNG được coi là
    # vừa. `purine_mg` khuyết ở 248/318 món, nên gộp nhóm chưa biết vào nhóm
    # vừa sẽ làm trần purin gần như không bao giờ chạm tới.
    kq_thieu = classify_foods(tt_toi, [{"id": "f9", "name": "Món lạ"}])
    kiem(kq_thieu.does_not_fit == {}, "món thiếu số đo không bị kết luận vượt")
    kiem(
        kq_thieu.undecidable == {"f9": ["sodium_mg", "purine_mg"]},
        "món thiếu số đo vào nhóm `undecidable`, nêu đủ hai chất",
    )
    kiem(not kq_thieu.fits("f9"), "`fits()` phải là Sai với món chưa xét được")

    # Vướng một ngưỡng ĐÃ BIẾT thì kết luận được day, dù ngưỡng khác khuyết.
    kq_mot_nua = classify_foods(
        tt_toi, [{"id": "f8", "name": "Nửa số", "sodium_mg": 9999.0}]
    )
    kiem(
        set(kq_mot_nua.does_not_fit) == {"f8"} and kq_mot_nua.undecidable == {},
        "đã chắc chắn vượt thì không xếp vào nhóm chưa biết",
    )

    kq_rong = classify_foods(DailyLimitStatus("u1", date(2026, 11, 7)), candidates)
    kiem(
        kq_rong.does_not_fit == {} and kq_rong.undecidable == {},
        "không có ngưỡng nào thì không món nào bị bỏ",
    )

    # ── Cờ đủ dữ liệu ──
    kiem(natri.has_full_data, "mọi suất đều có số liệu natri → đủ dữ liệu")
    thieu_sl = DailyLimit(
        condition="Gút",
        nutrient="purine_mg",
        comparator="lte",
        threshold=400.0,
        eaten=38.1,
        planned=102.5,
        missing_eaten=1,
        missing_planned=3,
    )
    kiem(not thieu_sl.has_full_data, "có suất khuyết số liệu → KHÔNG đủ dữ liệu")
    kiem(thieu_sl.n_missing_servings == 4, "đếm đủ 4 suất thiếu số liệu")
    kiem(
        thieu_sl.remaining > 0,
        "còn lại vẫn tính được, nhưng nó CAO hơn thực tế — cờ `has_full_data` "
        "là chỗ duy nhất nói ra điều đó",
    )

    tc = NutrientTotals(totals={"purine_mg": 140.6}, missing={"purine_mg": 4}, n_servings=6)
    kiem(not tc.has_full_data("purine_mg"), "NutrientTotals báo thiếu đúng chất")
    kiem(tc.has_full_data("sodium_mg"), "chất không khuyết thì đủ")


# ── 12. Lý do bị F1 loại ──────────────────────────────────────────────


def kiem_ly_do_loai() -> None:
    print("12. Phân loại lý do bị F1 loại")

    def _reason(**ghi_de) -> ExclusionReason:
        goc = dict(
            food_id="f1",
            name="Món thử",
            dish_role="main",
            rule_type="nutrient_limit",
            condition="Tăng huyết áp",
            severity_min="mild",
        )
        goc.update(ghi_de)
        return ExclusionReason(**goc)

    nhan_cam = _reason(rule_type="exclude_tag", tag="Giàu purin", condition="Gút")
    nhan_thieu = _reason(rule_type="require_tag", tag="Món chay", condition="Ăn chay")
    kiem(nhan_cam.kind == "tag", "nhãn bị cấm → bậc `tag`")
    kiem(nhan_thieu.kind == "tag", "thiếu nhãn bắt buộc → bậc `tag`")

    vuot = _reason(nutrient="sodium_mg", comparator="lte", threshold=500.0, value=879.4)
    kiem(vuot.kind == "serving_threshold", "vượt ngưỡng theo suất → bậc `serving_threshold`")
    gan(vuot.excess, 379.4, "vượt trần: số đo − ngưỡng")

    duoi_san = _reason(nutrient="fiber_g", comparator="gte", threshold=5.0, value=1.2)
    kiem(duoi_san.kind == "serving_threshold", "dưới sàn cũng là `serving_threshold`")
    gan(duoi_san.excess, 3.8, "dưới sàn: ngưỡng − số đo, vẫn là số dương")

    # Phân biệt quan trọng nhất của cả phần này. `allowed_foods` loại món thiếu số
    # liệu ở ngưỡng theo suất, và nói với người dùng "món này vượt ngưỡng"
    # khi thật ra là "chúng tôi không biết" là sai sự thật.
    khuyet = _reason(nutrient="purine_mg", comparator="lte", threshold=150.0, value=None)
    kiem(khuyet.missing_data, "`nutrient_limit` không có số đo → thiếu số liệu")
    kiem(khuyet.kind == "missing_data", "bậc riêng, không gộp vào `serving_threshold`")
    kiem(
        khuyet.excess is None,
        "không có số đo thì không bịa ra một lượng vượt",
    )

    # Bẫy: luật nhãn cũng có `value` rỗng, nhưng nó KHÔNG phải thiếu số
    # liệu — nó không cần số liệu nào. Gộp hai thứ sẽ làm 181 món bị loại
    # vì nhãn hiện ra như thể hệ thống không biết gì về chúng.
    kiem(
        not nhan_cam.missing_data,
        "luật nhãn có `value` rỗng nhưng KHÔNG phải thiếu số liệu",
    )
    kiem(
        nhan_cam.excess is None,
        "luật nhãn không có lượng vượt — và không được nổ khi hỏi",
    )
    kiem(
        not nhan_thieu.missing_data,
        "`require_tag` cũng vậy",
    )

    # Chiều của hai tầng trái nhau, và đó là chủ ý: xem docstring
    # `ExclusionReason.missing_data`. Giữ phép kiểm này để ai đổi một bên phải
    # đọc lý do trước.
    kiem(
        khuyet.kind == "missing_data",
        "theo SUẤT: thiếu số liệu thì LOẠI (ngược với hạn mức theo NGÀY, "
        "nơi thiếu số liệu thì cộng 0 kèm cờ)",
    )


# ── 13. Hình phạt mềm ─────────────────────────────────────────────────


def kiem_hinh_phat_mem() -> None:
    print("13. Ràng buộc mềm — hệ số nhân, và phép cộng hình phạt")

    # Hai dải LỒNG NHAU của cùng một bệnh, cùng một chất. Đây là ca mà một
    # phép nhân thẳng sẽ đếm đôi.
    tha_nhe = SoftRule(
        condition="Tăng huyết áp",
        severity_min="mild",
        nutrient="sodium_mg",
        comparator="lte",
        threshold=700.0,
        penalty=0.600,
        scope="per_serving",
    )
    tha_nang = SoftRule(
        condition="Tăng huyết áp",
        severity_min="severe",
        nutrient="sodium_mg",
        comparator="lte",
        threshold=500.0,
        penalty=0.400,
        scope="per_serving",
    )
    gut = SoftRule(
        condition="Gút",
        severity_min="mild",
        nutrient="purine_mg",
        comparator="lte",
        threshold=150.0,
        penalty=0.500,
        scope="per_serving",
    )

    # `penalty` là HỆ SỐ NHÂN. Chứng cứ nằm trong chính dữ liệu: ghi chú của
    # dòng mức nặng viết "phạt nặng hơn cho mức nặng" và giá trị là 0,400 so
    # với 0,600 của mức nhẹ. Đọc theo phép trừ thì 0,400 trừ ÍT hơn, tức
    # mức nặng bị phạt nhẹ hơn — ngược hẳn ghi chú.
    kiem(tha_nang.penalty < tha_nhe.penalty, "mức nặng có hệ số NHỎ hơn")

    mot_nhom = penalty({"sodium_mg": 800.0, "purine_mg": 10.0}, [tha_nhe, tha_nang, gut])
    gan(
        mot_nhom.factor,
        0.400,
        "800 mg natri vượt CẢ HAI dải của cùng bệnh → lấy nặng nhất 0,400, "
        "không nhân thành 0,240",
    )
    kiem(len(mot_nhom.violations) == 1, "một mối lo thì nêu một vi phạm, không hai")
    kiem(
        mot_nhom.violations[0].threshold == 500.0,
        "vi phạm được nêu là dải chặt hơn (500 mg), không phải dải 700 mg",
    )
    gan(mot_nhom.violations[0].excess, 300.0, "lệch so với dải được nêu: 800 − 500")

    hai_nhom = penalty(
        {"sodium_mg": 800.0, "purine_mg": 200.0}, [tha_nhe, tha_nang, gut]
    )
    gan(hai_nhom.factor, 0.200, "hai bệnh khác nhau thì NHÂN qua nhóm: 0,4 × 0,5")
    kiem(len(hai_nhom.violations) == 2, "hai mối lo thì nêu hai vi phạm")
    kiem(
        [v.condition for v in hai_nhom.violations] == ["Tăng huyết áp", "Gút"],
        "vi phạm xếp theo mức phạt nặng trước",
    )

    sach = penalty({"sodium_mg": 100.0, "purine_mg": 10.0}, [tha_nhe, tha_nang, gut])
    gan(sach.factor, 1.0, "không vượt gì thì hệ số 1,0")
    kiem(not sach.is_penalised, "hệ số 1,0 thì không bị trừ điểm")
    kiem(sach.violations == (), "không vi phạm nào")
    gan(sach.apply(0.78), 0.78, "hệ số 1,0 không đổi điểm")
    gan(mot_nhom.apply(0.78), 0.312, "điểm 0,78 × 0,400 = 0,312")

    # Biên: đúng bằng ngưỡng thì KHÔNG vượt.
    bien = penalty({"sodium_mg": 700.0, "purine_mg": 150.0}, [tha_nhe, gut])
    gan(bien.factor, 1.0, "đúng bằng ngưỡng `lte` thì không vượt")
    hon = penalty({"sodium_mg": 700.01, "purine_mg": 10.0}, [tha_nhe, gut])
    kiem(hon.is_penalised, "hơn ngưỡng 0,01 mg là vượt — biên phải chặt")

    # Thiếu số liệu: KHÔNG phạt, nhưng phải ghi lại. Ràng buộc mềm là quyết
    # định về xếp hạng, nên hạ điểm một món vì danh mục thiếu số liệu là
    # phạt sai đối tượng.
    khuyet = penalty({"sodium_mg": None, "purine_mg": 10.0}, [tha_nhe, tha_nang, gut])
    gan(khuyet.factor, 1.0, "thiếu số liệu thì không phạt")
    kiem(
        khuyet.missing_data == ("sodium_mg",),
        "nhưng ghi lại chất không xét được, và chỉ ghi một lần cho hai luật",
    )
    kiem(khuyet.violations == (), "không bịa ra vi phạm từ số liệu không có")

    # Ngưỡng `gte` là sàn: thiếu thì phạt, chứ không phải vượt thì phạt.
    san = SoftRule(
        condition="Thiếu máu",
        severity_min="mild",
        nutrient="iron_mg",
        comparator="gte",
        threshold=4.0,
        penalty=0.800,
        scope="per_serving",
    )
    duoi_san = penalty({"iron_mg": 1.5}, [san])
    gan(duoi_san.factor, 0.800, "dưới sàn sắt thì bị phạt")
    gan(duoi_san.violations[0].excess, 2.5, "lệch của sàn: ngưỡng − số đo")
    gan(penalty({"iron_mg": 9.0}, [san]).factor, 1.0, "trên sàn thì không phạt")
    kiem(san.direction_word == "thiếu", "chữ cho sàn là `thiếu`")
    kiem(tha_nhe.direction_word == "vượt", "chữ cho trần là `vượt`")

    # Phạm vi sai phải NỔ, không được âm thầm tính ra một con số trông hợp lý.
    # Áp luật `per_meal` cho từng món sai cả hai chiều: bỏ sót khi tổng bữa
    # vượt dù không món nào vượt, và phạt oan món lớn trong bữa còn dư địa.
    bua = SoftRule(
        condition="Đái tháo đường",
        severity_min="mild",
        nutrient="carbs_g",
        comparator="lte",
        threshold=60.0,
        penalty=0.700,
        scope="per_meal",
    )
    day = SoftRule(
        condition="Đái tháo đường",
        severity_min="mild",
        nutrient="sugar_g",
        comparator="lte",
        threshold=25.0,
        penalty=0.600,
        scope="per_day",
    )
    nem(lambda: penalty({"carbs_g": 80.0}, [bua]), ValueError, "luật per_meal phải nổ")
    nem(lambda: penalty({"sugar_g": 30.0}, [day]), ValueError, "luật per_day phải nổ")

    # Phân luồng theo phạm vi, và luật chưa có tầng thi hành.
    theo = soft_rules_by_scope([tha_nhe, gut, bua, day])
    kiem(len(theo["per_serving"]) == 2, "hai luật theo suất")
    kiem(len(theo["per_meal"]) == 1 and len(theo["per_day"]) == 1, "mỗi phạm vi một luật")
    chua = unenforced_rules([tha_nhe, gut, bua, day])
    kiem(
        [l.scope for l in chua] == ["per_meal"],
        "chỉ `per_meal` là chưa có tầng thi hành — Bước 4 chưa nhận nó",
    )
    kiem(
        ENFORCED_BY["per_serving"] is not None
        and ENFORCED_BY["per_day"] is not None,
        "hai phạm vi còn lại đã có chủ",
    )


# ── 14. Giải thích bằng câu ───────────────────────────────────────────


def kiem_cau_giai_thich() -> None:
    print("14. Giải thích gợi ý — câu cho người dùng, không phải số thô")

    # Không gian hai nhóm, để kiểm cả chiều cố định lẫn chiều one-hot nhóm.
    mon = [
        _mon(id="a", name="Canh A", category="Món canh", protein=20, carb=5, fat=2),
        _mon(id="b", name="Cơm B", category="Cơm", protein=5, carb=60, fat=3),
    ]
    kg = FeatureSpace.from_foods(mon)

    # Mọi chiều phải có câu. Đây là phép kiểm giữ cho một chiều mới thêm vào
    # không âm thầm hiện nhãn kỹ thuật cho người dùng.
    kiem(
        dimensions_without_phrase(kg) == [],
        f"mọi chiều đều có mệnh đề, thiếu: {dimensions_without_phrase(kg)}",
    )

    # Hồ sơ rỗng: không có cơ sở nào để nói người này thích gì.
    rong = empty_profile(kg)
    kiem(contributions(kg, rong, mon[0]) == [], "hồ sơ rỗng → không đóng góp nào")
    kiem(explanation_sentences(kg, rong, mon[0]) == [], "và không câu nào")
    kiem(
        debug_explanation(kg, rong, mon[0]) == "no preference profile yet",
        "dạng gỡ lỗi nói rõ là chưa có hồ sơ",
    )

    ho_so = build_profile(kg, [(mon[0], "like"), (mon[1], "dislike")])
    gop = contributions(kg, ho_so, mon[0])
    kiem(len(gop) > 0, "món được thích có đóng góp dương")

    # Chiều one-hot nhóm dựng câu từ tên nhóm, không cần bảng tra.
    nhom = [d for d in gop if d.dimension.startswith(CATEGORY_PREFIX)]
    kiem(len(nhom) == 1, "đúng một chiều nhóm đóng góp (one-hot)")
    kiem(
        nhom[0].sentence == "Bạn thích nhóm Món canh",
        f"câu cho chiều nhóm: được {nhom[0].sentence!r}",
    )

    # Chiều cố định tra bảng.
    dam = [d for d in gop if d.dimension == "Tỷ lệ đạm"]
    if dam:
        kiem(
            dam[0].sentence == "Bạn thường chọn món nhiều đạm",
            f"câu cho chiều đạm: được {dam[0].sentence!r}",
        )

    # Thứ tự giảm dần, và tỷ lệ chuẩn hóa theo đỉnh của CHÍNH món đó.
    kiem(
        all(a.value >= b.value for a, b in zip(gop, gop[1:])),
        "đóng góp xếp giảm dần",
    )
    gan(gop[0].share, 1.0, "đóng góp đầu có tỷ lệ 1,0")
    kiem(
        all(0.0 < d.share <= 1.0 for d in gop),
        "mọi tỷ lệ nằm trong (0, 1]",
    )

    # Mọi chiều NÊU RA phải dương. Đây là điều khiến câu luôn theo chiều
    # "nhiều X": vì mọi chiều vector nằm trong [0, 1] nên dấu của
    # `p_u[i]·v[i]` là dấu của `p_u[i]`, và đóng góp dương nghĩa là người
    # này nghiêng về giá trị CAO ở chiều đó.
    v = kg.encode(mon[0])
    kiem(all(0.0 <= x <= 1.0 for x in v), "mọi chiều vector trong [0, 1]")
    kiem(all(d.value > 0 for d in gop), "mọi đóng góp nêu ra đều dương")
    for d in gop:
        i = kg.labels.index(d.dimension)
        kiem(
            ho_so.weights[i] > 0,
            f"{d.dimension}: đóng góp dương ⟹ trọng số hồ sơ dương, nên câu "
            f"phải theo chiều `nhiều`, không bao giờ `ít`",
        )

    # `so` giới hạn số chiều.
    kiem(len(contributions(kg, ho_so, mon[0], count=1)) == 1, "`count=1` trả đúng một chiều")
    kiem(len(contributions(kg, ho_so, mon[0], count=99)) <= kg.length, "`so` lớn không vượt số chiều")

    # Dạng gỡ lỗi và dạng giao diện phải xếp hạng GIỐNG nhau — chúng dùng
    # chung `contributions`, và phép kiểm này giữ cho ai đó không cài lại.
    chuoi = debug_explanation(kg, ho_so, mon[0])
    kiem(
        all(d.dimension in chuoi for d in gop),
        "dạng gỡ lỗi nêu đúng các chiều mà `contributions` chọn",
    )
    kiem(
        chuoi.index(gop[0].dimension) < chuoi.index(gop[-1].dimension) or len(gop) == 1,
        "và theo cùng thứ tự",
    )
    sentence = explanation_sentences(kg, ho_so, mon[0])
    kiem(
        sentence == [d.sentence for d in gop if d.sentence is not None],
        "dạng giao diện chỉ bỏ chiều chưa có câu, không đổi thứ tự",
    )
    kiem(
        all("+" not in c and "0." not in c for c in sentence),
        "không câu nào lọt số thô ra giao diện",
    )

    # Chiều chưa có mệnh đề: bỏ dòng, KHÔNG hiện nhãn kỹ thuật.
    luu = PHRASE_BY_DIMENSION.pop("Tỷ lệ đạm")
    try:
        kiem(
            dimensions_without_phrase(kg) == ["Tỷ lệ đạm"],
            "`dimensions_without_phrase` báo đúng chiều bị quên",
        )
        gop2 = contributions(kg, ho_so, mon[0])
        missing = [d for d in gop2 if d.dimension == "Tỷ lệ đạm"]
        if missing:
            kiem(missing[0].sentence is None, "chiều bị quên có `sentence` rỗng")
            kiem(
                "Tỷ lệ đạm" not in explanation_sentences(kg, ho_so, mon[0]),
                "và không lọt vào danh sách câu của giao diện",
            )
    finally:
        PHRASE_BY_DIMENSION["Tỷ lệ đạm"] = luu
    kiem(dimensions_without_phrase(kg) == [], "đã phục hồi bảng mệnh đề")


# ── 15. Mức tin cậy của ngưỡng ────────────────────────────────────────


def kiem_muc_tin_cay() -> None:
    print("15. Mức tin cậy của ngưỡng — bốn mức, và mức nào dẫn được nguồn")

    kiem(
        set(EVIDENCE_LEVELS) == set(EVIDENCE_LABELS),
        "mọi mức đều có nhãn tiếng Việt cho giao diện",
    )
    kiem(
        CITABLE_EVIDENCE == {"published"},
        "CHỈ `published` được dẫn như khuyến cáo có nguồn — `derived` kèm "
        "giả thiết nên không, `unsupported` thì không có nguồn nào",
    )
    kiem(
        "definitional" not in CITABLE_EVIDENCE,
        "`definitional` không dẫn nguồn được vì nó không có ngưỡng nào — "
        '"dị ứng trứng thì loại món có trứng" không cần WHO công bố',
    )

    def _ly(muc: str) -> ExclusionReason:
        return ExclusionReason(
            food_id="f",
            name="Món",
            dish_role="main",
            rule_type="nutrient_limit",
            condition="Tăng huyết áp",
            severity_min="mild",
            evidence_level=muc,
        )

    kiem(_ly("published").is_citable, "ngưỡng `published` dẫn được nguồn")
    kiem(not _ly("derived").is_citable, "ngưỡng `derived` thì không")
    kiem(not _ly("unsupported").is_citable, "ngưỡng `unsupported` thì không")
    kiem(
        _ly("unsupported").evidence_label == "không có nguồn đang hiệu lực",
        f"nhãn của `unsupported`: được {_ly('unsupported').evidence_label!r}",
    )

    # Mặc định phải là mức KHÔNG dẫn được nguồn. Chọn `published` làm mặc
    # định sẽ khiến mọi quy tắc thêm vào mà quên khai tự nhận là có nguồn.
    is_default = ExclusionReason(
        food_id="f", name="Món", dish_role="main",
        rule_type="nutrient_limit", condition="X", severity_min="mild",
    )
    kiem(
        not is_default.is_citable,
        f"mặc định `{is_default.evidence_level}` KHÔNG dẫn được nguồn",
    )

    # Một mức lạ không được làm hàm nổ, nhưng cũng không được dẫn nguồn.
    la = _ly("muc_la_nao_do")
    kiem(not la.is_citable, "mức lạ thì không dẫn nguồn được")
    kiem(la.evidence_label == "muc_la_nao_do", "mức lạ hiện nguyên văn, không nổ")

    # `SoftRule` và `DailyLimit` dùng cùng một quy ước.
    lm = SoftRule(
        condition="Rối loạn mỡ máu", severity_min="mild", nutrient="cholesterol_mg",
        comparator="lte", threshold=300.0, penalty=0.700, scope="per_day",
        evidence_level="unsupported",
    )
    kiem(not lm.is_citable, "SoftRule `unsupported` không dẫn nguồn")
    hm_ = DailyLimit(
        condition="Tăng huyết áp", nutrient="sodium_mg", comparator="lte",
        threshold=2000.0, eaten=0.0, planned=0.0,
        evidence_level="published",
    )
    kiem(hm_.is_citable, "DailyLimit `published` dẫn được nguồn")
    kiem(
        hm_.evidence_label == lm.evidence_label.replace(
            "không có nguồn đang hiệu lực", "có nguồn công bố"
        ),
        "ba lớp dùng cùng một bảng nhãn, không ai cài lại",
    )


def main() -> int:
    use_utf8()
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
        kiem_hinh_phat_mem,
        kiem_cau_giai_thich,
        kiem_muc_tin_cay,
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
