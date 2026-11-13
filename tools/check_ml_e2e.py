#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm đầu-cuối phần học máy — tự dựng CSDL riêng, tự xóa khi xong.

`tools/check_ml.py` kiểm các hàm thuần mà không cần CSDL. Tệp này kiểm phần
còn lại: bốn script đọc ghi CSDL, chạy nối tiếp nhau đúng như khi làm thật.

    build_dataset  →  train  →  evaluate  →  serve

Vì sao phải tự dựng CSDL. Bảy nguồn tín hiệu trong `nutrition_rec` đều **đang
trống** — chưa có người dùng thật nào. Nên không có cách nào kiểm bốn script
này trên CSDL thật, và viết tín hiệu giả vào CSDL thật thì làm bẩn đúng cái
mình phải giữ sạch. Tệp này tạo một CSDL riêng, sao **dữ liệu món thật** sang
(để vector đặc trưng vẫn là vector thật), dựng người dùng giả ở đó, chạy hết
rồi xóa CSDL đi.

**Nhãn được gắn ngẫu nhiên, và đó là chủ ý.** Không phải vì tiện, mà vì nó
tạo ra một **chốt canh rò rỉ dữ liệu**: nếu đường ống không rò rỉ thì mô hình
buộc phải cho kết quả quanh mức tình cờ. Một con số đẹp ở đây là bằng chứng
có rò rỉ, không phải tin tốt. Sinh hồ sơ giả với khẩu vị đã biết rồi cho
chúng "vuốt" theo khẩu vị đó thì mô hình sẽ học lại đúng quy luật mình vừa
bịa ra, và chốt canh này mất tác dụng.

Mọi con số in ra đây **không phải kết quả thực nghiệm** và không được đưa vào
báo cáo. Chúng chỉ chứng minh đường ống chạy đúng.

Chạy:
    python tools/check_ml_e2e.py
    python tools/check_ml_e2e.py --giu     # giữ CSDL lại để xem bằng tay
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402

from ml.build_dataset import main as chay_dung_tap  # noqa: E402
from ml.db import connect, use_utf8  # noqa: E402
from ml.evaluate import main as chay_danh_gia  # noqa: E402
from ml.f1_filter import (  # noqa: E402
    conditions_for_user,
    conditions_by_name,
    cross_check_f1,
    allowed_foods,
    unenforced_rules,
    soft_rules,
    soft_rules_by_scope,
    exclusion_reasons,
)
from ml.scoring import penalty  # noqa: E402
from ml.daily_limits import (  # noqa: E402
    eaten_totals,
    planned_totals,
    check_double_counting,
    classify_foods,
    status,
)
from ml.features import FEATURE_VERSION, FeatureSpace, load_foods  # noqa: E402
from ml.rocchio import alpha, build_profile, stage  # noqa: E402
from ml.serve import recommend, load_active_model  # noqa: E402
from ml.train import main as chay_huan_luyen  # noqa: E402
from tools.make_survey_deck import chon_bo_mon  # noqa: E402
from tools.update_popularity import main as _cap_nhat_pho_bien  # noqa: E402


def chay_nhap_phieu(argv: list[str]) -> int:
    """`import_swipes.main` đọc `sys.argv`, nên phải thay tạm."""
    from tools.import_swipes import main as _nhap

    cu = sys.argv
    sys.argv = ["import_swipes.py", *argv]
    try:
        return _nhap()
    finally:
        sys.argv = cu


def chay_cap_nhat_pho_bien(argv: list[str]) -> int:
    """`update_popularity.main` đọc `sys.argv`, nên phải thay tạm."""
    cu = sys.argv
    sys.argv = ["update_popularity.py", *argv]
    try:
        return _cap_nhat_pho_bien()
    finally:
        sys.argv = cu

TEN_CSDL_THU = "zz_kiem_ml"
SES = "33333333-3333-3333-3333-333333333333"

#: Các bảng tham chiếu được sao từ CSDL thật, theo thứ tự an toàn khóa ngoại.
BANG_THAM_CHIEU = (
    "food_categories",
    "tags",
    "conditions",
    "condition_rules",
    "rda_reference",
    "foods",
    "food_nutrition",
    "food_tags",
)

#: Số lượt vuốt của từng người, chọn để phủ **cả bốn giai đoạn**.
#: `stage`: 0 → cold, 1–29 → content, 30–100 → hybrid, >100 → ml.
SO_VUOT = [0, 12, 12, 18, 45, 45, 60, 60, 120, 150, 25, 25]

_dat = 0
_loi: list[str] = []


def kiem(conditions: bool, mo_ta: str) -> None:
    global _dat
    if conditions:
        _dat += 1
        print(f"  ✓ {mo_ta}")
    else:
        _loi.append(mo_ta)
        print(f"  ✗ {mo_ta}")


#: Sai số khi so hai tổng dinh dưỡng. `food_nutrition` là `DECIMAL`, khẩu
#: phần là `DECIMAL(4,2)`, nên tổng do MySQL cộng và tổng do Python cộng có
#: thể lệch ở chữ số cuối — nhưng chỉ ở đó.
SAI_SO_TONG = 1e-6


def gan(thuc_te: float, mong_doi: float, mo_ta: str) -> None:
    kiem(
        abs(thuc_te - mong_doi) < SAI_SO_TONG,
        f"{mo_ta}: được {thuc_te:.4f}, mong đợi {mong_doi:.4f}",
    )


# ── Dựng CSDL thử ─────────────────────────────────────────────────────


def _cot_ghi_duoc(cn, db: str, bang: str) -> list[str]:
    """Các cột ghi được — bỏ **cột sinh**, vì `INSERT` vào chúng là lỗi 3105.

    Lọc theo `GENERATION_EXPRESSION`, không lọc theo `EXTRA`. Cách đầu tiên
    tôi viết là `EXTRA NOT LIKE '%GENERATED%'`, và nó sai một cách rất khó
    thấy: MySQL 8 đánh dấu **mọi** cột có mặc định dạng biểu thức là
    `DEFAULT_GENERATED`, nên `id CHAR(36) DEFAULT (UUID())` và
    `created_at DATETIME DEFAULT CURRENT_TIMESTAMP` cũng bị loại.

    Hậu quả không phải một lỗi SQL mà là **dữ liệu sai trong im lặng**: bản
    sao vẫn chèn đủ dòng, nhưng mỗi dòng nhận một `UUID()` mới, nên
    `foods.category_id` trỏ tới những `food_categories.id` không còn tồn tại.
    Phép `JOIN` sau đó trả về 0 dòng, và dấu hiệu duy nhất là "tập món rỗng".
    """
    with cn.cursor() as cur:
        cur.execute(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
            "  AND (GENERATION_EXPRESSION IS NULL "
            "       OR GENERATION_EXPRESSION = '') "
            "ORDER BY ORDINAL_POSITION",
            (db, bang),
        )
        return [d["COLUMN_NAME"] for d in cur.fetchall()]


def dung_csdl_thu(goc: str, thu: str) -> None:
    """Sao lược đồ của toàn bộ bảng + dữ liệu của các bảng tham chiếu.

    `CREATE TABLE ... LIKE` sao đủ cột sinh, khóa và chỉ mục, nên lược đồ thử
    giống lược đồ thật từng chi tiết — kể cả `uq_sample` và `uq_eval`, hai
    khóa mà bài kiểm này cần để chứng minh chạy lại không nhân đôi dữ liệu.
    """
    cn = connect(goc, dict_cursor=True)
    try:
        with cn.cursor() as cur:
            cur.execute(
                "SELECT TABLE_NAME FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'",
                (goc,),
            )
            tat_ca = {d["TABLE_NAME"] for d in cur.fetchall()}

        # Thứ tự tạo bảng: khóa ngoại trỏ tới bảng chưa tồn tại thì lỗi 1215.
        # Tắt kiểm khóa ngoại trong lúc dựng rồi bật lại — rẻ hơn nhiều so với
        # sắp xếp topo, và lược đồ sau khi dựng vẫn có đủ ràng buộc.
        with cn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{thu}`")
            cur.execute(
                f"CREATE DATABASE `{thu}` CHARACTER SET utf8mb4 "
                f"COLLATE utf8mb4_unicode_ci"
            )
            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            for b in sorted(tat_ca):
                cur.execute(f"CREATE TABLE `{thu}`.`{b}` LIKE `{goc}`.`{b}`")
            for b in BANG_THAM_CHIEU:
                cot = _cot_ghi_duoc(cn, goc, b)
                ds = ", ".join(f"`{c}`" for c in cot)
                cur.execute(
                    f"INSERT INTO `{thu}`.`{b}` ({ds}) "
                    f"SELECT {ds} FROM `{goc}`.`{b}`"
                )
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        cn.commit()
    finally:
        cn.close()


def xoa_csdl_thu(thu: str) -> None:
    cn = connect("information_schema", dict_cursor=True)
    try:
        with cn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{thu}`")
        cn.commit()
    finally:
        cn.close()


# ── Dựng người dùng giả ───────────────────────────────────────────────


