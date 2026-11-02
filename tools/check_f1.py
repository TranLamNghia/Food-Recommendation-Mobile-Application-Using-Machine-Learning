#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chạy Bộ lọc F1 **thuần bằng SQL** để chứng minh lược đồ đã đủ.

Vì sao có tệp này. Bộ lọc F1 — bước loại món không an toàn theo bệnh lý, dị
ứng và chế độ ăn — hiện **chưa có dòng mã nào** trong ứng dụng. Câu hỏi cần
trả lời trước khi chốt ERD không phải "đã viết chưa" mà là:

    Lược đồ hiện tại có đủ để biểu diễn F1, hay còn phải thêm bảng/cột?

Tệp này trả lời bằng cách **chạy thật**: dựng F1 hoàn toàn bằng SQL trên
`conditions`, `user_conditions`, `condition_rules`, `tags`, `food_tags`,
`foods` — không thêm bảng nào, không xử lý gì ở tầng ứng dụng. Nếu nó chạy ra
kết quả đúng thì phần còn lại chỉ là dịch truy vấn này sang Dart hoặc sang
tầng API, và ERD không phải chờ.

Ba loại quy tắc trong `condition_rules`:

    exclude_tag     loại mọi món mang nhãn đó          → lọc được ở cấp MÓN
    require_tag     chỉ giữ món mang nhãn đó           → lọc được ở cấp MÓN
    nutrient_limit  ngưỡng số                          → xem bên dưới

`nutrient_limit` **cứng** đều có `scope = 'per_day'`, nên nó KHÔNG lọc món
nào ở cấp ứng viên — một món mặn vẫn hợp lệ nếu cả ngày vẫn dưới ngưỡng. Đó
là chủ ý: bản trước đặt ngưỡng cứng theo từng suất và ngưỡng natri 600 mg
loại 58/60 món, khiến Bước 4 không dựng nổi thực đơn. Phần theo ngày do Bước 4
pha 5 thi hành, không phải F1.

Chạy:
    python tools/check_f1.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

# ── Bộ lọc F1, viết một lần bằng SQL ──────────────────────────────────
#
# Tham số duy nhất là danh sách id bệnh lý của người dùng. Trong hệ thống
# thật nó lấy từ `user_conditions WHERE user_id = ?`; ở đây truyền trực tiếp
# để thử được mọi tổ hợp mà không cần tạo người dùng giả.
#
# `owner_id IS NULL OR owner_id = ?` là phần phạm vi món: món danh mục chung
# cộng món riêng của chính người đó. Chỉ mục `idx_active_category` đặt
# `owner_id` đứng đầu đúng vì mệnh đề này.
F1_SQL = """
SELECT f.id, f.name
FROM foods f
WHERE f.is_active = 1
  AND (f.owner_id IS NULL OR f.owner_id = %(user_id)s)

  -- (1) exclude_tag — loại món mang nhãn bị cấm
  AND NOT EXISTS (
        SELECT 1
        FROM condition_rules cr
        JOIN food_tags ft ON ft.tag_id = cr.tag_id
        WHERE cr.rule_type = 'exclude_tag'
          AND cr.is_hard = 1
          AND cr.condition_id IN ({conds})
          AND ft.food_id = f.id
      )

  -- (2) require_tag — món phải mang MỌI nhãn bắt buộc
  AND NOT EXISTS (
        SELECT 1
        FROM condition_rules cr
        WHERE cr.rule_type = 'require_tag'
          AND cr.is_hard = 1
          AND cr.condition_id IN ({conds})
          AND NOT EXISTS (
                SELECT 1 FROM food_tags ft
                WHERE ft.food_id = f.id AND ft.tag_id = cr.tag_id
              )
      )

  -- (3) nutrient_limit cứng theo SUẤT — hiện không có dòng nào, giữ mệnh đề
  --     để lược đồ vẫn đúng nếu sau này thêm. Thiếu số liệu thì LOẠI, vì
  --     không chứng minh được là an toàn.
  AND NOT EXISTS (
        SELECT 1
        FROM condition_rules cr
        JOIN food_nutrition fn ON fn.food_id = f.id
        WHERE cr.rule_type = 'nutrient_limit'
          AND cr.is_hard = 1
          AND cr.scope = 'per_serving'
          AND cr.condition_id IN ({conds})
          AND (
            CASE cr.nutrient
              WHEN 'sodium_mg'      THEN fn.sodium_mg
              WHEN 'sugar_g'        THEN fn.sugar_g
              WHEN 'purine_mg'      THEN fn.purine_mg
              WHEN 'protein_g'      THEN fn.protein_g
              WHEN 'fat_g'          THEN fn.fat_g
              WHEN 'carbs_g'        THEN fn.carbs_g
              WHEN 'cholesterol_mg' THEN fn.cholesterol_mg
              WHEN 'fiber_g'        THEN fn.fiber_g
              WHEN 'calories_kcal'  THEN fn.calories_kcal
            END IS NULL
            OR (cr.comparator = 'lte' AND
                CASE cr.nutrient
                  WHEN 'sodium_mg'      THEN fn.sodium_mg
                  WHEN 'sugar_g'        THEN fn.sugar_g
                  WHEN 'purine_mg'      THEN fn.purine_mg
                  WHEN 'protein_g'      THEN fn.protein_g
                  WHEN 'fat_g'          THEN fn.fat_g
                  WHEN 'carbs_g'        THEN fn.carbs_g
                  WHEN 'cholesterol_mg' THEN fn.cholesterol_mg
                  WHEN 'fiber_g'        THEN fn.fiber_g
                  WHEN 'calories_kcal'  THEN fn.calories_kcal
                END > cr.threshold)
          )
      )
"""

