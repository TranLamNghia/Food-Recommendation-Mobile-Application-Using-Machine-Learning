# -*- coding: utf-8 -*-
"""Bộ lọc F1 — tầng an toàn, đặt **trước** mọi phép chấm điểm.

Loại khỏi tập ứng viên mọi món vi phạm ràng buộc cứng, bất kể người dùng
thích món đó đến đâu. Bộ quy tắc nằm **dưới dạng dữ liệu** trong
`condition_rules`, không viết cứng trong mã: thêm một bệnh lý là thêm dòng,
không phải sửa mã.

`tools/check_f1.py` đã chứng minh lược đồ đủ sức biểu diễn F1 bằng SQL thuần.
Tệp này biến phép chứng minh đó thành một hàm dùng được cho cả ba giai đoạn,
và bổ sung hai điều mà bản chứng minh bỏ qua:

**1. `severity_min` được tôn trọng.** Một quy tắc chỉ áp khi mức độ bệnh của
người dùng đạt tối thiểu `severity_min`. `check_f1.py` nhận vào danh sách tên
bệnh nên không biểu diễn được mức độ, và vì vậy nó áp **mọi** quy tắc — chặt
hơn thực tế. Bỏ qua cột này thì một người tăng huyết áp mức nhẹ sẽ bị cắt
đúng bằng một người mức nặng, và cột `severity_min` trong lược đồ thành vô
nghĩa.

**2. Ràng buộc mềm được trả về chứ không bị bỏ.** `is_hard = 0` nghĩa là
**trừ điểm** ở bước chấm điểm, món vẫn ở trong tập ứng viên. Nếu mọi ràng
buộc đều cứng thì tập ứng viên teo lại và bộ tối ưu Bước 4 không tìm nổi tổ
hợp thỏa hạn mức năng lượng — ràng buộc mềm chính là đường xoay xở.

Một điều quy tắc **không** làm: ngưỡng dinh dưỡng cứng theo ngày
(`scope = 'per_day'`) không lọc món nào ở đây. Một món mặn vẫn hợp lệ nếu cả
ngày vẫn dưới ngưỡng; phần theo ngày do Bước 4 pha 5 thi hành. Hàm
`han_muc_theo_ngay` trả về đúng những hạn mức đó để Bước 4 dùng.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

#: Mức tin cậy của một ngưỡng, từ `condition_rules.evidence_level`.
#:
#: Giao diện dùng nó để chọn giọng: dẫn khuyến cáo của WHO và một con số
#: chưa ai tra bằng cùng một giọng là không trung thực. Trước đây mức này
#: nằm trong văn xuôi cột `note`, nên muốn lọc phải tìm chuỗi "chưa xác
#: minh" — hỏng ngay lần đầu ai sửa câu chữ.
MUC_TIN_CAY = ("definitional", "published", "derived", "unsupported")

#: Mức nào được phép dẫn như khuyến cáo có nguồn.
DAN_DUOC_NGUON = frozenset({"published"})

#: Câu ngắn cho giao diện, theo từng mức.
NHAN_TIN_CAY = {
    "definitional": "quy tắc định nghĩa",
    "published": "có nguồn công bố",
    "derived": "suy ra kèm giả thiết",
    "unsupported": "không có nguồn đang hiệu lực",
}

#: Thứ tự mức độ. Dùng cả ở Python và trong SQL qua `FIELD()`.
THU_TU_MUC_DO = ("mild", "moderate", "severe")


@dataclass(frozen=True)
class DieuKien:
    """Một bệnh lý / dị ứng / chế độ ăn của người dùng, kèm mức độ."""

    condition_id: int
    severity: str = "moderate"
    name_vi: str = ""

    def __post_init__(self) -> None:
        if self.severity not in THU_TU_MUC_DO:
            raise ValueError(
                f"severity phải thuộc {THU_TU_MUC_DO}, nhận {self.severity!r}"
            )


# ── Lấy điều kiện của một người dùng thật ─────────────────────────────


def dieu_kien_cua_nguoi_dung(cn, user_id: str) -> list[DieuKien]:
    """Đọc `user_conditions` của một người, kèm mức độ và tên bệnh."""
    sql = """
        SELECT uc.condition_id, uc.severity, co.name_vi
        FROM user_conditions uc
        JOIN conditions co ON co.id = uc.condition_id
        WHERE uc.user_id = %s
        ORDER BY co.name_vi
    """
    with cn.cursor() as cur:
        cur.execute(sql, (user_id,))
        return [
            DieuKien(int(d["condition_id"]), d["severity"], d["name_vi"])
            for d in cur.fetchall()
        ]


def dieu_kien_theo_ten(cn, ten: Sequence[str], severity: str = "severe") -> list[DieuKien]:
    """Tra điều kiện theo `conditions.name_vi` — dùng khi thử tình huống.

    Mặc định `severe` để áp **mọi** quy tắc, tức là giữ đúng hành vi của
    `tools/check_f1.py`: đó là trường hợp chặt nhất, cũng là trường hợp phải
    kiểm vì nếu nó còn dựng nổi thực đơn thì mọi mức nhẹ hơn đều dựng nổi.
    """
    if not ten:
        return []
    cho = ", ".join(["%s"] * len(ten))
    with cn.cursor() as cur:
        cur.execute(
            f"SELECT id, name_vi FROM conditions WHERE name_vi IN ({cho})",
            tuple(ten),
        )
        tim_duoc = {d["name_vi"]: int(d["id"]) for d in cur.fetchall()}

    thieu = [t for t in ten if t not in tim_duoc]
    if thieu:
        raise ValueError(
            "Không có bệnh lý nào tên như vậy trong `conditions`: "
            + ", ".join(repr(t) for t in thieu)
        )
    return [DieuKien(tim_duoc[t], severity, t) for t in ten]


# ── Bộ lọc ────────────────────────────────────────────────────────────

#: Ánh xạ `condition_rules.nutrient` → cột của `food_nutrition`. Viết một lần
#: ở đây thay vì một khối `CASE` dài trong SQL: một chất mới chỉ phải thêm
#: vào đúng một chỗ, và quên thêm thì `_cot_dinh_duong` báo lỗi ngay thay vì
#: trả về `NULL` rồi âm thầm loại sạch món.
COT_DINH_DUONG = {
    "calories_kcal": "fn.calories_kcal",
    "protein_g": "fn.protein_g",
    "carbs_g": "fn.carbs_g",
    "fat_g": "fn.fat_g",
    "fiber_g": "fn.fiber_g",
    "sugar_g": "fn.sugar_g",
    "sodium_mg": "fn.sodium_mg",
    "cholesterol_mg": "fn.cholesterol_mg",
    "purine_mg": "fn.purine_mg",
    "calcium_mg": "fn.calcium_mg",
    "iron_mg": "fn.iron_mg",
    "zinc_mg": "fn.zinc_mg",
    "vitamin_a_mcg": "fn.vitamin_a_mcg",
    "vitamin_c_mg": "fn.vitamin_c_mg",
}

_CASE_CHAT = "CASE cr.nutrient\n" + "\n".join(
    f"              WHEN '{chat}' THEN {cot}" for chat, cot in COT_DINH_DUONG.items()
) + "\n            END"

#: Mệnh đề so mức độ: quy tắc chỉ áp khi mức của người dùng đạt `severity_min`.
_DU_MUC_DO = (
    "FIELD(dk.severity, 'mild', 'moderate', 'severe') >= "
    "FIELD(cr.severity_min, 'mild', 'moderate', 'severe')"
)


def _cte_dieu_kien(dieu_kien: Sequence[DieuKien]) -> tuple[str, list[Any]]:
    """Dựng bảng dẫn xuất `dk(condition_id, severity)` từ danh sách Python.

    Dùng bảng dẫn xuất thay vì `IN (...)` để mức độ đi cùng được mã bệnh
    trong cùng một dòng — nhờ vậy mệnh đề `severity_min` so được từng cặp.
    """
    manh = " UNION ALL ".join(
        ["SELECT CAST(%s AS UNSIGNED) AS condition_id, CAST(%s AS CHAR) AS severity"]
        + ["SELECT %s, %s"] * (len(dieu_kien) - 1)
    )
    tham_so: list[Any] = []
    for dk in dieu_kien:
        tham_so += [dk.condition_id, dk.severity]
    return f"WITH dk AS ({manh})", tham_so


def loc_f1(
    cn,
    *,
    user_id: str | None = None,
    dieu_kien: Sequence[DieuKien] = (),
    chi_mon_chung: bool = False,
) -> list[dict[str, Any]]:
    """Trả về tập món **an toàn** cho người dùng, đã áp mọi ràng buộc cứng.

    `user_id` dùng cho hai việc khác nhau, đừng lẫn:

    · **phạm vi món** — `owner_id IS NULL OR owner_id = user_id`, tức là món
      danh mục chung cộng món riêng của chính người đó;
    · **tra điều kiện** — nếu `dieu_kien` để trống thì đọc từ
      `user_conditions`.

    `chi_mon_chung=True` bỏ hẳn món riêng. Đặt `True` khi dựng tập huấn luyện
    cho mô hình toàn cục: số liệu dinh dưỡng của món riêng do người dùng tự
    khai, nhiễm vào mô hình dùng chung là làm hại mọi người dùng khác.
    """
    if not dieu_kien and user_id is not None:
        dieu_kien = dieu_kien_cua_nguoi_dung(cn, user_id)

    pham_vi = (
        "f.owner_id IS NULL"
        if chi_mon_chung
        else "(f.owner_id IS NULL OR f.owner_id <=> %s)"
    )
    tham_so_pham_vi: list[Any] = [] if chi_mon_chung else [user_id]

    chon = """