def dung_nguoi_dung(cn) -> dict[str, int]:
    """Tạo người dùng với số lượt vuốt phủ cả bốn giai đoạn.

    Trả về `{user_id: số lượt vuốt tính được}`. Số tính được khác số đã chèn
    vì lượt `unknown` không được đếm — và đó chính là một điều cần kiểm.
    """
    rng = random.Random(2026)
    mon, _ = load_foods(cn)
    kg = FeatureSpace.from_foods(mon)
    foods_by_id = {m.id: m for m in mon}
    fid = sorted(foods_by_id)
    goc = datetime(2026, 9, 1, 8, 0, 0)

    ket_qua: dict[str, int] = {}
    with cn.cursor() as cur:
        for u, so in enumerate(SO_VUOT):
            uid = f"{u:08d}-0000-0000-0000-000000000000"
            cur.execute(
                "INSERT INTO users (id, email, password_hash, display_name) "
                "VALUES (%s, %s, %s, %s)",
                (uid, f"u{u}@thu.test", "x" * 20, f"Người thử {u} ({so} vuốt)"),
            )
            cur.execute(
                "INSERT INTO health_profiles (id, user_id, gender, "
                "date_of_birth, height_cm, weight_kg, activity_level, goal) "
                "VALUES (UUID(), %s, %s, %s, %s, %s, %s, %s)",
                (
                    uid,
                    rng.choice(["male", "female"]),
                    f"{rng.randint(1975, 2005)}-06-15",
                    rng.randint(150, 185),
                    rng.randint(45, 95),
                    rng.choice(["sedentary", "light", "moderate", "active"]),
                    rng.choice(
                        ["lose_weight", "maintain", "gain_weight", "healthy_eating"]
                    ),
                ),
            )

            cap = []
            for i, f in enumerate(rng.sample(fid, so)):
                # Một phần nhỏ là `unknown` để kiểm rằng nó bị loại khỏi cả
                # vector Rocchio lẫn tập huấn luyện.
                hd = rng.choices(
                    ["like", "dislike", "neutral", "unknown"],
                    weights=[40, 40, 15, 5],
                )[0]
                cur.execute(
                    "INSERT INTO interactions (id, user_id, food_id, action, "
                    "session_id, interacted_at) VALUES (UUID(), %s, %s, %s, %s, %s)",
                    (uid, f, hd, SES, goc + timedelta(seconds=u * 7200 + i)),
                )
                cap.append((foods_by_id[f], hd))

            # Vài tín hiệu khác nguồn, nhãn cũng ngẫu nhiên.
            for f in rng.sample(fid, min(4, so) if so else 0):
                cur.execute(
                    "INSERT INTO feedbacks (id, user_id, food_id, rating, "
                    "created_at) VALUES (UUID(), %s, %s, %s, %s)",
                    (uid, f, rng.randint(1, 5),
                     goc + timedelta(days=5, seconds=u * 60)),
                )

            ho_so = build_profile(kg, cap)
            cur.execute(
                "INSERT INTO user_preference_profiles (user_id, "
                "feature_version, weights, sum_abs_weight, n_signals, stage, "
                "alpha) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    uid,
                    FEATURE_VERSION,
                    json.dumps(list(ho_so.weights)),
                    ho_so.sum_abs_weight,
                    ho_so.n_signals,
                    stage(ho_so.n_signals),
                    round(alpha(ho_so.n_signals), 3),
                ),
            )
            ket_qua[uid] = ho_so.n_signals
    cn.commit()
    return ket_qua


# ── Các phép kiểm ─────────────────────────────────────────────────────


def kiem_nhap_phieu(db: str) -> str | None:
    """Sinh một phiếu khảo sát, điền sẵn, nhập vào — kèm các đường lỗi.

    Người dùng nhập từ phiếu sẽ đi tiếp qua cả đường ống phía sau cùng những
    người dùng giả khác, nên bài kiểm này chứng minh luôn rằng dữ liệu thu
    bằng phiếu **dùng được ở hạ nguồn**, không chỉ ghi vào bảng là xong.
    """
    print("\n0. Nhập phiếu khảo sát khẩu vị")
    rng = random.Random(99)
    # `tempfile` chứ không phải một thư mục trong repo: bài kiểm này không
    # được để lại tệp nào trong cây nguồn, kể cả khi nó hỏng giữa đường.
    thu_muc = Path(tempfile.mkdtemp(prefix="kiem_ml_phieu_"))

    cn = connect(db)
    try:
        mon, _ = load_foods(cn)
    finally:
        cn.close()
    kg = FeatureSpace.from_foods(mon)
    bo = chon_bo_mon(mon, kg, 40)
    kiem(len(bo) == 40, "chọn được bộ 40 món khảo sát")
    kiem(
        len({m.category for m in bo}) == len({m.category for m in mon}),
        "bộ món phủ đủ mọi nhóm món",
    )
    kiem(
        chon_bo_mon(mon, kg, 40) == bo,
        "chọn lại cho đúng bộ cũ — thuật toán xác định, không ngẫu nhiên",
    )

    def viet_phieu(
        ten: str, *, lua_chon=None, thong_tin_them="", n_foods: int = 40
    ) -> Path:
        p = thu_muc / ten
        with p.open("w", encoding="utf-8", newline="") as f:
            f.write("# ho_ten: Người điền phiếu\n")
            f.write("# email: nguoi.dien@thu.test\n")
            f.write("# gioi_tinh: female\n")
            f.write("# ngay_sinh: 1999-04-20\n")
            f.write("# chieu_cao_cm: 162\n")
            f.write("# can_nang_kg: 54\n")
            f.write("# muc_van_dong: light\n")
            f.write("# muc_tieu: healthy_eating\n")
            f.write("# benh_ly: Tăng huyết áp\n")
            f.write("# ngay_khao_sat: 2026-10-20\n")
            f.write(thong_tin_them)
            w = csv.writer(f)
            w.writerow(["stt", "ma_mon", "ten_mon", "nhom", "muc_cay", "lua_chon"])
            for i, m in enumerate(bo[:n_foods], start=1):
                chon = (
                    lua_chon(i, m)
                    if lua_chon
                    else rng.choice(
                        ["thich", "thich", "khong_thich", "binh_thuong", "chua_biet"]
                    )
                )
                w.writerow([i, m.id, m.name, m.category, m.spice_level, chon])
        return p

    # ── Đường lỗi: phải từ chối TRƯỚC khi ghi gì ──
    truong_hop_loi = [
        (
            "sai_lua_chon.csv",
            dict(lua_chon=lambda i, m: "co_le_thich" if i == 3 else "thich"),
            "`lua_chon` sai giá trị",
        ),
        (
            "chua_dien.csv",
            dict(lua_chon=lambda i, m: ""),
            "phiếu chưa điền lựa chọn nào",
        ),
        (
            "thieu_thong_tin.csv",
            dict(thong_tin_them="# chieu_cao_cm: \n"),
            "phần thông tin còn trống",
        ),
    ]
    for ten, kw, mo_ta in truong_hop_loi:
        p = viet_phieu(ten, **kw)
        if ten == "thieu_thong_tin.csv":
            # Ghi lại cả tệp với chiều cao để trống, vì khóa trùng thì bản
            # sau thắng — viết thêm một dòng không xóa được dòng cũ.
            noi_dung = p.read_text(encoding="utf-8").replace(
                "# chieu_cao_cm: 162\n", ""
            )
            p.write_text(noi_dung, encoding="utf-8")
        ma = chay_nhap_phieu(["--phieu", str(p), "--db", db, "--apply"])
        kiem(ma == 1, f"từ chối phiếu: {mo_ta}")

    cn = connect(db)
    try:
        with cn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) n FROM users WHERE email = 'nguoi.dien@thu.test'"
            )
            kiem(
                int(cur.fetchone()["n"]) == 0,
                "phiếu bị từ chối không để lại người dùng nào",
            )
    finally:
        cn.close()

    # Chiều cao ngoài khoảng CHECK của health_profiles.
    p = viet_phieu("cao_vo_ly.csv")
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "# chieu_cao_cm: 162", "# chieu_cao_cm: 320"
        ),
        encoding="utf-8",
    )
    kiem(
        chay_nhap_phieu(["--phieu", str(p), "--db", db, "--apply"]) == 1,
        "từ chối phiếu: chiều cao ngoài khoảng 50–250",
    )

    # Tên bệnh lý không khớp `conditions`.
    p = viet_phieu("benh_la.csv")
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "# benh_ly: Tăng huyết áp", "# benh_ly: Cảm nắng"
        ),
        encoding="utf-8",
    )
    kiem(
        chay_nhap_phieu(["--phieu", str(p), "--db", db, "--apply"]) == 1,
        "từ chối phiếu: tên bệnh lý không có trong `conditions`",
    )

    # ── Đường đúng ──
    p = viet_phieu("hop_le.csv")
    kiem(
        chay_nhap_phieu(["--phieu", str(p), "--db", db]) == 0,
        "chạy thử phiếu hợp lệ: mã trả về 0",
    )
    cn = connect(db)
    try:
        with cn.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM users")
            truoc = int(cur.fetchone()["n"])
    finally:
        cn.close()

    kiem(
        chay_nhap_phieu(["--phieu", str(p), "--db", db, "--apply"]) == 0,
        "nhập phiếu hợp lệ: mã trả về 0",
    )

    cn = connect(db)
    try:
        with cn.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM users")
            kiem(int(cur.fetchone()["n"]) == truoc + 1, "chạy thử KHÔNG ghi gì")

            cur.execute(
                "SELECT id, password_hash, display_name FROM users "
                "WHERE email = 'nguoi.dien@thu.test'"
            )
            u = cur.fetchone()
            kiem(u is not None, "đã tạo người dùng")
            uid = u["id"]
            kiem(
                u["password_hash"].startswith("!"),
                "mật khẩu là giá trị không dùng được (có dấu `!` đầu)",
            )

            cur.execute(
                "SELECT gender, height_cm, weight_kg, bmi, goal "
                "FROM health_profiles WHERE user_id = %s",
                (uid,),
            )
            hp = cur.fetchone()
            kiem(hp is not None, "đã tạo health_profiles")
            kiem(
                abs(float(hp["bmi"]) - 54 / (1.62**2)) < 0.01,
                f"cột sinh bmi tự tính đúng ({float(hp['bmi']):.2f})",
            )

            cur.execute(
                "SELECT co.name_vi FROM user_conditions uc "
                "JOIN conditions co ON co.id = uc.condition_id "
                "WHERE uc.user_id = %s",
                (uid,),
            )
            kiem(
                [d["name_vi"] for d in cur.fetchall()] == ["Tăng huyết áp"],
                "đã ghi bệnh lý",
            )

            cur.execute(
                "SELECT action, COUNT(*) n FROM interactions "
                "WHERE user_id = %s GROUP BY action",
                (uid,),
            )
            dem = {d["action"]: int(d["n"]) for d in cur.fetchall()}
            kiem(sum(dem.values()) == 40, f"ghi đủ 40 lượt vuốt (được {dem})")

            cur.execute(
                "SELECT COUNT(DISTINCT interacted_at) n FROM interactions "
                "WHERE user_id = %s",
                (uid,),
            )
            kiem(
                int(cur.fetchone()["n"]) == 40,
                "40 lượt có 40 mốc thời gian phân biệt — thứ tự phiếu được giữ",
            )

            cur.execute(
                "SELECT feature_version, n_signals, stage, "
                "       JSON_LENGTH(weights) so_chieu "
                "FROM user_preference_profiles WHERE user_id = %s",
                (uid,),
            )
            pr = cur.fetchone()
            kiem(pr is not None, "đã tính user_preference_profiles")
            kiem(
                int(pr["so_chieu"]) == kg.length,
                f"vector sở thích đủ {kg.length} chiều",
            )
            kiem(
                int(pr["n_signals"]) == 40 - dem.get("unknown", 0),
                f"n_signals = {pr['n_signals']} đã trừ "
                f"{dem.get('unknown', 0)} lượt `chua_biet`",
            )
            kiem(
                pr["feature_version"] == FEATURE_VERSION,
                "hồ sơ ghi kèm phiên bản đặc trưng",
            )

        # Nhập lại cùng phiếu: phải từ chối vì email đã tồn tại.
        kiem(
            chay_nhap_phieu(["--phieu", str(p), "--db", db, "--apply"]) == 1,
            "nhập lại cùng phiếu thì từ chối — email đã tồn tại",
        )
    finally:
        cn.close()

    shutil.rmtree(thu_muc, ignore_errors=True)
    return uid


