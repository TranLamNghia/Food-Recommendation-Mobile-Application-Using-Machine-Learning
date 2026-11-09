# -*- coding: utf-8 -*-
"""Trích chọn đặc trưng món ăn — **bản Python của `food_vector.dart`**.

Vì sao tệp này tồn tại. Ứng dụng Flutter chấm điểm món bằng vector đặc trưng
dựng ở `mobile/lib/data/recommender/food_vector.dart`, nhưng việc huấn luyện
mô hình phải chạy bằng Python. Hai bản **buộc phải cho ra cùng một vector**:
nếu lệch, mô hình học trên một không gian rồi suy luận trên một không gian
khác — một lỗi không bao giờ báo ra, vì mô hình vẫn chạy và vẫn trả về số.
`tools/check_feature_parity.py` đối chiếu từng chiều giữa hai bản.

Ba cái bẫy đã gặp khi dịch, ghi lại ở đây vì chúng vô hình khi đọc mã:

1.  **`kcal` là số nguyên ở phía Dart** (`Food.kcal` khai `int`) nhưng là
    `DECIMAL(7,2)` trong CSDL. Phải làm tròn ở đúng một chỗ, và làm tròn
    **giống Dart**: `num.round()` của Dart làm tròn 0,5 ra xa số không, còn
    `round()` của Python làm tròn về số chẵn — `round(2.5)` cho 2. Nên dùng
    `floor(x + 0.5)`, xem `lam_tron_kcal`.

2.  **Ba chiều macro là tỷ lệ *năng lượng*, không phải tỷ lệ gam**: đạm và
    bột đường nhân 4, béo nhân 9. Dịch thành `protein / (protein+carb+fat)`
    sẽ cho ra một vector trông rất hợp lý và sai hoàn toàn.

3.  **Thứ tự chiều phải ổn định**, nên danh sách nhóm món luôn được sắp xếp.
    `List<String>.sort()` của Dart so sánh theo đơn vị mã UTF-16, `sorted()`
    của Python so theo điểm mã Unicode. Hai cách này **trùng nhau** với mọi
    ký tự thuộc mặt phẳng cơ bản, mà chữ Việt thì đều thuộc mặt phẳng đó —
    nên hiện tại an toàn. Chỉ hỏng nếu tên nhóm có emoji.

Phiên bản đặc trưng được gắn vào `ml_models.feature_version`: đổi bất cứ
chiều nào thì **phải** tăng số này, nếu không một mô hình cũ sẽ được nạp lại
với một vector khác và không ai biết.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Iterable, Sequence

#: Tăng mỗi khi tập chiều hoặc cách chuẩn hóa thay đổi.
#:
#: v1 → v2: chiều "Vị ngọt" đổi từ `sugar_g / carbs_g` sang **nồng độ đường**
#: `sugar_g / serving_size_g` rồi chuẩn hóa min–max. Lý do ở `Mon.nong_do_duong`.
FEATURE_VERSION = "v2"

#: Mức cay chạy 0–3 (`foods.spice_level`), chia cho hằng này để về [0, 1].
MUC_CAY_TOI_DA = 3


# ── Món ăn ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Mon:
    """Một món ăn, đã quy về đúng kiểu dữ liệu mà phía Dart nhìn thấy.

    `suy_ra` liệt kê những trường vốn `NULL` trong CSDL và đã được **suy ra**
    bằng trung vị. Giữ danh sách này thay vì âm thầm thay số là có chủ ý: khi
    báo cáo kết quả phải nói được bao nhiêu món mang giá trị suy ra.
    """

    id: str
    name: str
    category: str
    dish_role: str
    spice_level: int
    kcal: int
    protein: float
    carb: float
    fat: float
    sugar: float
    sodium: float
    fiber: float
    #: Khối lượng một suất, tính bằng gam (`food_nutrition.serving_size_g`).
    #: Mọi số dinh dưỡng ở trên là **của cả suất**, không phải trên 100 g.
    serving_size_g: float = 100.0
    suy_ra: tuple[str, ...] = ()

    # Tỷ lệ năng lượng từ mỗi chất sinh năng lượng — xem bẫy số 2 ở đầu tệp.
    @property
    def macro_share(self) -> tuple[float, float, float]:
        tong = self.protein * 4 + self.carb * 4 + self.fat * 9
        if tong <= 0:
            return (0.0, 0.0, 0.0)
        return (
            self.protein * 4 / tong,
            self.carb * 4 / tong,
            self.fat * 9 / tong,
        )

    @property
    def nong_do_duong(self) -> float:
        """Đường trên mỗi gam món ăn — đại lượng đo được cho vị ngọt.

        Dùng **nồng độ** chứ không dùng số gam thuần vì khẩu vị là về *cấu
        trúc* món ăn: một suất 400 g chứa 20 g đường không ngọt bằng một
        suất 100 g chứa 15 g đường.

        **Vì sao mẫu số là khối lượng suất, không phải lượng bột đường.** Bản
        v1 dùng `sugar_g / carbs_g`, và nó vỡ ở món ít bột đường: tỷ lệ nổ
        khi mẫu số nhỏ. Đo trên 318 món thật, **46 món bị kẹp về đúng 1,000**
        — tức 14 % danh mục đọc ra "ngọt tối đa" — và trong đó có *trứng
        luộc* (0,6 g bột đường) cùng *canh hẹ đậu phụ* (2,2 g) đứng ngang
        *chuối sứ* và *nước ép lựu*. Khi hai món đó không phân biệt được trên
        chiều này thì Rocchio **không thể học được sở thích ngọt**: nó là một
        chiều đầy nhiễu chứ không phải một chiều đặc trưng.

        Đổi mẫu số sang `serving_size_g` giữ nguyên ý định ban đầu — vẫn là
        nồng độ, vẫn không phụ thuộc khẩu phần — nhưng mẫu số là khối lượng
        cả suất nên không bao giờ nhỏ bất thường. Sau khi đổi: 1/318 món ở
        mức tối đa, trứng luộc 0,036, canh hẹ 0,074, dưa hấu 0,279, chuối sứ
        1,000.

        Trả về nồng độ **thô**; phép chuẩn hóa min–max do `KhongGianDacTrung`
        làm, cùng cách với natri và chất xơ, vì "ngọt" là khái niệm tương đối
        trong phạm vi tập món đang có.
        """
        if self.serving_size_g <= 0:
            return 0.0
        return self.sugar / self.serving_size_g


def lam_tron_kcal(x: float) -> int:
    """Làm tròn năng lượng về số nguyên **giống `num.round()` của Dart**.

    Không dùng `round()` của Python: nó làm tròn về số chẵn, nên `round(2.5)`
    ra 2 trong khi Dart cho 3. Xem bẫy số 1 ở đầu tệp.
    """
    return math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5)


def _ep(x: float, thap: float = 0.0, cao: float = 1.0) -> float:
    """Kẹp về đoạn [thap, cao] — tương đương `clamp` của Dart."""
    return thap if x < thap else cao if x > cao else x


# ── Nạp món từ CSDL, kèm báo cáo chất lượng ──────────────────────────


@dataclass
class BaoCaoChatLuong:
    """Những gì dữ liệu còn thiếu hoặc còn tự mâu thuẫn.

    In ra mỗi lần nạp. Một con số đánh giá đẹp dựng trên dữ liệu khuyết mà
    không ai nhắc tới thì không bảo vệ được.
    """

    so_mon: int = 0
    suy_ra: dict[str, int] = field(default_factory=dict)
    #: `(tên món, g đường, g bột đường, đường có phải suy ra hay không)`
    duong_vuot_bot_duong: list[tuple[str, float, float, bool]] = field(
        default_factory=list
    )
    cay_bang_khong: int = 0

    def in_ra(self) -> None:
        print(f"Đã nạp {self.so_mon} món.")
        for cot, n in sorted(self.suy_ra.items()):
            print(f"  · {cot:12} {n:3} món NULL → thay bằng trung vị nhóm")
        # Đường nhiều hơn tổng bột đường là điều không thể về mặt dinh dưỡng.
        # Từ v2, chiều vị ngọt không còn chia cho `carbs_g` nên những món này
        # **không làm lệch vector** nữa — nhưng vẫn phải báo, và phải tách
        # làm hai nhóm, vì hai nhóm có hai nguyên nhân khác nhau:
        #
        #   · đo được  — `carbs_g` khóa theo FCT Việt Nam còn `sugar_g` vay
        #     từ USDA. Hai định nghĩa đo khác nhau, dồn vào trái cây và nước
        #     ép. Là một mục của phần hạn chế dữ liệu, không phải lỗi mã.
        #   · suy ra   — chính `carbs_g` của món đó thấp bất thường, nên bất
        #     kỳ lượng đường hợp lý nào cũng vượt nó. Đây là **cờ báo lỗi dữ
        #     liệu ở cột bột đường**, chỗ cần kiểm lại khi rà danh mục.
        for ten_nhom, loc in (
            ("đo được", lambda s: not s),
            ("suy ra", lambda s: s),
        ):
            ds = [t for t in self.duong_vuot_bot_duong if loc(t[3])]
            if not ds:
                continue
            ten, d, b, _ = max(ds, key=lambda t: t[1] / t[2])
            print(
                f"  · {'sugar>carb':12} {len(ds):3} món có đường > tổng bột "
                f"đường ({ten_nhom})"
            )
            print(f"      nặng nhất: {ten} ({d:g} g đường / {b:g} g bột đường)")
        print(f"  · {'spice_level':12} {self.cay_bang_khong:3} món ở mức cay 0")


SQL_MON = """
SELECT f.id, f.name, c.name AS category, f.dish_role, f.spice_level,
       n.serving_size_g, n.calories_kcal, n.protein_g, n.carbs_g, n.fat_g,
       n.sugar_g, n.sodium_mg, n.fiber_g