SELECT f.id, f.name, f.category_id, f.dish_role, f.spice_level,
       f.popularity_score, f.owner_id
FROM foods f
WHERE f.is_active = 1
  AND {pham_vi}
"""

    if not dieu_kien:
        # Không có bệnh lý nào: F1 chỉ còn mệnh đề phạm vi. Tách nhánh vì
        # một bảng dẫn xuất rỗng là SQL không hợp lệ.
        sql = chon.format(pham_vi=pham_vi) + " ORDER BY f.name, f.id"
        with cn.cursor() as cur:
            cur.execute(sql, tuple(tham_so_pham_vi))
            return list(cur.fetchall())

    cte, tham_so_cte = _cte_dieu_kien(dieu_kien)

    than = (
        chon.format(pham_vi=pham_vi)
        + f"""
  -- (1) exclude_tag — loại món mang nhãn bị cấm
  AND NOT EXISTS (
        SELECT 1
        FROM condition_rules cr
        JOIN dk        ON dk.condition_id = cr.condition_id
        JOIN food_tags ft ON ft.tag_id = cr.tag_id
        WHERE cr.rule_type = 'exclude_tag'
          AND cr.is_hard = 1
          AND {_DU_MUC_DO}
          AND ft.food_id = f.id
      )

  -- (2) require_tag — món phải mang MỌI nhãn bắt buộc
  AND NOT EXISTS (
        SELECT 1
        FROM condition_rules cr
        JOIN dk ON dk.condition_id = cr.condition_id
        WHERE cr.rule_type = 'require_tag'
          AND cr.is_hard = 1
          AND {_DU_MUC_DO}
          AND NOT EXISTS (
                SELECT 1 FROM food_tags ft
                WHERE ft.food_id = f.id AND ft.tag_id = cr.tag_id
              )
      )

  -- (3) nutrient_limit cứng theo SUẤT. Thiếu số liệu thì LOẠI, vì không
  --     chứng minh được là an toàn — im lặng cho qua mới là nguy hiểm.
  AND NOT EXISTS (
        SELECT 1
        FROM condition_rules cr
        JOIN dk ON dk.condition_id = cr.condition_id
        JOIN food_nutrition fn ON fn.food_id = f.id
        WHERE cr.rule_type = 'nutrient_limit'
          AND cr.is_hard = 1
          AND cr.scope = 'per_serving'
          AND {_DU_MUC_DO}
          AND (
            {_CASE_CHAT} IS NULL
            OR (cr.comparator = 'lte' AND {_CASE_CHAT} > cr.threshold)
            OR (cr.comparator = 'gte' AND {_CASE_CHAT} < cr.threshold)
          )
      )