def kiem_duong_ong(db: str, so_tin_hieu: dict[str, int]) -> None:
    print("\n1. Bộ dựng tập dữ liệu")
    ma = chay_dung_tap(
        ["--version", "e2e", "--db", db, "--apply", "--random-neg", "8",
         "--folds", "5", "--seed", "7"]
    )
    kiem(ma == 0, "build_dataset chạy xong, mã trả về 0")

    cn = connect(db)
    try:
        with cn.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM ml_training_samples")
            n_mau = cur.fetchone()["n"]
            cur.execute(
                "SELECT COUNT(*) n FROM ml_training_samples s "
                "JOIN interactions i ON i.user_id = s.user_id "
                "  AND i.food_id = s.food_id "
                "WHERE s.source = 'swipe' AND i.action = 'unknown'"
            )
            n_unknown = cur.fetchone()["n"]
            cur.execute(
                "SELECT COUNT(DISTINCT fold) n FROM ml_training_samples"
            )
            n_fold = cur.fetchone()["n"]
            cur.execute(
                "SELECT COUNT(*) n FROM ("
                "  SELECT user_id FROM ml_training_samples "
                "  GROUP BY user_id HAVING COUNT(DISTINCT fold) > 1) x"
            )
            n_vo_fold = cur.fetchone()["n"]
            cur.execute(
                "SELECT COUNT(*) n FROM ml_training_samples "
                "WHERE profile_snapshot IS NULL"
            )
            n_thieu_anh = cur.fetchone()["n"]

        kiem(n_mau > 0, f"có {n_mau} mẫu")
        kiem(n_unknown == 0, "không mẫu `swipe` nào đến từ lượt `unknown`")
        kiem(n_fold == 5, f"dùng đủ 5 fold (được {n_fold})")
        kiem(n_vo_fold == 0, "không người dùng nào bị cắt qua hai fold")
        kiem(n_thieu_anh == 0, "mọi mẫu đều có profile_snapshot")

        print("\n1b. Độ phổ biến — phương án đối chứng phải thôi suy biến")
        with cn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT popularity_score) n FROM foods"
            )
            kiem(
                cur.fetchone()["n"] == 1,
                "trước khi tính: mọi món cùng một popularity_score (suy biến)",
            )
        ma = chay_cap_nhat_pho_bien(["--db", db, "--apply"])
        kiem(ma == 0, "update_popularity chạy xong, mã trả về 0")
        cn.commit()
        with cn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT popularity_score) n, "
                "       MIN(popularity_score) nho, MAX(popularity_score) lon, "
                "       SUM(popularity_score > 0) co_diem "
                "FROM foods"
            )
            pb = cur.fetchone()
        kiem(
            int(pb["n"]) > 1,
            f"sau khi tính: có {pb['n']} mức điểm phân biệt — thôi suy biến",
        )
        kiem(
            0 <= float(pb["nho"]) and float(pb["lon"]) <= 1,
            f"điểm nằm trong [0, 1]: {float(pb['nho']):.4f}–{float(pb['lon']):.4f}",
        )
        kiem(
            int(pb["co_diem"]) > 0,
            f"{pb['co_diem']} món có điểm lớn hơn 0",
        )

        print("\n2. Huấn luyện")
        ma = chay_huan_luyen(
            ["--dataset", "e2e", "--db", db, "--apply",
             "--algorithm", "logistic_regression",
             "--activate", "logistic_regression"]
        )
        kiem(ma == 0, "train chạy xong, mã trả về 0")

        cn.commit()  # thoát ảnh chụp giao dịch cũ để thấy hàng vừa ghi
        with cn.cursor() as cur:
            cur.execute(
                "SELECT version, n_train, n_test, is_active, feature_version "
                "FROM ml_models"
            )
            mh = cur.fetchall()
        kiem(len(mh) == 1, f"ghi 1 mô hình (được {len(mh)})")
        kiem(
            sum(int(r["is_active"]) for r in mh) == 1,
            "đúng một mô hình is_active = 1",
        )
        kiem(
            mh[0]["feature_version"] == FEATURE_VERSION,
            "feature_version của mô hình khớp mã hiện tại",
        )
        kiem(
            mh[0]["n_train"] > 0 and mh[0]["n_test"] > 0,
            f"n_train = {mh[0]['n_train']}, n_test = {mh[0]['n_test']}",
        )
        ban_mo_hinh = mh[0]["version"]

        print("\n3. Đánh giá")
        ma = chay_danh_gia(
            ["--dataset", "e2e", "--model", ban_mo_hinh, "--db", db, "--apply"]
        )
        kiem(ma == 0, "evaluate chạy xong, mã trả về 0")

        cn.commit()
        with cn.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM ml_evaluations")
            n_dg = cur.fetchone()["n"]
            cur.execute(
                "SELECT COUNT(DISTINCT variant) n FROM ml_evaluations"
            )
            n_pa = cur.fetchone()["n"]
            cur.execute(
                "SELECT COUNT(DISTINCT metric) n FROM ml_evaluations"
            )
            n_cs = cur.fetchone()["n"]
            cur.execute(
                "SELECT variant, ROUND(AVG(value), 4) v FROM ml_evaluations "
                "WHERE metric = 'auc' GROUP BY variant ORDER BY variant"
            )
            auc = {d["variant"]: float(d["v"]) for d in cur.fetchall()}
        kiem(n_dg > 0, f"ghi {n_dg} dòng đánh giá")
        kiem(n_pa == 5, f"đủ 5 phương án đối chứng (được {n_pa})")
        kiem(n_cs == 8, f"đủ 8 chỉ số (được {n_cs})")

        # ── Chốt canh rò rỉ dữ liệu ──
        #
        # Nhãn ngẫu nhiên hoàn toàn, nên **mọi** phương án phải ở mức tình cờ.
        # Kiểm bằng AUC chứ không bằng nDCG: AUC có mức tình cờ xác định là
        # 0,5 bất kể phân bố nhãn và bất kể hòa điểm, còn nDCG@5 thì không —
        # mức tình cờ của nó phụ thuộc độ dài danh sách của từng người và số
        # món hòa điểm, nên nDCG của hai phương án lệch nhau 0,15 vẫn có thể
        # là cả hai đều vô thông tin.
        #
        # Kiểm cả năm phương án, không chỉ `ml`: hai lần rò rỉ đã tìm ra đều
        # xuất hiện ở `popularity` TRƯỚC khi lan sang mô hình.
        for pa in sorted(auc):
            kiem(
                0.35 <= auc[pa] <= 0.65,
                f"CHỐT CANH RÒ RỈ: AUC của `{pa}` = {auc[pa]:.4f}, "
                f"quanh mức tình cờ",
            )

        # Chạy lại không nhân đôi — hai khóa duy nhất phải chặn.
        chay_dung_tap(
            ["--version", "e2e", "--db", db, "--apply", "--random-neg", "8",
             "--folds", "5", "--seed", "7"]
        )
        chay_danh_gia(
            ["--dataset", "e2e", "--model", ban_mo_hinh, "--db", db, "--apply"]
        )
        cn.commit()
        with cn.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM ml_training_samples")
            n_mau2 = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) n FROM ml_evaluations")
            n_dg2 = cur.fetchone()["n"]
        kiem(n_mau2 == n_mau, f"chạy lại: {n_mau} → {n_mau2} mẫu, không nhân đôi")
        kiem(n_dg2 == n_dg, f"chạy lại: {n_dg} → {n_dg2} dòng đánh giá")
    finally:
        cn.close()