FROM foods f
JOIN food_categories c ON c.id = f.category_id
JOIN food_nutrition  n ON n.food_id = f.id
WHERE (%(chi_mon_hoat_dong)s = 0 OR f.is_active = 1)
ORDER BY f.name, f.id
"""

#: Các cột `NULL` được phép suy ra. `calories_kcal`, `protein_g`, `carbs_g`,
#: `fat_g` không có ở đây vì chúng `NOT NULL` — thiếu là lỗi dữ liệu, không
#: phải chỗ để đoán.
COT_SUY_RA = ("sugar_g", "sodium_mg", "fiber_g")

#: `sugar_g` suy theo **nồng độ**, không theo số gam tuyệt đối.
#:
#: Lần làm đầu dùng trung vị số gam của nhóm cho cả ba cột, và số món có
#: `đường > bột đường` nhảy từ 28 lên 35: phép suy **tự tạo thêm 7 món tự
#: mâu thuẫn**, vì trung vị đường của nhóm không liên quan gì tới khẩu phần
#: của chính món đang thiếu.
#:
#: Mẫu số phải **trùng với mẫu số mà chiều vị ngọt dùng tới**, nếu không
#: phép suy sẽ tạo tác ngay trên chiều đó. Khi chiều vị ngọt còn là
#: `sugar/carbs`, mẫu số ở đây là `carbs_g` — và cơm trắng (60 g bột đường)
#: bị suy ra một lượng đường lớn, đọc thành 0,201 trên thang ngọt dù cơm
#: không ngọt. Giờ chiều vị ngọt là `sugar/serving_size_g` thì mẫu số ở đây
#: cũng là `serving_size_g`, và tạo tác đó biến mất.
#:
#: Natri và chất xơ thì ngược lại: chúng vào vector dưới dạng **tuyệt đối**
#: đã chuẩn hóa min–max, nên trung vị số gam mới là ước lượng đúng.
COT_SUY_THEO_TY_LE = {"sugar_g": "serving_size_g"}


def nap_mon(cn, *, chi_mon_hoat_dong: bool = True) -> tuple[list[Mon], BaoCaoChatLuong]:
    """Nạp toàn bộ món kèm dinh dưỡng, suy ra giá trị khuyết, trả kèm báo cáo.

    **Suy giá trị khuyết đặt ở đây, không đặt trong `KhongGianDacTrung`.** Lý
    do là kiến trúc: ứng dụng Flutter nhận số đã sạch qua API và khai các
    trường dinh dưỡng là `double` không rỗng, nên nó *không thể* biết giá trị
    nào là suy ra. Vậy phép suy phải nằm phía máy chủ, ở trên tầng dựng
    vector — và hai bản dựng vector nhờ đó vẫn giống nhau từng chiều.

    Cách suy: **trung vị của chính nhóm món**, lùi về trung vị toàn danh mục
    nếu cả nhóm không có số nào. Không dùng 0: một món thiếu `sodium_mg` mà
    gán 0 sẽ thành món nhạt nhất danh mục, tức là bịa ra một giá trị cực trị.
    Riêng `sugar_g` suy theo tỷ lệ — xem `COT_SUY_THEO_TY_LE`.
    """
    with cn.cursor() as cur:
        cur.execute(SQL_MON, {"chi_mon_hoat_dong": 1 if chi_mon_hoat_dong else 0})
        dong = cur.fetchall()

    # Trung vị theo nhóm, rồi trung vị toàn bộ, cho từng cột được phép suy.
    # Với cột suy theo tỷ lệ thì lấy trung vị của chính tỷ lệ đó.
    tv_nhom: dict[tuple[str, str], float] = {}
    tv_chung: dict[str, float] = {}
    for cot in COT_SUY_RA:
        mau = COT_SUY_THEO_TY_LE.get(cot)
        theo_nhom: dict[str, list[float]] = {}
        tat_ca: list[float] = []
        for d in dong:
            v = d[cot]
            if v is None:
                continue
            if mau is not None:
                chia = float(d[mau] or 0)
                if chia <= 0:
                    continue  # tỷ lệ không xác định, không góp vào trung vị
                x = _ep(float(v) / chia)
            else:
                x = float(v)
            theo_nhom.setdefault(d["category"], []).append(x)
            tat_ca.append(x)
        for nhom, ds in theo_nhom.items():
            tv_nhom[(cot, nhom)] = float(median(ds))
        tv_chung[cot] = float(median(tat_ca)) if tat_ca else 0.0

    bao_cao = BaoCaoChatLuong(so_mon=len(dong))
    mon: list[Mon] = []

    for d in dong:
        da_suy: list[str] = []
        gia_tri: dict[str, float] = {}
        for cot in COT_SUY_RA:
            v = d[cot]
            if v is None:
                uoc = tv_nhom.get((cot, d["category"]), tv_chung[cot])
                mau = COT_SUY_THEO_TY_LE.get(cot)
                # Cột suy theo tỷ lệ: nhân trung vị tỷ lệ với mẫu số của
                # chính món này, nên không thể vượt quá mẫu số đó.
                gia_tri[cot] = uoc * float(d[mau] or 0) if mau else uoc
                da_suy.append(cot)
                bao_cao.suy_ra[cot] = bao_cao.suy_ra.get(cot, 0) + 1
            else:
                gia_tri[cot] = float(v)

        m = Mon(
            id=d["id"],
            name=d["name"],
            category=d["category"],
            dish_role=d["dish_role"],
            spice_level=int(d["spice_level"]),
            kcal=lam_tron_kcal(float(d["calories_kcal"])),
            protein=float(d["protein_g"]),
            carb=float(d["carbs_g"]),
            fat=float(d["fat_g"]),
            sugar=gia_tri["sugar_g"],
            sodium=gia_tri["sodium_mg"],
            fiber=gia_tri["fiber_g"],
            serving_size_g=float(d["serving_size_g"]),
            suy_ra=tuple(da_suy),
        )
        mon.append(m)

        if m.carb > 0 and m.sugar > m.carb:
            bao_cao.duong_vuot_bot_duong.append(
                (m.name, m.sugar, m.carb, "sugar_g" in m.suy_ra)
            )
        if m.spice_level == 0:
            bao_cao.cay_bang_khong += 1

    return mon, bao_cao


# ── Không gian đặc trưng ─────────────────────────────────────────────


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

#: Chiều ứng với một chất dinh dưỡng đơn lẻ, dùng khi người dùng **tự khai**
#: một mục tiêu ("tôi muốn ăn nhiều chất xơ"). Ba chiều macro cố tình không
#: có mặt: chúng là tỷ lệ cộng lại bằng 1, nên đẩy tỷ lệ đạm lên đồng nghĩa
#: với dìm hai tỷ lệ kia xuống — không cùng một ý với "muốn ăn nhiều đạm".
NHAN_THEO_CHAT = {
    "sugar_g": "Vị ngọt",
    "sodium_mg": "Vị mặn",
    "fiber_g": "Chất xơ",
}


class KhongGianDacTrung:
    """Phép ánh xạ món ăn → vector số, cố định sau khi dựng.

    Số chiều là `8 + số nhóm món`: 4 dinh dưỡng + ngọt + mặn + xơ + cay, rồi
    one-hot nhóm. Nhóm món **gánh luôn phương pháp chế biến** — nhóm
    `Món chiên` thì cách chế biến là chiên — nên không có khối one-hot riêng
    cho cách chế biến.

    Ba tham số min–max (năng lượng, natri, chất xơ) là **trạng thái của
    không gian**, không phải của món. Chúng phải được lưu cùng mô hình
    (`ml_models.scaler_params`) và nạp lại khi suy luận: tính lại min–max
    trên dữ liệu mới là một lỗi âm thầm làm điểm số lệch dần theo thời gian.
    """

    def __init__(
        self,
        *,
        categories: Sequence[str],
        min_kcal: float,
        max_kcal: float,
        min_sugar: float,
        max_sugar: float,
        min_sodium: float,
        max_sodium: float,
        min_fiber: float,
        max_fiber: float,
    ) -> None:
        self.categories = list(categories)
        self.min_kcal = min_kcal
        self.max_kcal = max_kcal
        #: Biên nồng độ đường (g đường trên g món), xem `Mon.nong_do_duong`.
        self.min_sugar = min_sugar
        self.max_sugar = max_sugar
        self.min_sodium = min_sodium
        self.max_sodium = max_sodium
        self.min_fiber = min_fiber
        self.max_fiber = max_fiber
        self._chi_so_nhom = {c: i for i, c in enumerate(self.categories)}

    # ── dựng ──
    @classmethod
    def tu_mon(cls, mon: Iterable[Mon]) -> "KhongGianDacTrung":
        ds = list(mon)
        if not ds:
            raise ValueError("Không dựng được không gian đặc trưng từ tập món rỗng.")
        return cls(
            categories=sorted({m.category for m in ds}),
            min_kcal=min(m.kcal for m in ds),
            max_kcal=max(m.kcal for m in ds),
            min_sugar=min(m.nong_do_duong for m in ds),
            max_sugar=max(m.nong_do_duong for m in ds),
            min_sodium=min(m.sodium for m in ds),
            max_sodium=max(m.sodium for m in ds),
            min_fiber=min(m.fiber for m in ds),
            max_fiber=max(m.fiber for m in ds),
        )

    # ── lưu / nạp lại ──
    def tham_so(self) -> dict[str, Any]:
        """Dạng JSON để ghi vào `ml_models.scaler_params`."""
        return {
            "feature_version": FEATURE_VERSION,
            "categories": list(self.categories),
            "min_kcal": self.min_kcal,
            "max_kcal": self.max_kcal,
            "min_sugar": self.min_sugar,
            "max_sugar": self.max_sugar,
            "min_sodium": self.min_sodium,
            "max_sodium": self.max_sodium,
            "min_fiber": self.min_fiber,
            "max_fiber": self.max_fiber,
        }

    @classmethod
    def tu_tham_so(cls, d: dict[str, Any]) -> "KhongGianDacTrung":
        ban = d.get("feature_version")
        if ban != FEATURE_VERSION:
            raise ValueError(
                f"scaler_params thuộc phiên bản đặc trưng {ban!r} nhưng mã "
                f"hiện tại là {FEATURE_VERSION!r}. Mô hình cũ không nạp được "
                f"với vector mới — huấn luyện lại hoặc dùng đúng bản mã."
            )
        return cls(
            categories=d["categories"],
            min_kcal=d["min_kcal"],
            max_kcal=d["max_kcal"],
            min_sugar=d["min_sugar"],
            max_sugar=d["max_sugar"],
            min_sodium=d["min_sodium"],
            max_sodium=d["max_sodium"],
            min_fiber=d["min_fiber"],
            max_fiber=d["max_fiber"],
        )

    # ── mô tả ──
    @property
    def length(self) -> int:
        return len(NHAN_CO_DINH) + len(self.categories)

    @property
    def labels(self) -> list[str]:
        return [*NHAN_CO_DINH, *(f"Nhóm: {c}" for c in self.categories)]

    def chieu_cua_chat(self, nutrient: str) -> int | None:
        nhan = NHAN_THEO_CHAT.get(nutrient)
        if nhan is None:
            return None
        nhan_ds = self.labels
        return nhan_ds.index(nhan) if nhan in nhan_ds else None

    # ── mã hóa ──
    def encode(self, m: Mon) -> list[float]:
        v = [0.0] * self.length
        dam, bot, beo = m.macro_share

        v[0] = dam
        v[1] = bot
        v[2] = beo
        v[3] = self._chuan_hoa(float(m.kcal), self.min_kcal, self.max_kcal)
        v[4] = self._chuan_hoa(m.nong_do_duong, self.min_sugar, self.max_sugar)
        v[5] = self._chuan_hoa(m.sodium, self.min_sodium, self.max_sodium)
        v[6] = self._chuan_hoa(m.fiber, self.min_fiber, self.max_fiber)
        v[7] = m.spice_level / MUC_CAY_TOI_DA

        i = self._chi_so_nhom.get(m.category)
        if i is not None:
            v[len(NHAN_CO_DINH) + i] = 1.0

        return v

    @staticmethod
    def _chuan_hoa(x: float, thap: float, cao: float) -> float:
        """Chuẩn hóa min–max.

        Khi cả tập chỉ có một mức giá trị thì mẫu số bằng 0; lúc đó trả 0,5
        để chiều này không đóng góp lệch về bên nào. Phía Dart làm đúng vậy.
        """
        if cao <= thap:
            return 0.5
        return _ep((x - thap) / (cao - thap))


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Độ tương đồng cosin, trả 0 khi một vector có độ dài 0."""
    if len(a) != len(b):
        raise ValueError(f"Hai vector phải cùng số chiều: {len(a)} ≠ {len(b)}")
    tich = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return tich / (na * nb)