ORDER BY f.name, f.id
"""
    )

    with cn.cursor() as cur:
        cur.execute(cte + than, tuple(tham_so_cte + tham_so_pham_vi))
        return list(cur.fetchall())


# ── Ràng buộc mềm và hạn mức theo ngày ────────────────────────────────


def hinh_phat_mem(cn, dieu_kien: Sequence[DieuKien]) -> list[dict[str, Any]]:
    """Các quy tắc `is_hard = 0` đang áp, kèm `penalty`, để bước chấm điểm trừ.

    F1 **không** loại món theo các quy tắc này; nó chỉ trả chúng về. Giữ hai
    việc tách nhau là có chủ ý: loại món là quyết định về an toàn, trừ điểm
    là quyết định về sở thích, và trộn lẫn hai thứ thì không gỡ ra được khi
    phải giải thích vì sao một món bị bỏ.
    """
    if not dieu_kien:
        return []
    cte, tham_so = _cte_dieu_kien(dieu_kien)
    sql = (
        cte
        + f"""
SELECT co.name_vi, cr.rule_type, cr.tag_id, t.name_vi AS tag_name,
       cr.nutrient, cr.comparator, cr.threshold, cr.scope, cr.penalty,
       cr.severity_min, cr.evidence_level, cr.note
FROM condition_rules cr
JOIN dk         ON dk.condition_id = cr.condition_id
JOIN conditions co ON co.id = cr.condition_id
LEFT JOIN tags  t  ON t.id = cr.tag_id
WHERE cr.is_hard = 0
  AND {_DU_MUC_DO}