def kiem_phuc_vu(db: str, so_tin_hieu: dict[str, int]) -> None:
    print("\n4. Tầng phục vụ — bốn giai đoạn")
    cn = connect(db)
    try:
        theo_gd: dict[str, str] = {}
        for uid, n in sorted(so_tin_hieu.items(), key=lambda kv: kv[1]):
            theo_gd.setdefault(stage(n), uid)

        kiem(
            set(theo_gd) == {"cold", "content", "hybrid", "ml"},
            f"dữ liệu thử phủ cả bốn giai đoạn (được {sorted(theo_gd)})",
        )

        mong_doi_nguon = {
            "cold": "rule_based",
            "content": "content_based",
            "hybrid": "hybrid",
            "ml": "ml",
        }
        for gd, uid in sorted(theo_gd.items()):
            kq = recommend(cn, uid, limit=5)
            kiem(
                kq.stage == gd and kq.generation_source == mong_doi_nguon[gd],
                f"{gd}: generation_source = {kq.generation_source}",
            )
            kiem(
                len(kq.candidates) == 5,
                f"{gd}: trả về 5 ứng viên hàng đầu",
            )
            kiem(
                all(0.0 <= u.score <= 1.0 for u in kq.candidates),
                f"{gd}: mọi điểm nằm trong [0, 1]",
            )
            kiem(
                all(
                    kq.candidates[i].score >= kq.candidates[i + 1].score
                    for i in range(len(kq.candidates) - 1)
                ),
                f"{gd}: danh sách đã xếp giảm dần",
            )
            dung_mo_hinh = gd in ("hybrid", "ml")
            kiem(
                (kq.model_id is not None) == dung_mo_hinh,
                f"{gd}: {'dùng' if dung_mo_hinh else 'không dùng'} mô hình",
            )
            if gd == "cold":
                kiem(
                    all(u.ml_score is None for u in kq.candidates),
                    "cold: không gọi mô hình chút nào",
                )
            if gd == "hybrid":
                kiem(0 < kq.alpha < 1, f"hybrid: 0 < α = {kq.alpha:.3f} < 1")
            if gd == "ml":
                kiem(kq.alpha == 1.0, "ml: α = 1")

        # ── Bộ lọc F1 thật sự cắt ứng viên ──
        uid = theo_gd["content"]
        truoc = recommend(cn, uid, limit=1000).n_foods_after_f1
        dk = conditions_by_name(cn, ["Ăn thuần chay", "Dị ứng đậu nành"], "severe")
        with cn.cursor() as cur:
            for d in dk:
                cur.execute(
                    "INSERT INTO user_conditions (id, user_id, condition_id, "
                    "severity) VALUES (UUID(), %s, %s, 'severe')",
                    (uid, d.condition_id),
                )
        cn.commit()
        sau = recommend(cn, uid, limit=1000).n_foods_after_f1
        kiem(
            sau < truoc,
            f"thêm bệnh lý thì F1 cắt ứng viên: {truoc} → {sau} món",
        )

        # Món đã dùng trong ngày bị loại.
        kq = recommend(cn, uid, limit=3)
        da_dung = [u.food.id for u in kq.candidates[:2]]
        kq2 = recommend(cn, uid, limit=3, exclude_foods=da_dung)
        kiem(
            all(u.food.id not in da_dung for u in kq2.candidates),
            "món đã dùng trong ngày không xuất hiện lại",
        )

        print("\n5. Hạ cấp có công bố")
        uid_ml = theo_gd["ml"]
        with cn.cursor() as cur:
            cur.execute("UPDATE ml_models SET is_active = 0")
        cn.commit()
        kq = recommend(cn, uid_ml, limit=3)
        kiem(
            kq.stage == "content" and kq.generation_source == "content_based",
            f"không có mô hình → lùi về content_based (được {kq.stage})",
        )
        kiem(
            any("falling back to Stage 1" in c for c in kq.warnings),
            "việc hạ cấp được công bố trong cảnh báo",
        )

        # Hai mô hình cùng is_active: phải từ chối chọn bừa.
        with cn.cursor() as cur:
            cur.execute(
                "INSERT INTO ml_models (version, algorithm, feature_version, "
                "dataset_version, n_train, n_test, artifact_path, is_active) "
                "SELECT CONCAT(version, '-x'), algorithm, feature_version, "
                "dataset_version, n_train, n_test, artifact_path, 1 "
                "FROM ml_models LIMIT 1"
            )
            cur.execute("UPDATE ml_models SET is_active = 1")
        cn.commit()
        mon, _ = load_foods(cn)
        kg = FeatureSpace.from_foods(mon)
        mh, ly_do = load_active_model(cn, kg)
        kiem(
            mh is None and ly_do is not None and "share is_active" in ly_do,
            f"hai mô hình cùng is_active thì từ chối chọn bừa ({ly_do})",
        )

        # Hồ sơ sở thích sai phiên bản đặc trưng: bỏ qua và công bố.
        with cn.cursor() as cur:
            cur.execute("UPDATE ml_models SET is_active = 0")
            cur.execute(
                "UPDATE user_preference_profiles SET feature_version = 'v0-cu' "
                "WHERE user_id = %s",
                (uid_ml,),
            )
        cn.commit()
        kq = recommend(cn, uid_ml, limit=3)
        kiem(
            kq.stage == "cold" and kq.n_signals == 0,
            f"hồ sơ sai phiên bản → lùi về Giai đoạn 0 (được {kq.stage})",
        )
        kiem(
            any("feature version" in c for c in kq.warnings),
            "việc bỏ qua hồ sơ được công bố",
        )

        # Hồ sơ thiếu chiều: cũng phải bị bỏ qua.
        with cn.cursor() as cur:
            cur.execute(
                "UPDATE user_preference_profiles "
                "SET feature_version = %s, weights = %s WHERE user_id = %s",
                (FEATURE_VERSION, json.dumps([0.1] * 5), uid_ml),
            )
        cn.commit()
        kq = recommend(cn, uid_ml, limit=3)
        kiem(
            kq.stage == "cold",
            f"hồ sơ thiếu chiều → lùi về Giai đoạn 0 (được {kq.stage})",
        )
        kiem(
            any("dimensions" in c for c in kq.warnings),
            "việc bỏ qua hồ sơ thiếu chiều được công bố",
        )
    finally:
        cn.close()


