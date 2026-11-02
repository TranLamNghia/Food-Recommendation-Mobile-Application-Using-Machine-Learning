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
       cr.nutrient, cr.comparator, cr.threshold, cr.scope, cr.penalty, cr.note
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


def han_muc_theo_ngay(cn, dieu_kien: Sequence[DieuKien]) -> list[dict[str, Any]]:
    """Ngưỡng dinh dưỡng **cứng theo ngày** — đầu vào của Bước 4 pha 5.

    Không lọc món nào: một món mặn vẫn hợp lệ nếu tổng cả ngày vẫn dưới
    ngưỡng. Bản trước đặt ngưỡng cứng theo từng suất và ngưỡng natri 600 mg
    loại 58/60 món, khiến Bước 4 không dựng nổi thực đơn.
    """
    if not dieu_kien:
        return []
    cte, tham_so = _cte_dieu_kien(dieu_kien)
    sql = (
        cte
        + f"""
SELECT co.name_vi, cr.nutrient, cr.comparator, cr.threshold, cr.note
FROM condition_rules cr
JOIN dk         ON dk.condition_id = cr.condition_id
JOIN conditions co ON co.id = cr.condition_id
WHERE cr.rule_type = 'nutrient_limit'
  AND cr.is_hard = 1
  AND cr.scope = 'per_day'
  AND {_DU_MUC_DO}
ORDER BY co.name_vi, cr.nutrient
"""
    )
    with cn.cursor() as cur:
        cur.execute(sql, tuple(tham_so))
        return list(cur.fetchall())


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