ORDER BY co.name_vi, cr.rule_type, cr.nutrient
"""
    )
    with cn.cursor() as cur:
        cur.execute(sql, tuple(tham_so))
        return list(cur.fetchall())


def han_muc_theo_ngay(
    cn,
    dieu_kien: Sequence[DieuKien],
    *,
    chi_cung: bool = True,
) -> list[dict[str, Any]]:
    """Ngưỡng dinh dưỡng **theo ngày** — đầu vào của Bước 4 pha 5.

    Không lọc món nào: một món mặn vẫn hợp lệ nếu tổng cả ngày vẫn dưới
    ngưỡng. Bản trước đặt ngưỡng cứng theo từng suất và ngưỡng natri 600 mg
    loại 58/60 món, khiến Bước 4 không dựng nổi thực đơn.

    `chi_cung=True` (mặc định, giữ nguyên hành vi cũ) chỉ trả ngưỡng cứng —
    thứ **chặn** món. `chi_cung=False` trả thêm ngưỡng mềm theo ngày, thứ
    chỉ **trừ điểm**. Hai loại phải phân biệt được ở phía gọi, nên mỗi dòng
    mang theo `is_hard` và `penalty`; gộp chúng lại sẽ biến một khuyến cáo
    thành một lệnh cấm.
    """
    if not dieu_kien:
        return []
    cte, tham_so = _cte_dieu_kien(dieu_kien)
    loc_cung = "  AND cr.is_hard = 1\n" if chi_cung else ""
    sql = (
        cte
        + f"""
SELECT co.name_vi, cr.nutrient, cr.comparator, cr.threshold,
       cr.is_hard, cr.penalty, cr.severity_min, cr.evidence_level, cr.note
FROM condition_rules cr
JOIN dk         ON dk.condition_id = cr.condition_id
JOIN conditions co ON co.id = cr.condition_id
WHERE cr.rule_type = 'nutrient_limit'
{loc_cung}  AND cr.scope = 'per_day'
  AND {_DU_MUC_DO}