def kiem_han_muc_ngay(db: str) -> None:
    """Hạn mức theo ngày trên CSDL thật — hai nguồn, và quy ước không đếm đôi.

    Phần này chèn nhật ký và thực đơn thật rồi đối chiếu tổng với số cộng tay
    lấy day từ `food_nutrition`. Nó kiểm những điều phép kiểm hàm thuần
    không chạm tới: câu SQL có nhân `portion_multiplier` không, ô `replaced`
    có tính theo món **mới** không, và ô `eaten` có bị cộng hai lần không.
    """
    print("\n6. Hạn mức theo ngày — nhật ký, thực đơn và quy ước đếm")
    day= date(2026, 10, 15)
    uid = "00000003-0000-0000-0000-000000000000"

    cn = connect(db)
    try:
        with cn.cursor() as cur:
            # Gút mức vừa + Tăng huyết áp mức nhẹ: đúng hai bệnh có ngưỡng
            # cứng theo ngày trong bộ quy tắc.
            for cid, muc in ((5, "moderate"), (2, "mild")):
                cur.execute(
                    "INSERT INTO user_conditions (id, user_id, condition_id, "
                    "severity, created_at) VALUES (UUID(), %s, %s, %s, NOW())",
                    (uid, cid, muc),
                )

            cur.execute(
                "SELECT f.id, f.name, fn.sodium_mg, fn.purine_mg "
                "FROM foods f JOIN food_nutrition fn ON fn.food_id = f.id "
                "WHERE f.name IN (%s, %s, %s, %s)",
                ("Bánh cuốn nóng", "Canh chua chay", "Cá chiên xù", "Bắp cải luộc"),
            )
            mon = {d["name"]: d for d in cur.fetchall()}

        kiem(len(mon) == 4, f"tìm đủ 4 món mốc trong CSDL thử, được {len(mon)}")
        if len(mon) != 4:
            return

        natri = {k: float(v["sodium_mg"]) for k, v in mon.items()}
        purin = {k: float(v["purine_mg"]) for k, v in mon.items()}

        with cn.cursor() as cur:
            # ĐÃ ĂN: một suất rưỡi, để bắt lỗi quên nhân khẩu phần. Lỗi đó
            # cho ra số NHỎ hơn thật, tức là nới hạn mức an toàn mà không
            # báo gì — đúng loại lỗi không bao giờ tự lộ.
            cur.execute(
                "INSERT INTO food_diary (id, user_id, food_id, ate_on, "
                "meal_type, portion_multiplier, created_at) "
                "VALUES (UUID(), %s, %s, %s, 'breakfast', 0.50, NOW())",
                (uid, mon["Bánh cuốn nóng"]["id"], day),
            )

            cur.execute(
                "INSERT INTO meal_plans (id, user_id, plan_date, "
                "target_calories_kcal, target_protein_g, target_carbs_g, "
                "target_fat_g, generation_source, status, generated_at) "
                "VALUES (UUID(), %s, %s, 2000, 90, 250, 60, 'rule_based', "
                "'active', NOW())",
                (uid, day),
            )
            cur.execute(
                "SELECT id FROM meal_plans WHERE user_id = %s AND plan_date = %s",
                (uid, day),
            )
            plan_id = cur.fetchone()["id"]

            o = (
                # (món, trạng thái, khẩu phần, món thay thế)
                ("Canh chua chay", "kept", 1.00, None),
                ("Cá chiên xù", "suggested", 2.00, None),
                # Ô bị đổi: phải tính Bắp cải luộc, KHÔNG phải Cá chiên xù.
                ("Cá chiên xù", "replaced", 1.00, "Bắp cải luộc"),
                # Có nhật ký kèm → quy ước được tôn trọng.
                ("Bánh cuốn nóng", "eaten", 1.00, None),
                # KHÔNG có nhật ký → `check_double_counting` phải bắt được.
                ("Cá chiên xù", "eaten", 1.00, None),
                ("Bắp cải luộc", "skipped", 1.00, None),
            )
            for ten, tt_o, khau, thay in o:
                cur.execute(
                    "INSERT INTO meal_plan_items (id, meal_plan_id, food_id, "
                    "meal_type, portion_multiplier, status, "
                    "replaced_by_food_id, created_at) "
                    "VALUES (UUID(), %s, %s, 'lunch', %s, %s, %s, NOW())",
                    (
                        plan_id,
                        mon[ten]["id"],
                        khau,
                        tt_o,
                        mon[thay]["id"] if thay else None,
                    ),
                )
        cn.commit()

        # ── Từng tổng đối chiếu với số cộng tay ──
        an = eaten_totals(cn, uid, day)
        mong_an = natri["Bánh cuốn nóng"] * 0.5
        gan(an.totals["sodium_mg"], mong_an, "đã ăn: natri = 0,5 suất Bánh cuốn nóng")

        ke = planned_totals(cn, uid, day)
        mong_ke = (
            natri["Canh chua chay"] * 1.0
            + natri["Cá chiên xù"] * 2.0
            + natri["Bắp cải luộc"] * 1.0  # ô `replaced` tính theo món MỚI
        )
        gan(
            ke.totals["sodium_mg"],
            mong_ke,
            "kế hoạch: `kept` + `suggested`×2 + `replaced`→món mới",
        )
        kiem(
            abs(ke.totals["sodium_mg"] - (mong_ke + natri["Bánh cuốn nóng"])) > 1.0,
            "ô `eaten` KHÔNG bị cộng vào kế hoạch — nếu cộng là đếm đôi",
        )
        kiem(
            abs(ke.totals["sodium_mg"] - (mong_ke + natri["Bắp cải luộc"])) > 1.0,
            "ô `skipped` không được cộng",
        )
        kiem(
            abs(
                ke.totals["sodium_mg"]
                - (mong_ke - natri["Bắp cải luộc"] + natri["Cá chiên xù"])
            )
            > 1.0,
            "ô `replaced` không tính theo món CŨ",
        )

        # ── Trạng thái hạn mức ──
        dk = conditions_for_user(cn, uid)
        kiem(len(dk) == 2, f"đọc được 2 bệnh của người này, được {len(dk)}")
        tt = status(cn, uid, conditions=dk, day=day)
        kiem(not tt.is_empty, "có ngưỡng cứng theo ngày")
        nutrient = {h.nutrient for h in tt.limits}
        kiem(
            nutrient == {"sodium_mg", "purine_mg"},
            f"hai ngưỡng: natri và purin, được {sorted(nutrient)}",
        )

        h_natri = tt.tightest_limit("sodium_mg")
        kiem(h_natri is not None, "có ngưỡng trần cho natri")
        if h_natri is not None:
            gan(h_natri.threshold, 2000.0, "ngưỡng natri 2 000 mg (WHO)")
            gan(h_natri.eaten, mong_an, "phần đã ăn khớp")
            gan(h_natri.planned, mong_ke, "phần kế hoạch khớp")
            gan(
                h_natri.remaining,
                2000.0 - mong_an - mong_ke,
                "phần còn lại = ngưỡng − đã ăn − kế hoạch",
            )

        h_purin = tt.tightest_limit("purine_mg")
        kiem(h_purin is not None, "có ngưỡng trần cho purin")
        if h_purin is not None:
            gan(h_purin.threshold, 400.0, "ngưỡng purin 400 mg")
            mong_purin = (
                purin["Bánh cuốn nóng"] * 0.5
                + purin["Canh chua chay"]
                + purin["Cá chiên xù"] * 2.0
                + purin["Bắp cải luộc"]
            )
            gan(h_purin.used, mong_purin, "tổng purin khớp số cộng tay")

        # ── `classify_foods` trên toàn danh mục thật ──
        with cn.cursor() as cur:
            cur.execute(
                "SELECT f.id, f.name, fn.sodium_mg, fn.purine_mg "
                "FROM foods f JOIN food_nutrition fn ON fn.food_id = f.id "
                "WHERE f.is_active = 1 ORDER BY f.name"
            )
            tat_ca = list(cur.fetchall())

        kq = classify_foods(tt, tat_ca)
        does_not_fit = kq.does_not_fit
        if h_natri is not None and h_purin is not None:
            # Phép lọc tay phải xử lý NULL y như mã: ô khuyết KHÔNG kết luận
            # được, nên không vào tập này.
            def vuot(d, nutrient, h):
                v = d[nutrient]
                return v is not None and float(v) > h.remaining

            bang_tay = {
                d["id"]
                for d in tat_ca
                if vuot(d, "sodium_mg", h_natri) or vuot(d, "purine_mg", h_purin)
            }
            kiem(
                set(does_not_fit) == bang_tay,
                f"tập món không vừa khớp phép lọc tay "
                f"({len(does_not_fit)} vs {len(bang_tay)} món)",
            )
            # Nhóm chưa xét được phải khớp đúng số ô NULL của danh mục.
            tay_thieu = {
                d["id"]
                for d in tat_ca
                if d["id"] not in bang_tay
                and (d["sodium_mg"] is None or d["purine_mg"] is None)
            }
            kiem(
                set(kq.undecidable) == tay_thieu,
                f"nhóm chưa xét được khớp số ô NULL "
                f"({len(kq.undecidable)} vs {len(tay_thieu)} món)",
            )
            kiem(
                len(kq.undecidable) > 0,
                f"danh mục thật CÓ món thiếu số liệu — {len(kq.undecidable)} "
                f"món; nếu con số này là 0 thì phép kiểm mất ý nghĩa",
            )
            kiem(
                not any(f in kq.undecidable for f in does_not_fit),
                "không món nào ở cả hai nhóm cùng lúc",
            )
        kiem(
            all(l.excess > 0 for ly_do in does_not_fit.values() for l in ly_do),
            "mọi lý do đều nêu một lượng vượt dương",
        )
        kiem(
            all(
                l.nutrient in ("sodium_mg", "purine_mg")
                for ly_do in does_not_fit.values()
                for l in ly_do
            ),
            "không lý do nào viện một chất không bị hạn chế",
        )

        # ── Cờ đủ dữ liệu, trên danh mục thật ──
        if h_purin is not None:
            kiem(
                h_purin.has_full_data,
                "bốn món mốc đều có số liệu purin nên cờ báo ĐỦ dữ liệu",
            )

        # Giờ chèn một món KHUYẾT purin vào nhật ký. Trên 318 món hoạt động
        # có 248 món như vậy, nên đây là trường hợp thường, không phải ngoại
        # lệ — và cờ phải bật.
        with cn.cursor() as cur:
            cur.execute(
                "SELECT f.id, f.name FROM foods f "
                "JOIN food_nutrition fn ON fn.food_id = f.id "
                "WHERE f.is_active = 1 AND fn.purine_mg IS NULL "
                "ORDER BY f.name LIMIT 1"
            )
            mon_khuyet = cur.fetchone()
        kiem(mon_khuyet is not None, "danh mục có món khuyết purine_mg")
        if mon_khuyet is not None:
            with cn.cursor() as cur:
                cur.execute(
                    "INSERT INTO food_diary (id, user_id, food_id, ate_on, "
                    "meal_type, portion_multiplier, created_at) "
                    "VALUES (UUID(), %s, %s, %s, 'snack', 1.00, NOW())",
                    (uid, mon_khuyet["id"], day),
                )
            cn.commit()

            tt2 = status(cn, uid, conditions=dk, day=day)
            h2 = tt2.tightest_limit("purine_mg")
            kiem(h2 is not None, "vẫn đọc được ngưỡng purin sau khi thêm món")
            if h2 is not None:
                kiem(
                    not h2.has_full_data,
                    f"thêm 1 món khuyết purin thì cờ báo THIẾU dữ liệu "
                    f"({mon_khuyet['name']})",
                )
                gan(
                    float(h2.n_missing_servings),
                    1.0,
                    "đếm đúng 1 suất thiếu số liệu purin",
                )
                gan(
                    h2.used,
                    h_purin.used if h_purin else 0.0,
                    "tổng purin KHÔNG đổi — món khuyết cộng vào 0, và chính "
                    "đó là lý do phải có cờ chứ không thể tin con số",
                )
            h2_natri = tt2.tightest_limit("sodium_mg")
            if h2_natri is not None:
                kiem(
                    h2_natri.used > (h_natri.used if h_natri else 0.0),
                    "natri của cùng món đó thì CÓ cộng vào — khuyết theo "
                    "từng chất, không theo cả món",
                )

        # ── Quy ước đếm đôi ──
        excess = check_double_counting(cn, uid, day)
        kiem(
            len(excess) == 1,
            f"bắt đúng 1 ô `eaten` thiếu nhật ký, được {len(excess)}",
        )
        kiem(
            bool(excess) and excess[0]["food_name"] == "Cá chiên xù",
            "ô bị bắt là Cá chiên xù, còn Bánh cuốn nóng có nhật ký nên bỏ qua",
        )
    finally:
        cn.close()


