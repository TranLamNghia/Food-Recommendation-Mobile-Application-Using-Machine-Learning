# -*- coding: utf-8 -*-
"""Từ `ml_training_samples` dựng ma trận đặc trưng cho mô hình toàn cục.

`ML_PIPELINE.md` §6 mô tả đầu vào của Giai đoạn 2 là

        x = [ đặc trưng người dùng  ⊕  đặc trưng món ăn  ⊕  đặc trưng chéo ]

Tệp này hiện thực hóa ba khối đó, và điểm đáng nói nhất nằm ở khối thứ ba.

**Vì sao khối chéo quyết định tất cả.** Mô hình là **một mô hình cho tất cả
mọi người**, không phải mỗi người một mô hình. Nếu đầu vào chỉ có khối người
dùng cộng khối món thì một mô hình tuyến tính học được "người BMI cao thì
thích món ít béo" nhưng **không** học được "người *này* thích món ít béo" —
tính cá nhân hóa không có chỗ để biểu diễn. Khối chéo là chỗ đó:

    cos(p_u, vᵢ)      — một số: món này giống khẩu vị người này đến đâu
    p_u ⊙ vᵢ          — hai mươi số: giống ở **chiều nào**

Tích từng chiều `p_u ⊙ vᵢ` là phần cho mô hình tuyến tính học được rằng với
người thiên về đồ cay thì chiều "mức cay" của món phải được cộng điểm, còn
với người né đồ cay thì cùng chiều đó phải bị trừ. Một mình `cos` thì nén cả
hai mươi chiều thành một con số và mất thông tin đó.

`p_u` **luôn lấy từ `profile_snapshot`** — vector tại thời điểm thu tín hiệu,
không phải vector hiện tại. Dùng vector hiện tại là rò rỉ dữ liệu, xem
`ML_PIPELINE.md` §9.4.

**Một hạn chế đã biết, phải ghi vào báo cáo.** Khối người dùng lấy từ
`health_profiles` **hiện tại**, vì lược đồ không lưu lịch sử hồ sơ sức khỏe.
Nếu một người giảm 8 kg trong thời gian dùng app thì những mẫu cũ của họ bị
gắn cân nặng mới. Đây là rò rỉ nhẹ và theo một chiều: nó không mang thông tin
về *nhãn* của từng mẫu, nên không thổi phồng kết quả theo cách `p_u` hiện tại
sẽ làm. Khắc phục đúng là thêm bảng lịch sử, không phải thêm một phép đoán.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence

from .features import KhongGianDacTrung, Mon, cosine_similarity

GIOI_TINH = ("male", "female", "other")
MUC_VAN_DONG = ("sedentary", "light", "moderate", "active", "very_active")
MUC_TIEU = ("lose_weight", "maintain", "gain_weight", "healthy_eating")

#: Chặn trên của `n_signals` khi chuẩn hóa — bằng `n_max` của công thức α.
N_TIN_HIEU_TOI_DA = 100

#: Khoảng BMI dùng để chuẩn hóa. Chọn 15–40 vì đó là khoảng mà phân loại của
#: WHO cho châu Á còn có nghĩa; ngoài khoảng thì kẹp lại.
BMI_THAP, BMI_CAO = 15.0, 40.0


@dataclass
class HoSoNguoi:
    """Khối đặc trưng người dùng, đã quy về số."""

    gender: str = "other"
    age: int = 30
    bmi: float = 22.0
    activity_level: str = "moderate"
    goal: str = "maintain"
    #: Tỷ lệ năng lượng mục tiêu từ đạm / bột đường / béo, theo phần trăm.
    #: Mặc định 15–60–25 đúng như `health_profiles`.
    muc_tieu_macro: tuple[float, float, float] = (15.0, 60.0, 25.0)
    #: `True` khi người này **không có** `health_profiles` và cả khối đang
    #: dùng giá trị mặc định. Đếm được để báo cáo, thay vì lặng lẽ coi như thật.
    mac_dinh: bool = False


def _ep(x: float, thap: float = 0.0, cao: float = 1.0) -> float:
    return thap if x < thap else cao if x > cao else x


def nap_ho_so_nguoi(cn) -> dict[str, HoSoNguoi]:
    """Đọc `health_profiles`, tính tuổi từ `date_of_birth`.

    Lưu `date_of_birth` chứ không lưu tuổi là quyết định đúng của lược đồ —
    tuổi thì mỗi năm một sai — nhưng nó có nghĩa là tuổi phải tính ở đây, và
    tính theo **hôm nay**, không theo ngày thu tín hiệu. Với một đồ án vài
    tháng thì sai số dưới một tuổi; ghi lại để không ai tưởng là đã xử lý.
    """
    sql = """
        SELECT user_id, gender, date_of_birth, bmi, activity_level, goal,
               target_protein_pct, target_carbs_pct, target_fat_pct
        FROM health_profiles
    """
    hom_nay = date.today()
    ket_qua: dict[str, HoSoNguoi] = {}
    with cn.cursor() as cur:
        cur.execute(sql)
        for d in cur.fetchall():
            ns = d["date_of_birth"]
            tuoi = (
                hom_nay.year
                - ns.year
                - ((hom_nay.month, hom_nay.day) < (ns.month, ns.day))
            )
            ket_qua[d["user_id"]] = HoSoNguoi(
                gender=d["gender"],
                age=tuoi,
                bmi=float(d["bmi"]) if d["bmi"] is not None else 22.0,
                activity_level=d["activity_level"],
                goal=d["goal"],
                muc_tieu_macro=(
                    float(d["target_protein_pct"]),
                    float(d["target_carbs_pct"]),
                    float(d["target_fat_pct"]),
                ),
            )
    return ket_qua


def _khoi_nguoi(h: HoSoNguoi, n_signals: int) -> list[float]:
    v: list[float] = [0.0] * len(GIOI_TINH)
    if h.gender in GIOI_TINH:
        v[GIOI_TINH.index(h.gender)] = 1.0
    v.append(_ep(h.age / 100))
    v.append(_ep((h.bmi - BMI_THAP) / (BMI_CAO - BMI_THAP)))
    v.append(MUC_VAN_DONG.index(h.activity_level) / (len(MUC_VAN_DONG) - 1))
    mt = [0.0] * len(MUC_TIEU)
    if h.goal in MUC_TIEU:
        mt[MUC_TIEU.index(h.goal)] = 1.0
    v += mt
    v.append(_ep(min(n_signals, N_TIN_HIEU_TOI_DA) / N_TIN_HIEU_TOI_DA))
    return v


def ten_khoi_nguoi() -> list[str]:
    return (
        [f"nguoi.gioi_tinh={g}" for g in GIOI_TINH]
        + ["nguoi.tuoi", "nguoi.bmi", "nguoi.van_dong"]
        + [f"nguoi.muc_tieu={m}" for m in MUC_TIEU]
        + ["nguoi.n_tin_hieu"]
    )


def ten_dac_trung(kg: KhongGianDacTrung) -> list[str]:
    """Tên của từng cột đầu vào, theo đúng thứ tự `dung_hang_dac_trung` sinh ra.

    Hai danh sách này **phải** đi cùng nhau: `feature_importance` gắn tên vào
    cột theo vị trí, nên lệch một chỗ là cả bảng độ quan trọng đọc sai tên mà
    vẫn trông hợp lý. `dung_hang_dac_trung` tự kiểm điều này mỗi lần gọi.
    """
    return (
        ten_khoi_nguoi()
        + [f"mon.{nh}" for nh in kg.labels]
        + ["mon.do_pho_bien"]
        + ["cheo.cos"]
        + [f"cheo.tich.{nh}" for nh in kg.labels]
    )


def dung_hang_dac_trung(
    h: HoSoNguoi,
    n_tin_hieu: int,
    p_u: Sequence[float],
    v_mon: Sequence[float],
    do_pho_bien: float,
    *,
    so_chieu_mong_doi: int | None = None,
) -> list[float]:
    """Ghép ba khối thành **một hàng** đầu vào của mô hình.

    Hàm này là chỗ duy nhất biết thứ tự các cột, và nó được gọi từ **hai**
    nơi: `nap_tap` khi dựng tập huấn luyện, và `ml/serve.py` khi chấm điểm
    cho người dùng thật. Nếu hai nơi tự ghép riêng thì mô hình sẽ được huấn
    luyện trên một thứ tự cột và suy luận trên một thứ tự khác — cùng loại
    lỗi với việc hai bản trích đặc trưng Dart và Python lệch nhau, và cũng
    im lặng như thế: ma trận vẫn đủ 53 cột, mô hình vẫn trả về xác suất.
    """
    hang = (
        _khoi_nguoi(h, n_tin_hieu)
        + list(v_mon)
        + [do_pho_bien]
        + [cosine_similarity(p_u, v_mon)]
        + [a * b for a, b in zip(p_u, v_mon)]
    )
    if so_chieu_mong_doi is not None and len(hang) != so_chieu_mong_doi:
        raise AssertionError(
            f"Dựng được {len(hang)} đặc trưng nhưng mong đợi "
            f"{so_chieu_mong_doi} — hai danh sách phải khớp, nếu không "
            f"`feature_importance` sẽ gắn sai tên vào sai cột."
        )
    return hang


@dataclass
class TapDacTrung:
    """Ma trận đặc trưng cùng mọi thứ cần để huấn luyện và đánh giá."""

    X: list[list[float]]
    y: list[float]
    #: Nhãn nhị phân `label >= 0.5`, dùng cho f1 / auc và cho mô hình phân lớp.
    y_lop: list[int]
    sample_weight: list[float]
    user_id: list[str]
    food_id: list[str]
    source: list[str]
    fold: list[int]
    #: Vai trong **lần chia tham chiếu** do `build_dataset` ghi sẵn:
    #: `train` / `val` / `test`. Phần kiểm định chéo không dùng cột này, nó
    #: xoay vòng `fold`.
    split: list[str]
    #: Vector sở thích **tại thời điểm thu tín hiệu**, lấy từ
    #: `profile_snapshot`. Phương án đối chứng `content_based` chấm điểm bằng
    #: chính nó, nên nó phải ra tới đây chứ không chỉ nằm trong khối chéo.
    p_u: list[list[float]]
    #: `n_signals` của ảnh chụp — đầu vào của hệ số trộn α.
    n_tin_hieu: list[int]
    #: Vector đặc trưng món, tách riêng để `content_based` dùng lại.
    v_mon: list[list[float]]
    #: `foods.popularity_score` — phương án đối chứng `popularity` dùng.
    do_pho_bien: list[float]
    #: Tỷ lệ macro mục tiêu của người dùng — `rule_based` dùng.
    muc_tieu_macro: list[tuple[float, float, float]]
    ten_dac_trung: list[str]
    #: Số mẫu dùng hồ sơ sức khỏe mặc định vì người đó chưa khai.
    so_ho_so_mac_dinh: int = 0
    #: Số mẫu có `profile_snapshot` rỗng (chưa vuốt lượt nào trước đó).
    so_anh_chup_rong: int = 0

    def __len__(self) -> int:
        return len(self.y)


#: Ngưỡng tách "thích" / "không thích" khi cần nhãn nhị phân.
#:
#: Đặt ở 0,5 chứ không ở giữa dải nhãn thực tế, vì 0,5 là **điểm trung tính
#: có nghĩa**: lượt vuốt `neutral` mang đúng nhãn 0,500 và đánh giá 3 sao
#: cũng vậy. Mọi tín hiệu từ đó lên là nghiêng về thích.
#:
#: `>=` chứ không `>`: nhãn 0,500 tính là thích. Đây là một lựa chọn, không
#: phải một sự thật — và nó phải nhất quán giữa huấn luyện với đánh giá, nên
#: hằng số này là chỗ duy nhất định nghĩa nó.
NGUONG_THICH = 0.5


def nap_tap(
    cn,
    *,
    dataset_version: str,
    kg: KhongGianDacTrung,
    mon_theo_id: dict[str, Mon],
) -> TapDacTrung:
    """Dựng `TapDacTrung` từ một phiên bản tập dữ liệu."""
    sql = """
        SELECT s.user_id, s.food_id, s.source, s.label, s.sample_weight,
               s.fold, s.split, s.profile_snapshot, f.popularity_score
        FROM ml_training_samples s
        JOIN foods f ON f.id = s.food_id
        WHERE s.dataset_version = %s
        ORDER BY s.user_id, s.source, s.food_id
    """
    with cn.cursor() as cur:
        cur.execute(sql, (dataset_version,))
        dong = cur.fetchall()

    ho_so = nap_ho_so_nguoi(cn)

    ten = ten_dac_trung(kg)

    t = TapDacTrung(
        X=[], y=[], y_lop=[], sample_weight=[], user_id=[], food_id=[],
        source=[], fold=[], split=[], p_u=[], n_tin_hieu=[], v_mon=[],
        do_pho_bien=[], muc_tieu_macro=[], ten_dac_trung=ten,
    )

    for d in dong:
        m = mon_theo_id.get(d["food_id"])
        if m is None:
            # Món đã bị vô hiệu hóa hoặc là món riêng tư. Bỏ mẫu thay vì
            # đoán vector cho nó.
            continue

        anh = json.loads(d["profile_snapshot"]) if d["profile_snapshot"] else None
        p_u = list(anh["weights"]) if anh else [0.0] * kg.length
        n_tin_hieu = int(anh["n_signals"]) if anh else 0
        if len(p_u) != kg.length:
            raise ValueError(
                f"profile_snapshot có {len(p_u)} chiều nhưng không gian đặc "
                f"trưng hiện tại có {kg.length}. Tập dữ liệu được dựng bằng "
                f"một phiên bản đặc trưng khác — dựng lại bằng "
                f"`python -m ml.build_dataset`."
            )
        if not any(p_u):
            t.so_anh_chup_rong += 1

        h = ho_so.get(d["user_id"])
        if h is None:
            h = HoSoNguoi(mac_dinh=True)
            t.so_ho_so_mac_dinh += 1

        v = kg.encode(m)
        x = dung_hang_dac_trung(
            h,
            n_tin_hieu,
            p_u,
            v,
            float(d["popularity_score"]),
            so_chieu_mong_doi=len(ten),
        )

        nhan = float(d["label"])
        t.X.append(x)
        t.y.append(nhan)
        t.y_lop.append(1 if nhan >= NGUONG_THICH else 0)
        t.sample_weight.append(float(d["sample_weight"]))
        t.user_id.append(d["user_id"])
        t.food_id.append(d["food_id"])
        t.source.append(d["source"])
        t.fold.append(int(d["fold"]))
        t.split.append(d["split"])
        t.p_u.append(p_u)
        t.n_tin_hieu.append(n_tin_hieu)
        t.v_mon.append(v)
        t.do_pho_bien.append(float(d["popularity_score"]))
        t.muc_tieu_macro.append(h.muc_tieu_macro)

    return t


def nap_khong_gian(cn) -> tuple[KhongGianDacTrung, dict[str, Mon]]:
    """Tiện ích: nạp món rồi dựng không gian đặc trưng, không in báo cáo."""
    from .features import nap_mon

    mon, _ = nap_mon(cn)
    return KhongGianDacTrung.tu_mon(mon), {m.id: m for m in mon}


def thong_ke(t: TapDacTrung) -> str:
    dem_nguon: dict[str, int] = {}
    for s in t.source:
        dem_nguon[s] = dem_nguon.get(s, 0) + 1
    thich = sum(t.y_lop)
    return "\n".join(
        [
            f"{len(t)} mẫu · {len(t.ten_dac_trung)} đặc trưng · "
            f"{len(set(t.user_id))} người dùng",
            f"  nhãn ≥ {NGUONG_THICH}: {thich} "
            f"({thich / len(t):.1%})" if t else "  (tập rỗng)",
            "  nguồn: " + " ".join(f"{k}={v}" for k, v in sorted(dem_nguon.items())),
            f"  hồ sơ sức khỏe mặc định: {t.so_ho_so_mac_dinh} mẫu",
            f"  ảnh chụp hồ sơ rỗng:     {t.so_anh_chup_rong} mẫu",
        ]
    )