ORDER BY cr.is_hard DESC, co.name_vi, cr.nutrient
"""
    )
    with cn.cursor() as cur:
        cur.execute(sql, tuple(tham_so))
        return list(cur.fetchall())


# ── Ràng buộc mềm, dạng có kiểu ────────────────────────────────────────
#
# `hinh_phat_mem` trả về dòng thô. Nó được giữ nguyên vì `main()` dùng, còn
# `LuatMem` là dạng mà bước chấm điểm nhận: có kiểu, có `scope` bắt buộc
# phải xét, và không cho một luật đi lạc phạm vi.


@dataclass(frozen=True)
class LuatMem:
    """Một ràng buộc mềm: vượt thì **trừ điểm**, không loại món."""

    benh: str
    severity_min: str
    nutrient: str
    comparator: str
    nguong: float
    #: **Hệ số nhân**, không phải lượng trừ. Xem `scoring.hinh_phat`.
    penalty: float
    scope: str
    note: str = ""
    evidence_level: str = "derived"

    @property
    def dan_duoc_nguon(self) -> bool:
        """Ngưỡng này có được dẫn như khuyến cáo có nguồn hay không."""
        return self.evidence_level in DAN_DUOC_NGUON

    @property
    def nhan_tin_cay(self) -> str:
        return NHAN_TIN_CAY.get(self.evidence_level, self.evidence_level)

    def vi_pham(self, gia_tri: float) -> bool:
        if self.comparator == "lte":
            return gia_tri > self.nguong
        return gia_tri < self.nguong

    @property
    def lech_bao_nhieu_tu(self) -> str:
        """Chiều của ngưỡng, để giao diện chọn chữ: `vượt` hay `thiếu`."""
        return "vượt" if self.comparator == "lte" else "thiếu"


def luat_mem(cn, dieu_kien: Sequence[DieuKien]) -> list[LuatMem]:
    """`hinh_phat_mem` ở dạng có kiểu, chỉ gồm quy tắc `nutrient_limit`.

    Bộ quy tắc hiện tại không có ràng buộc mềm nào dạng nhãn, nhưng lược đồ
    cho phép. Lọc ở đây thay vì để bước chấm điểm tự đoán: một luật nhãn mềm
    không có `nutrient` nên mọi phép so số với nó đều vô nghĩa.
    """
    ra: list[LuatMem] = []
    for d in hinh_phat_mem(cn, dieu_kien):
        if d["rule_type"] != "nutrient_limit" or d["nutrient"] is None:
            continue
        ra.append(
            LuatMem(
                benh=d["name_vi"],
                severity_min=d["severity_min"],
                nutrient=d["nutrient"],
                comparator=d["comparator"],
                nguong=float(d["threshold"]),
                penalty=float(d["penalty"]),
                scope=d["scope"],
                note=d["note"] or "",
                evidence_level=d["evidence_level"],
            )
        )
    return ra


#: Phạm vi nào đã có tầng thi hành, và tầng đó ở đâu.
#:
#: `per_meal` là `None` vì **chưa có ai thi hành**. Bộ quy tắc hiện có đúng
#: một luật như vậy — Đái tháo đường, bột đường ≤ 60 g mỗi bữa — và nó không
#: ảnh hưởng đến bất cứ thứ gì. Nêu ra thành dữ liệu để `luat_chua_thi_hanh`
#: báo được, thay vì để nó nằm im trong CSDL trông như đang hoạt động.
TANG_THI_HANH: dict[str, str | None] = {
    "per_serving": "ml/scoring.hinh_phat",
    "per_day": "ml/han_muc.trang_thai",
    "per_meal": None,
}


def luat_chua_thi_hanh(luat: Sequence[LuatMem]) -> list[LuatMem]:
    """Luật mềm thuộc phạm vi chưa có tầng nào thi hành.

    Danh sách này **không được phép** biến thành rỗng bằng cách xóa luật.
    Nó rỗng khi và chỉ khi Bước 4 nhận phần `per_meal`.
    """
    return [l for l in luat if TANG_THI_HANH.get(l.scope) is None]


def luat_mem_theo_pham_vi(
    luat: Sequence[LuatMem],
) -> dict[str, list[LuatMem]]:
    """Chia luật mềm theo `scope`, vì ba phạm vi cần ba lượng thông tin khác.

        per_serving — xét được từng món một, bước chấm điểm làm
        per_meal    — cần tổng cả bữa, thuộc Bước 4
        per_day     — cần tổng cả ngày, thuộc `ml/han_muc.py`

    Áp một luật `per_meal` cho từng món là sai cả hai chiều: nó bỏ sót
    trường hợp tổng bữa vượt dù không món nào vượt, và nó phạt oan một món
    lớn trong một bữa vẫn còn dư địa. Nên hàm chia ra để mỗi tầng chỉ nhận
    phần nó xét được, và `chua_thi_hanh` nói thẳng phần nào chưa có ai nhận.
    """
    ra: dict[str, list[LuatMem]] = {
        "per_serving": [],
        "per_meal": [],
        "per_day": [],
    }
    for l in luat:
        ra.setdefault(l.scope, []).append(l)
    return ra


# ── Nghịch đảo của F1: vì sao một món bị loại ─────────────────────────
#
# `loc_f1` trả về tập món còn lại. Giao diện cần điều ngược lại — món nào bị
# bỏ và vì luật nào — và câu trả lời đó KHÔNG suy ra được từ tập còn lại:
# lấy phần bù chỉ cho biết món nào bị bỏ, không cho biết tại sao.
#
# Hai hàm dưới đây dựng đúng ba mệnh đề `NOT EXISTS` của `loc_f1` thành ba
# nhánh `UNION ALL` đọc cùng một bộ quy tắc. Nguy cơ rõ ràng là hai bên lệch
# nhau sau một lần sửa, và khi đó giao diện sẽ nói một món vừa an toàn vừa
# bị loại. `doi_chieu_loc_f1` tồn tại để bắt đúng tình huống đó.


@dataclass(frozen=True)
class LyDoLoai:
    """Một luật cứng mà một món vi phạm."""

    food_id: str
    name: str
    dish_role: str
    rule_type: str
    benh: str
    severity_min: str
    the: str | None = None
    nutrient: str | None = None
    comparator: str | None = None
    nguong: float | None = None
    #: Số đo của món. `None` nghĩa là **thiếu số liệu**, không phải bằng 0.
    gia_tri: float | None = None
    note: str = ""
    evidence_level: str = "derived"

    @property
    def dan_duoc_nguon(self) -> bool:
        """Ngưỡng này có được dẫn như khuyến cáo có nguồn hay không."""
        return self.evidence_level in DAN_DUOC_NGUON

    @property
    def nhan_tin_cay(self) -> str:
        return NHAN_TIN_CAY.get(self.evidence_level, self.evidence_level)


    @property
    def thieu_so_lieu(self) -> bool:
        """Món bị loại vì không có số liệu, chứ không vì vượt ngưỡng.

        `loc_f1` loại món thiếu số liệu ở ngưỡng theo suất — không chứng minh
        được là an toàn thì không cho qua. Đó là lựa chọn đúng cho một tầng
        an toàn, nhưng nói với người dùng "món này vượt ngưỡng" khi thật ra
        là "chúng tôi không biết" thì sai sự thật, nên hai thứ phải tách ra.

        Lưu ý chiều ngược với `ml/han_muc.py`: ngưỡng theo SUẤT thiếu số liệu
        thì LOẠI, còn hạn mức theo NGÀY thiếu số liệu thì CỘNG 0 kèm cờ báo.
        Hai lựa chọn trái nhau nhưng cùng một lý do: theo suất, câu hỏi là
        "món này có an toàn không" nên không biết là không cho qua; theo ngày,
        chặn khi không biết sẽ loại 248/318 món và hệ thống thành vô dụng.
        """
        return self.rule_type == "nutrient_limit" and self.gia_tri is None

    @property
    def bac(self) -> str:
        """Bậc lý do, để giao diện nhóm lại.

        · `nhan`          — món mang nhãn bị cấm, hoặc thiếu nhãn bắt buộc
        · `nguong_suat`   — số đo mỗi suất vượt ngưỡng cứng
        · `thieu_so_lieu` — không có số liệu nên không cho qua
        """
        if self.rule_type in ("exclude_tag", "require_tag"):
            return "nhan"
        return "thieu_so_lieu" if self.thieu_so_lieu else "nguong_suat"

    @property
    def vuot_bao_nhieu(self) -> float | None:
        """Vượt ngưỡng bao nhiêu. `None` khi không tính được."""
        if self.gia_tri is None or self.nguong is None:
            return None
        if self.comparator == "lte":
            return self.gia_tri - self.nguong
        return self.nguong - self.gia_tri


_CHON_LY_DO = """
SELECT f.id AS food_id, f.name, f.dish_role,
       {loai} AS rule_type,
       co.name_vi AS benh, cr.severity_min,
       {the} AS the,
       {nutrient} AS nutrient, {comparator} AS comparator,
       {nguong} AS nguong, {gia_tri} AS gia_tri,
       cr.evidence_level, cr.note