def kiem_ly_do_loai_sql(db: str) -> None:
    """`exclusion_reasons` phải khớp `allowed_foods` — và nhánh ngưỡng theo suất phải chạy.

    Phép kiểm cốt lõi là `cross_check_f1`: hai câu SQL viết tay đọc cùng
    một bộ quy tắc, nên chúng có thể lệch nhau sau một lần sửa, và khi đó
    giao diện hiện một món vừa trong thực đơn vừa trong danh sách bị loại.

    Phần sau quan trọng không kém: bộ quy tắc THẬT hiện **không có** luật
    `nutrient_limit` cứng theo suất nào — mọi luật theo suất đều mềm. Nghĩa
    là nhánh thứ ba của cả hai câu SQL chưa bao giờ chạy trên dữ liệu thật.
    Phần này dựng một luật như vậy trong CSDL thử để nhánh đó được kiểm, kể
    cả đường thiếu số liệu.
    """
    print("\n7. Lý do bị F1 loại — đối chiếu với allowed_foods và nhánh theo suất")

    cn = connect(db)
    try:
        # ── Đối chiếu trên bộ quy tắc thật ──
        for ten, muc in (
            (["Gút"], "moderate"),
            (["Gút", "Tăng huyết áp"], "moderate"),
            (["Ăn chay"], "mild"),
            (["Dị ứng hải sản", "Gút", "Bệnh thận"], "severe"),
            (["Ăn thuần chay", "Dị ứng đậu phộng"], "severe"),
        ):
            dk = conditions_by_name(cn, ten, severity=muc)
            con = allowed_foods(cn, conditions=dk)
            ly = exclusion_reasons(cn, conditions=dk)
            kh = cross_check_f1(cn, conditions=dk)
            label = "+".join(ten)
            kiem(
                not kh["unexplained"],
                f"{label}: mọi món bị bỏ đều có lý do "
                f"({len(kh['unexplained'])} món không giải thích được)",
            )
            kiem(
                not kh["spurious"],
                f"{label}: không món nào vừa bị loại vừa được cho qua "
                f"({len(kh['spurious'])} món)",
            )
            kiem(
                len(con) + len(ly) == 318,
                f"{label}: còn {len(con)} + bị loại {len(ly)} = 318",
            )

        # ── `severity_min` chặn đúng ──
        # Luật `Giàu purin` của Gút có `severity_min = 'moderate'`.
        dk_nhe = conditions_by_name(cn, ["Gút"], severity="mild")
        dk_vua = conditions_by_name(cn, ["Gút"], severity="moderate")
        kiem(
            len(exclusion_reasons(cn, conditions=dk_nhe)) == 0,
            "Gút mức NHẸ: không món nào bị loại — luật cần mức vừa",
        )
        kiem(
            len(exclusion_reasons(cn, conditions=dk_vua)) == 91,
            "Gút mức VỪA: 91 món bị loại vì nhãn Giàu purin",
        )

        # ── Nội dung lý do `require_tag` ──
        dk_chay = conditions_by_name(cn, ["Ăn chay"], severity="mild")
        ly_chay = exclusion_reasons(cn, conditions=dk_chay)
        kiem(len(ly_chay) == 201, f"Ăn chay: 201 món bị loại, được {len(ly_chay)}")
        mot = next(iter(ly_chay.values()))[0]
        kiem(
            mot.rule_type == "require_tag" and mot.tag == "Món chay",
            "lý do nêu đúng loại luật và đúng tên nhãn còn thiếu",
        )
        kiem(
            all(l.kind == "tag" for v in ly_chay.values() for l in v),
            "mọi lý do của Ăn chay đều ở bậc `tag`",
        )

        # ── Món nhiều lý do ──
        dk_ba = conditions_by_name(
            cn, ["Dị ứng hải sản", "Gút"], severity="severe"
        )
        ly_ba = exclusion_reasons(cn, conditions=dk_ba)
        nhieu = [v for v in ly_ba.values() if len(v) >= 2]
        kiem(
            len(nhieu) > 0,
            f"có món vi phạm nhiều luật cùng lúc ({len(nhieu)} món) — nêu "
            f"một lý do là chưa đủ để người dùng hiểu",
        )
        kiem(
            any({l.condition for l in v} == {"Gút", "Dị ứng hải sản"} for v in nhieu),
            "một món nêu được cả hai bệnh, không gộp thành một",
        )

        # ── Dựng luật cứng theo suất để nhánh 3 được chạy ──
        with cn.cursor() as cur:
            cur.execute(
                "INSERT INTO condition_rules (id, condition_id, rule_type, "
                "nutrient, comparator, threshold, scope, severity_min, "
                "is_hard, note) VALUES (UUID(), 2, 'nutrient_limit', "
                "'sodium_mg', 'lte', 500.00, 'per_serving', 'mild', 1, %s)",
                ("LUẬT DỰNG RIÊNG cho phép kiểm — không phải khuyến cáo nào",),
            )
            cur.execute(
                "SELECT SUM(fn.sodium_mg > 500) AS vuot, "
                "       SUM(fn.sodium_mg IS NULL) AS khuyet "
                "FROM foods f JOIN food_nutrition fn ON fn.food_id = f.id "
                "WHERE f.is_active = 1"
            )
            d = cur.fetchone()
            so_vuot, so_khuyet = int(d["vuot"]), int(d["khuyet"])
        cn.commit()

        dk_tha = conditions_by_name(cn, ["Tăng huyết áp"], severity="mild")
        ly_tha = exclusion_reasons(cn, conditions=dk_tha)
        kh_tha = cross_check_f1(cn, conditions=dk_tha)
        kiem(
            not kh_tha["unexplained"] and not kh_tha["spurious"],
            "luật theo suất: hai câu SQL vẫn khớp nhau",
        )

        kind = {}
        for v in ly_tha.values():
            for l in v:
                kind[l.kind] = kind.get(l.kind, 0) + 1
        kiem(
            kind.get("serving_threshold", 0) == so_vuot,
            f"bậc `serving_threshold` đếm đúng {so_vuot} món vượt 500 mg, "
            f"được {kind.get('nguong_suat', 0)}",
        )
        kiem(
            kind.get("missing_data", 0) == so_khuyet,
            f"bậc `missing_data` đếm đúng {so_khuyet} món khuyết natri, "
            f"được {kind.get('missing_data', 0)}",
        )
        kiem(
            so_khuyet > 0,
            f"danh mục thật CÓ món khuyết natri ({so_khuyet}) — nếu bằng 0 "
            f"thì đường thiếu số liệu không được kiểm",
        )

        # Một lý do cụ thể, đối chiếu số đo với CSDL.
        with cn.cursor() as cur:
            cur.execute(
                "SELECT f.id, f.name, fn.sodium_mg FROM foods f "
                "JOIN food_nutrition fn ON fn.food_id = f.id "
                "WHERE f.is_active = 1 AND fn.sodium_mg IS NOT NULL "
                "ORDER BY fn.sodium_mg DESC LIMIT 1"
            )
            man_nhat = cur.fetchone()
        v = ly_tha.get(man_nhat["id"], [])
        nguong_suat = [l for l in v if l.kind == "serving_threshold"]
        kiem(
            len(nguong_suat) == 1,
            f"{man_nhat['name']} có đúng 1 lý do ngưỡng theo suất",
        )
        if nguong_suat:
            l = nguong_suat[0]
            gan(l.value or 0.0, float(man_nhat["sodium_mg"]), "số đo khớp CSDL")
            gan(l.threshold or 0.0, 500.0, "ngưỡng khớp luật")
            gan(
                l.excess or 0.0,
                float(man_nhat["sodium_mg"]) - 500.0,
                "lượng vượt = số đo − ngưỡng",
            )
            kiem(l.comparator == "lte", "chiều so sánh được giữ lại")
            kiem(
                "LUẬT DỰNG RIÊNG" in l.note,
                "ghi chú của luật đi theo lý do — giao diện cần nó để nói "
                "nguồn khuyến cáo",
            )

        # Món khuyết natri phải vào bậc thiếu số liệu, KHÔNG phải vượt ngưỡng.
        with cn.cursor() as cur:
            cur.execute(
                "SELECT f.id, f.name FROM foods f "
                "JOIN food_nutrition fn ON fn.food_id = f.id "
                "WHERE f.is_active = 1 AND fn.sodium_mg IS NULL "
                "ORDER BY f.name LIMIT 1"
            )
            khuyet = cur.fetchone()
        if khuyet is not None:
            v2 = ly_tha.get(khuyet["id"], [])
            kiem(
                any(l.kind == "missing_data" for l in v2),
                f"{khuyet['name']}: khuyết natri → bậc `missing_data`",
            )
            kiem(
                all(l.excess is None for l in v2 if l.missing_data),
                "không bịa ra lượng vượt cho món không có số đo",
            )

        # Dọn luật dựng riêng. Một phép kiểm để lại CSDL đã bị sửa thì mọi
        # phép kiểm sau nó phụ thuộc thứ tự chạy — và mục 9 đã đếm 21 quy
        # tắc thay vì 20 đúng vì chuyện này.
        with cn.cursor() as cur:
            cur.execute(
                "DELETE FROM condition_rules "
                "WHERE note LIKE 'LUẬT DỰNG RIÊNG%'"
            )
            so_xoa = cur.rowcount
        cn.commit()
        kiem(so_xoa == 1, f"đã dọn luật dựng riêng, xóa {so_xoa} dòng")
    finally:
        cn.close()