# Ngưỡng CỨNG theo NGÀY — không lọc món, Bước 4 pha 5 thi hành.
PER_DAY_SQL = """
SELECT co.name_vi, cr.nutrient, cr.comparator, cr.threshold
FROM condition_rules cr
JOIN conditions co ON co.id = cr.condition_id
WHERE cr.rule_type = 'nutrient_limit'
  AND cr.is_hard = 1
  AND cr.scope = 'per_day'
  AND cr.condition_id IN ({conds})
ORDER BY co.name_vi, cr.nutrient
"""

# Mục tiêu người dùng tự khai — tra theo giới tính và tuổi.
RDA_SQL = """
SELECT nutrient, rda_value, unit, source
FROM rda_reference
WHERE nutrient = %(nutrient)s
  AND gender IN ('all', %(gender)s)
  AND %(age)s BETWEEN age_min AND age_max
"""

# Những tổ hợp đáng thử. Tên lấy đúng `conditions.name_vi`.
SCENARIOS = [
    ("Không bệnh gì", []),
    ("Tăng huyết áp", ["Tăng huyết áp"]),
    ("Gút", ["Gút"]),
    ("Bệnh thận", ["Bệnh thận"]),
    ("Đái tháo đường", ["Đái tháo đường"]),
    ("Rối loạn mỡ máu", ["Rối loạn mỡ máu"]),
    ("Dị ứng hải sản", ["Dị ứng hải sản"]),
    ("Dị ứng đậu phộng", ["Dị ứng đậu phộng"]),
    ("Ăn chay", ["Ăn chay"]),
    ("Ăn thuần chay", ["Ăn thuần chay"]),
    # Tổ hợp — chỗ dễ vỡ nhất, vì các quy tắc giao nhau.
    ("Gút + dị ứng hải sản", ["Gút", "Dị ứng hải sản"]),
    ("Ăn chay + dị ứng trứng", ["Ăn chay", "Dị ứng trứng"]),
    (
        "Thuần chay + gút + tăng huyết áp",
        ["Ăn thuần chay", "Gút", "Tăng huyết áp"],
    ),
    (
        "Bốn bệnh chuyển hóa cùng lúc",
        ["Tăng huyết áp", "Đái tháo đường", "Gút", "Rối loạn mỡ máu"],
    ),
    # Ca biên khó nhất: đậu phụ và nước tương đều LÀ đậu nành, nên nếu mọi
    # món chay đều dựa vào chúng thì tổ hợp này về 0 món mặn và 0 món canh.
    # Danh mục có sẵn món chay nêm muối và lấy đạm từ nấm đúng vì ca này.
    ("Ăn chay + dị ứng đậu nành", ["Ăn chay", "Dị ứng đậu nành"]),
    (
        "Thuần chay + dị ứng đậu nành + tăng huyết áp",
        ["Ăn thuần chay", "Dị ứng đậu nành", "Tăng huyết áp"],
    ),
    ("Dị ứng đậu nành", ["Dị ứng đậu nành"]),
]

# Số món tối thiểu mỗi vai trò để Bước 4 dựng nổi một ngày.
ROLES_NEEDED = {
    "main": 3,
    "side_protein": 2,
    "side_veg": 3,
    "soup": 2,
    "dessert": 1,
    "drink": 1,
}