"""


def ly_do_loai(
    cn,
    *,
    user_id: str | None = None,
    dieu_kien: Sequence[DieuKien] = (),
    chi_mon_chung: bool = False,
) -> dict[str, list[LyDoLoai]]:
    """Món nào bị F1 loại, và vì luật nào.

    Tham số giống `loc_f1` và phải được truyền giống nhau — cùng `user_id`,
    cùng `dieu_kien`, cùng `chi_mon_chung` — nếu không thì hai bên đang nói
    về hai tập món khác nhau.

    Trả về `{food_id: [lý do...]}`. Một món có thể vi phạm nhiều luật, và
    mọi luật bị vi phạm đều được nêu: biết một lý do không đủ để người dùng
    hiểu, vì sửa được một luật chưa chắc món đó hợp.
    """
    if not dieu_kien and user_id is not None:
        dieu_kien = dieu_kien_cua_nguoi_dung(cn, user_id)
    if not dieu_kien:
        # Không bệnh lý nào thì F1 không loại món nào.
        return {}

    pham_vi = (
        "f.owner_id IS NULL"
        if chi_mon_chung
        else "(f.owner_id IS NULL OR f.owner_id <=> %s)"
    )
    mot_pham_vi: list[Any] = [] if chi_mon_chung else [user_id]

    nhanh_the = (
        _CHON_LY_DO.format(
            loai="'exclude_tag'",
            the="t.name_vi",
            nutrient="NULL",
            comparator="NULL",
            nguong="NULL",
            gia_tri="NULL",
        )
        + f"""