def kiem_hinh_phat_mem_sql(db: str) -> None:
    """Ràng buộc mềm trên bộ quy tắc thật — và điều chúng KHÔNG được làm.

    Bất biến quan trọng nhất: một ràng buộc mềm **không bao giờ** được làm
    một món rời khỏi `allowed_foods`. `is_hard = 0` nghĩa là trừ điểm; nếu nó loại
    món thì cả tầng mềm mất lý do tồn tại, và Bước 4 lại hết đường xoay xở
    đúng như trước khi tầng này được thêm.
    """
    print("\n8. Ràng buộc mềm trên bộ quy tắc thật")
    day= date(2026, 10, 20)
    uid = "00000004-0000-0000-0000-000000000000"

    cn = connect(db)
    try:
        bon_benh = ["Gút", "Tăng huyết áp", "Đái tháo đường", "Rối loạn mỡ máu"]
        dk = conditions_by_name(cn, bon_benh, severity="severe")
        lm = soft_rules(cn, dk)
        kiem(len(lm) == 7, f"bốn bệnh cho 7 luật mềm, được {len(lm)}")

        theo = soft_rules_by_scope(lm)
        kiem(
            len(theo["per_serving"]) == 4,
            f"4 luật theo suất, được {len(theo['per_serving'])}",
        )
        kiem(len(theo["per_meal"]) == 1, f"1 luật theo bữa, được {len(theo['per_meal'])}")
        kiem(len(theo["per_day"]) == 2, f"2 luật theo ngày, được {len(theo['per_day'])}")

        chua = unenforced_rules(lm)
        kiem(
            [l.scope for l in chua] == ["per_meal"],
            f"đúng 1 luật chưa có tầng thi hành, được {[l.scope for l in chua]}",
        )
        kiem(
            chua and chua[0].nutrient == "carbs_g" and chua[0].condition == "Đái tháo đường",
            "luật chưa thi hành là bột đường ≤ 60 g mỗi bữa của Đái tháo đường",
        )

        # `penalty` là hệ số nhân: mức nặng phải có hệ số NHỎ hơn mức nhẹ.
        natri = sorted(
            [l for l in theo["per_serving"] if l.nutrient == "sodium_mg"],
            key=lambda l: l.threshold,
        )
        kiem(len(natri) == 2, f"hai dải natri theo suất, được {len(natri)}")
        if len(natri) == 2:
            nutrient, long_ = natri[0], natri[1]
            kiem(
                nutrient.threshold < long_.threshold and nutrient.penalty < long_.penalty,
                f"dải chặt hơn ({nutrient.threshold:.0f} mg) có hệ số nhỏ hơn "
                f"({nutrient.penalty} < {long_.penalty}) — hệ số NHÂN, không "
                f"phải lượng trừ",
            )

        # ── Áp lên danh mục thật ──
        with cn.cursor() as cur:
            cur.execute(
                "SELECT f.id, f.name, fn.sodium_mg, fn.purine_mg, fn.fat_g "
                "FROM foods f JOIN food_nutrition fn ON fn.food_id = f.id "
                "WHERE f.is_active = 1 ORDER BY f.name"
            )
            tat_ca = list(cur.fetchall())

        bi_tru = 0
        missing = 0
        he_so_nho_nhat = 1.0
        for d in tat_ca:
            so_do = {
                "sodium_mg": d["sodium_mg"],
                "purine_mg": d["purine_mg"],
                "fat_g": d["fat_g"],
            }
            r = penalty(so_do, theo["per_serving"])
            kiem_am_tham = 0.0 < r.factor <= 1.0
            if not kiem_am_tham:
                kiem(False, f"{d['name']}: hệ số {r.factor} ra ngoài (0, 1]")
                return
            if r.is_penalised:
                bi_tru += 1
            if r.missing_data:
                missing += 1
            he_so_nho_nhat = min(he_so_nho_nhat, r.factor)

        kiem(True, f"mọi hệ số của 318 món nằm trong (0, 1]")
        kiem(
            bi_tru > 0,
            f"{bi_tru} món bị trừ điểm vì ràng buộc mềm — nếu bằng 0 thì "
            f"tầng mềm không làm gì cả",
        )
        kiem(
            missing > 0,
            f"{missing} món thiếu số liệu ở chất có luật mềm — không bị phạt, "
            f"nhưng được ghi lại",
        )
        kiem(
            he_so_nho_nhat < 0.4,
            f"có món vướng nhiều nhóm luật nên hệ số xuống {he_so_nho_nhat:.3f} "
            f"— thấp hơn hệ số nặng nhất của một nhóm (0,400)",
        )

        # ── Bất biến: luật mềm KHÔNG loại món ──
        chi_cung = conditions_by_name(cn, ["Gút"], severity="mild")
        kiem(
            len(allowed_foods(cn, conditions=chi_cung)) == 318,
            "Gút mức nhẹ: luật mềm purin ≤ 150 mg/suất KHÔNG loại món nào",
        )
        kiem(
            len(exclusion_reasons(cn, conditions=chi_cung)) == 0,
            "và cũng không sinh ra lý do bị loại nào",
        )
        bon = allowed_foods(cn, conditions=dk)
        kiem(
            len(bon) == len(allowed_foods(cn, conditions=conditions_by_name(
                cn, ["Gút", "Tăng huyết áp"], severity="severe"))),
            "thêm Đái tháo đường và Rối loạn mỡ máu — toàn luật mềm — không "
            "làm tập ứng viên nhỏ đi",
        )

        # ── Hạn mức MỀM theo ngày ──
        with cn.cursor() as cur:
            for cid, muc in ((6, "severe"),):  # Đái tháo đường
                cur.execute(
                    "SELECT id FROM conditions WHERE name_vi = %s",
                    ("Đái tháo đường",),
                )
                cid = cur.fetchone()["id"]
                cur.execute(
                    "INSERT INTO user_conditions (id, user_id, condition_id, "
                    "severity, created_at) VALUES (UUID(), %s, %s, %s, NOW())",
                    (uid, cid, muc),
                )
            # Một món rất ngọt, ăn hai suất, để vượt hẳn mốc 25 g/ngày.
            cur.execute(
                "SELECT f.id, f.name, fn.sugar_g FROM foods f "
                "JOIN food_nutrition fn ON fn.food_id = f.id "
                "WHERE f.is_active = 1 AND fn.sugar_g IS NOT NULL "
                "ORDER BY fn.sugar_g DESC LIMIT 1"
            )
            ngot = cur.fetchone()
            cur.execute(
                "INSERT INTO food_diary (id, user_id, food_id, ate_on, "
                "meal_type, portion_multiplier, created_at) "
                "VALUES (UUID(), %s, %s, %s, 'snack', 2.00, NOW())",
                (uid, ngot["id"], day),
            )
        cn.commit()

        dk_dtd = conditions_for_user(cn, uid)
        tt = status(cn, uid, conditions=dk_dtd, day=day)
        kiem(len(tt.soft_limits()) == 1, f"một ngưỡng mềm theo ngày, được {len(tt.soft_limits())}")
        kiem(len(tt.hard_limits()) == 0, "Đái tháo đường không có ngưỡng CỨNG theo ngày")

        mem = tt.soft_limits()[0]
        gan(mem.threshold, 25.0, "mốc đường 25 g/ngày")
        gan(mem.penalty or 0.0, 0.600, "hệ số phạt 0,600 đi theo ngưỡng")
        gan(
            mem.eaten,
            float(ngot["sugar_g"]) * 2,
            f"đã ăn 2 suất {ngot['name']}",
        )
        kiem(
            mem.is_exceeded,
            f"{mem.used:.1f} g đường vượt mốc 25 g — vào `exceeded_recommendations`",
        )
        kiem(
            [h.nutrient for h in tt.exceeded_recommendations()] == ["sugar_g"],
            "`exceeded_recommendations` nêu đúng chất",
        )

        # Và đây là điều phải giữ: vượt khuyến cáo KHÔNG chặn món nào.
        kq = classify_foods(tt, tat_ca)
        kiem(
            kq.does_not_fit == {} and kq.undecidable == {},
            f"vượt mốc đường mềm không chặn món nào "
            f"({len(kq.does_not_fit)} bị chặn) — mềm là trừ điểm, không phải cấm",
        )
        kiem(
            tt.tightest_limit("sugar_g") is None,
            "`tightest_limit` chỉ trả ngưỡng CỨNG, nên đường trả None",
        )
    finally:
        cn.close()