def main() -> int:
    try:
        import pymysql
    except ImportError:
        sys.exit("Cần cài pymysql:  pip install pymysql")

    conn = pymysql.connect(
        host=_env.get("MYSQL_HOST", "localhost"),
        port=int(_env.get("MYSQL_PORT", "3306")),
        user=_env.require("MYSQL_USER"),
        password=_env.require("MYSQL_PASSWORD"),
        database=_env.require("MYSQL_DATABASE"),
        charset="utf8mb4",
    )

    problems: list[str] = []

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name_vi FROM conditions")
            by_name = {name: cid for cid, name in cur.fetchall()}

            cur.execute("SELECT COUNT(*) FROM foods WHERE is_active = 1")
            total = cur.fetchone()[0]

            print("═" * 78)
            print("BỘ LỌC F1 CHẠY THUẦN BẰNG SQL")
            print(f"Danh mục: {total} món đang hoạt động")
            print("═" * 78)

            print(f"\n{'Tình huống':<36}{'ứng viên':>10}{'%':>7}"
                  f"{'đủ vai trò':>13}")
            print("─" * 78)

            for label, names in SCENARIOS:
                missing_name = [n for n in names if n not in by_name]
                if missing_name:
                    problems.append(
                        f"{label}: không có bệnh {missing_name} trong bảng "
                        f"`conditions`"
                    )
                    continue

                ids = [by_name[n] for n in names]
                # IN () rỗng là lỗi cú pháp; dùng NULL để mệnh đề luôn sai.
                conds = ", ".join(str(i) for i in ids) if ids else "NULL"

                cur.execute(
                    F1_SQL.format(conds=conds), {"user_id": None}
                )
                kept = cur.fetchall()

                # Đếm theo vai trò để biết Bước 4 còn dựng nổi bữa không.
                if kept:
                    # `foods.id` là chuỗi UUID, không phải số, nên không nối
                    # thẳng vào câu lệnh được — thiếu dấu nháy là lỗi cú pháp
                    # ngay. Truyền qua tham số, cũng đúng cách hơn.
                    kept_ids = [r[0] for r in kept]
                    cho = ", ".join(["%s"] * len(kept_ids))
                    cur.execute(
                        f"SELECT dish_role, COUNT(*) FROM foods "
                        f"WHERE id IN ({cho}) GROUP BY dish_role",
                        kept_ids,
                    )
                    per_role = dict(cur.fetchall())
                else:
                    per_role = {}

                short = [
                    f"{role} {per_role.get(role, 0)}/{need}"
                    for role, need in ROLES_NEEDED.items()
                    if per_role.get(role, 0) < need
                ]
                mark = "✓" if not short else "✗"
                print(
                    f"{label:<36}{len(kept):>8}{len(kept) / total * 100:>8.0f}%"
                    f"{mark:>9}  {', '.join(short)}"
                )
                if short:
                    problems.append(
                        f"{label}: thiếu món ở vai trò {', '.join(short)} — "
                        f"Bước 4 không dựng nổi một ngày"
                    )

            # ── Ngưỡng theo ngày: không lọc món, nhưng phải tra được ──
            print("\n" + "─" * 78)
            print("Ngưỡng CỨNG theo NGÀY — F1 không lọc, Bước 4 pha 5 thi hành")
            print("─" * 78)
            everything = ", ".join(str(i) for i in by_name.values())
            cur.execute(PER_DAY_SQL.format(conds=everything))
            rows = cur.fetchall()
            for name, nutrient, comparator, threshold in rows:
                sign = "≤" if comparator == "lte" else "≥"
                print(f"   {name:<20}{nutrient:<16}{sign} {threshold}")
            if not rows:
                problems.append(
                    "không tra được ngưỡng cứng theo ngày nào — "
                    "`condition_rules` trống?"
                )

            # ── Mục tiêu tự khai: tra được từ rda_reference ──
            print("\n" + "─" * 78)
            print("Mục tiêu tự khai tra từ `rda_reference`")
            print("─" * 78)
            for gender, age in (("male", 24), ("female", 24), ("male", 8)):
                cur.execute(
                    RDA_SQL,
                    {"nutrient": "fiber_g", "gender": gender, "age": age},
                )
                found = cur.fetchall()
                if not found:
                    problems.append(
                        f"không tra được nhu cầu chất xơ cho {gender} {age} "
                        f"tuổi"
                    )
                    print(f"   ✗ {gender} {age} tuổi: không có dòng nào")
                    continue
                nutrient, value, unit, source = found[0]
                print(
                    f"   ✓ {gender} {age} tuổi: {nutrient} ≥ {value} {unit}"
                    f"   ({source})"
                )
    finally:
        conn.close()

    print("\n" + "═" * 78)
    if problems:
        print(f"{len(problems)} vấn đề:\n")
        for p in problems:
            print(f"  ✗ {p}")
    else:
        print("F1 BIỂU DIỄN ĐƯỢC HOÀN TOÀN BẰNG LƯỢC ĐỒ HIỆN TẠI.")
        print("Không thiếu bảng, không thiếu cột. Phần còn lại là dịch truy")
        print("vấn này sang tầng ứng dụng.")
    print("═" * 78)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