FROM foods f
JOIN food_tags       ft ON ft.food_id = f.id
JOIN condition_rules cr ON cr.tag_id = ft.tag_id
                       AND cr.rule_type = 'exclude_tag'
                       AND cr.is_hard = 1
JOIN dk                 ON dk.condition_id = cr.condition_id
JOIN conditions      co ON co.id = cr.condition_id
JOIN tags            t  ON t.id = cr.tag_id
WHERE f.is_active = 1
  AND {pham_vi}
  AND {_DU_MUC_DO}
"""
    )

    nhanh_bat_buoc = (
        _CHON_LY_DO.format(
            loai="'require_tag'",
            the="t.name_vi",
            nutrient="NULL",
            comparator="NULL",
            nguong="NULL",
            gia_tri="NULL",
        )
        + f"""
FROM foods f
JOIN condition_rules cr ON cr.rule_type = 'require_tag' AND cr.is_hard = 1
JOIN dk                 ON dk.condition_id = cr.condition_id
JOIN conditions      co ON co.id = cr.condition_id
JOIN tags            t  ON t.id = cr.tag_id
WHERE f.is_active = 1
  AND {pham_vi}
  AND {_DU_MUC_DO}
  AND NOT EXISTS (
        SELECT 1 FROM food_tags ft
        WHERE ft.food_id = f.id AND ft.tag_id = cr.tag_id
      )
"""
    )

    nhanh_nguong = (
        _CHON_LY_DO.format(
            loai="'nutrient_limit'",
            the="NULL",
            nutrient="cr.nutrient",
            comparator="cr.comparator",
            nguong="cr.threshold",
            gia_tri=_CASE_CHAT,
        )
        + f"""
FROM foods f
JOIN food_nutrition  fn ON fn.food_id = f.id
JOIN condition_rules cr ON cr.rule_type = 'nutrient_limit'
                       AND cr.is_hard = 1
                       AND cr.scope = 'per_serving'
JOIN dk                 ON dk.condition_id = cr.condition_id
JOIN conditions      co ON co.id = cr.condition_id
WHERE f.is_active = 1
  AND {pham_vi}
  AND {_DU_MUC_DO}
  AND (
        {_CASE_CHAT} IS NULL
        OR (cr.comparator = 'lte' AND {_CASE_CHAT} > cr.threshold)
        OR (cr.comparator = 'gte' AND {_CASE_CHAT} < cr.threshold)
      )