def kiem_muc_tin_cay_sql(db: str) -> None:
    """Mức tin cậy trên bộ quy tắc thật — và ràng buộc giữ nó khỏi bị lạm dụng.

    Điều quan trọng nhất ở đây không phải mấy con số đếm được, mà là
    `chk_rule_evidence`: không có nó thì một ngưỡng dinh dưỡng có thể tự
    khai `definitional` và thoát khỏi mọi yêu cầu dẫn nguồn.
    """
    print("\n9. Mức tin cậy của ngưỡng trên bộ quy tắc thật")

    cn = connect(db)
    try:
        with cn.cursor() as cur:
            cur.execute(
                "SELECT evidence_level e, COUNT(*) n FROM condition_rules "
                "GROUP BY e"
            )
            dem = {d["e"]: int(d["n"]) for d in cur.fetchall()}

        kiem(sum(dem.values()) == 20, f"20 quy tắc, được {sum(dem.values())}")
        kiem(
            dem.get("definitional") == 9,
            f"9 quy tắc nhãn là `definitional`, được {dem.get('definitional')}",
        )
        kiem(
            dem.get("published") == 3,
            f"3 ngưỡng lấy nguyên từ nguồn, được {dem.get('published')}",
        )
        kiem(
            dem.get("derived") == 6,
            f"6 ngưỡng suy ra kèm giả thiết, được {dem.get('derived')}",
        )
        kiem(
            dem.get("unsupported") == 2,
            f"2 ngưỡng không có nguồn đang hiệu lực, được {dem.get('unsupported')}",
        )

        # Mọi quy tắc nhãn phải là `definitional`, và ngược lại.
        with cn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) n FROM condition_rules "
                "WHERE (rule_type IN ('exclude_tag','require_tag') "
                "       AND evidence_level <> 'definitional') "
                "   OR (rule_type = 'nutrient_limit' "
                "       AND evidence_level = 'definitional')"
            )
            excess = int(cur.fetchone()["n"])
        kiem(excess == 0, f"không quy tắc nào lệch loại ↔ mức, được {excess}")

        # Ràng buộc CHECK phải thực sự chặn, không chỉ là chú thích.
        with cn.cursor() as cur:
            try:
                cur.execute(
                    "UPDATE condition_rules SET evidence_level = 'definitional' "
                    "WHERE rule_type = 'nutrient_limit' LIMIT 1"
                )
                chan = False
            except pymysql.err.OperationalError:
                chan = True
            except pymysql.err.IntegrityError:
                chan = True
        cn.rollback()
        kiem(
            chan,
            "`chk_rule_evidence` CHẶN một ngưỡng tự khai `definitional` — "
            "không có ràng buộc này thì nó thoát mọi yêu cầu dẫn nguồn",
        )

        # Ba ngưỡng `published` phải là đúng ba cái có nguồn trong `note`.
        with cn.cursor() as cur:
            cur.execute(
                "SELECT co.name_vi b, cr.nutrient, cr.threshold, cr.note "
                "FROM condition_rules cr "
                "JOIN conditions co ON co.id = cr.condition_id "
                "WHERE cr.evidence_level = 'published' "
                "ORDER BY co.name_vi, cr.nutrient"
            )
            pub = list(cur.fetchall())
        kiem(
            all(
                "WHO" in d["note"] or "Nhật Bản" in d["note"] or "KDIGO" in d["note"]
                for d in pub
            ),
            "mọi ngưỡng `published` nêu được tên nguồn trong `note`",
        )
        kiem(
            all(float(d["threshold"]) in (400.0, 2000.0) for d in pub),
            "ba ngưỡng đó là purin 400 mg và natri 2 000 mg (hai bệnh)",
        )

        # Hai ngưỡng `unsupported`: `note` phải nói rõ vì sao.
        with cn.cursor() as cur:
            cur.execute(
                "SELECT cr.note FROM condition_rules cr "
                "WHERE cr.evidence_level = 'unsupported'"
            )
            un = [d["note"] for d in cur.fetchall()]
        kiem(
            any("BỊ RÚT" in n for n in un),
            "một ngưỡng `unsupported` vì đã BỊ RÚT khỏi hướng dẫn",
        )
        kiem(
            any("chưa xác minh" in n for n in un),
            "ngưỡng còn lại vì CHƯA ai tra — hai lý do khác nhau, cùng một "
            "cách trình bày",
        )

        # Mức đi tới được cả ba lớp đọc nó.
        dk = conditions_by_name(
            cn, ["Gút", "Tăng huyết áp", "Rối loạn mỡ máu"], severity="severe"
        )
        ly = exclusion_reasons(cn, conditions=dk)
        kiem(
            all(
                l.evidence_level == "definitional"
                for v in ly.values()
                for l in v
            ),
            "mọi lý do bị loại hiện tại đều từ quy tắc nhãn → `definitional`",
        )
        lm = soft_rules(cn, dk)
        kiem(
            {l.evidence_level for l in lm} == {"derived", "unsupported"},
            f"luật mềm có hai mức, được {sorted({l.evidence_level for l in lm})}",
        )
        tt = status(cn, "khong-ai", conditions=dk, day=date(2026, 11, 7))
        cung = [h for h in tt.limits if h.is_hard]
        kiem(
            cung and all(h.is_citable for h in cung),
            "mọi ngưỡng CỨNG theo ngày đều dẫn được nguồn — đúng như phải "
            "thế: chặn món thì phải có nguồn",
        )
        mem = [h for h in tt.limits if not h.is_hard]
        kiem(
            mem and not any(h.is_citable for h in mem),
            "còn ngưỡng MỀM thì không ngưỡng nào dẫn được nguồn",
        )
    finally:
        cn.close()


def main() -> int:
    use_utf8()
    bo = argparse.ArgumentParser(description=__doc__)
    bo.add_argument("--goc", default="nutrition_rec", help="CSDL nguồn để sao món")
    bo.add_argument("--db", default=TEN_CSDL_THU, help="tên CSDL thử")
    bo.add_argument("--giu", action="store_true", help="không xóa CSDL thử khi xong")
    t = bo.parse_args()

    if t.db == t.goc:
        print("CSDL thử không được trùng CSDL nguồn.", file=sys.stderr)
        return 1

    print("Kiểm đầu-cuối phần học máy")
    print("=" * 62)
    print(f"Dựng CSDL thử {t.db!r} từ {t.goc!r}…")
    try:
        dung_csdl_thu(t.goc, t.db)
    except pymysql.Error as e:
        print(f"Không dựng được CSDL thử: {e}", file=sys.stderr)
        return 1

    try:
        cn = connect(t.db)
        try:
            so_tin_hieu = dung_nguoi_dung(cn)
        finally:
            cn.close()
        print(
            f"Đã dựng {len(so_tin_hieu)} người dùng giả, "
            f"nhãn NGẪU NHIÊN (xem phần đầu tệp)."
        )

        kiem_nhap_phieu(t.db)
        kiem_duong_ong(t.db, so_tin_hieu)
        kiem_phuc_vu(t.db, so_tin_hieu)
        kiem_han_muc_ngay(t.db)
        kiem_ly_do_loai_sql(t.db)
        kiem_hinh_phat_mem_sql(t.db)
        kiem_muc_tin_cay_sql(t.db)
    finally:
        if t.giu:
            print(f"\nGiữ lại CSDL {t.db!r} theo --giu.")
        else:
            xoa_csdl_thu(t.db)
            print(f"\nĐã xóa CSDL thử {t.db!r}.")

    print("=" * 62)
    if _loi:
        print(f"{_dat} mục đạt, {len(_loi)} MỤC SAI:")
        for x in _loi:
            print("  -", x)
        return 1
    print(f"Tất cả {_dat} mục kiểm đều đạt.")
    print(
        "Lưu ý: mọi con số ở trên là của dữ liệu giả, KHÔNG phải kết quả "
        "thực nghiệm."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