"""
    )

    cte, tham_so_cte = _cte_dieu_kien(dieu_kien)
    sql = (
        cte
        + nhanh_the
        + "UNION ALL"
        + nhanh_bat_buoc
        + "UNION ALL"
        + nhanh_nguong
        + "ORDER BY name, food_id, rule_type"
    )
    tham_so = tham_so_cte + mot_pham_vi + mot_pham_vi + mot_pham_vi

    with cn.cursor() as cur:
        cur.execute(sql, tuple(tham_so))
        dong = list(cur.fetchall())

    ket_qua: dict[str, list[LyDoLoai]] = {}
    for d in dong:
        ket_qua.setdefault(d["food_id"], []).append(
            LyDoLoai(
                food_id=d["food_id"],
                name=d["name"],
                dish_role=d["dish_role"],
                rule_type=d["rule_type"],
                benh=d["benh"],
                severity_min=d["severity_min"],
                the=d["the"],
                nutrient=d["nutrient"],
                comparator=d["comparator"],
                nguong=None if d["nguong"] is None else float(d["nguong"]),
                gia_tri=None if d["gia_tri"] is None else float(d["gia_tri"]),
                note=d["note"] or "",
                evidence_level=d["evidence_level"],
            )
        )
    return ket_qua


def doi_chieu_loc_f1(
    cn,
    *,
    user_id: str | None = None,
    dieu_kien: Sequence[DieuKien] = (),
    chi_mon_chung: bool = False,
) -> dict[str, list[str]]:
    """Soát `ly_do_loai` khớp `loc_f1` — hai câu SQL, một bộ quy tắc.

    `loc_f1` và `ly_do_loai` đọc cùng `condition_rules` nhưng bằng hai câu
    SQL viết tay khác nhau. Sửa một bên mà quên bên kia thì giao diện sẽ hiện
    một món vừa nằm trong thực đơn vừa nằm trong danh sách bị loại, và không
    có gì báo. Hàm này so hai tập:

        · `thieu_ly_do` — bị `loc_f1` bỏ nhưng `ly_do_loai` không giải thích
          được. Người dùng thấy món biến mất mà không có lý do nào.
        · `ly_do_du`    — có lý do bị loại nhưng `loc_f1` vẫn cho qua. Hướng
          này tệ hơn: một món bị coi là vi phạm vẫn vào được thực đơn.

    Hai danh sách rỗng nghĩa là hai bên đang khớp.
    """
    con_lai = {
        m["id"]
        for m in loc_f1(
            cn,
            user_id=user_id,
            dieu_kien=dieu_kien,
            chi_mon_chung=chi_mon_chung,
        )
    }
    co_ly_do = set(
        ly_do_loai(
            cn,
            user_id=user_id,
            dieu_kien=dieu_kien,
            chi_mon_chung=chi_mon_chung,
        )
    )

    pham_vi = (
        "f.owner_id IS NULL"
        if chi_mon_chung
        else "(f.owner_id IS NULL OR f.owner_id <=> %s)"
    )
    with cn.cursor() as cur:
        cur.execute(
            f"SELECT f.id FROM foods f WHERE f.is_active = 1 AND {pham_vi}",
            () if chi_mon_chung else (user_id,),
        )
        tat_ca = {d["id"] for d in cur.fetchall()}

    return {
        "thieu_ly_do": sorted((tat_ca - con_lai) - co_ly_do),
        "ly_do_du": sorted(co_ly_do & con_lai),
    }


# ── Chạy thử ──────────────────────────────────────────────────────────


def _dem_theo_vai(mon: Iterable[dict[str, Any]]) -> dict[str, int]:
    dem: dict[str, int] = {}
    for m in mon:
        dem[m["dish_role"]] = dem.get(m["dish_role"], 0) + 1
    return dem


def main() -> int:
    """Chạy vài tình huống, trong đó có hai tình huống chỉ khác nhau mức độ."""
    from .db import in_utf8, ket_noi

    in_utf8()
    cn = ket_noi()
    try:
        tat_ca = loc_f1(cn)
        print(f"Không bệnh gì: {len(tat_ca)} món")

        tinh_huong = [
            ("Tăng huyết áp", ["Tăng huyết áp"]),
            ("Gút + dị ứng hải sản", ["Gút", "Dị ứng hải sản"]),
            ("Ăn chay + dị ứng đậu nành", ["Ăn chay", "Dị ứng đậu nành"]),
        ]
        for ten, ds in tinh_huong:
            for muc in ("mild", "severe"):
                dk = dieu_kien_theo_ten(cn, ds, muc)
                mon = loc_f1(cn, dieu_kien=dk)
                vai = _dem_theo_vai(mon)
                print(
                    f"{ten:28} [{muc:7}] {len(mon):3} món  "
                    + " ".join(f"{k}={v}" for k, v in sorted(vai.items()))
                )

            mem = hinh_phat_mem(cn, dieu_kien_theo_ten(cn, ds, "severe"))
            ngay = han_muc_theo_ngay(cn, dieu_kien_theo_ten(cn, ds, "severe"))
            if mem:
                print(
                    "    mềm:   "
                    + "; ".join(
                        f"{r['name_vi']}/{r['rule_type']}"
                        f"{'/' + r['nutrient'] if r['nutrient'] else ''}"
                        f" −{r['penalty']}"
                        for r in mem
                    )
                )
            if ngay:
                print(
                    "    theo ngày: "
                    + "; ".join(
                        f"{r['name_vi']}/{r['nutrient']} "
                        f"{r['comparator']} {r['threshold']:g}"
                        for r in ngay
                    )
                )
    finally:
        cn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
