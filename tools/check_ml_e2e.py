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
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402

from ml.build_dataset import main as chay_dung_tap  # noqa: E402
from ml.db import ket_noi, in_utf8  # noqa: E402
from ml.evaluate import main as chay_danh_gia  # noqa: E402
from ml.f1_filter import dieu_kien_theo_ten  # noqa: E402
from ml.features import FEATURE_VERSION, KhongGianDacTrung, nap_mon  # noqa: E402
from ml.rocchio import dung_ho_so, giai_doan  # noqa: E402
from ml.serve import goi_y, nap_mo_hinh_hoat_dong  # noqa: E402
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
#: `giai_doan`: 0 → cold, 1–29 → content, 30–100 → hybrid, >100 → ml.
SO_VUOT = [0, 12, 12, 18, 45, 45, 60, 60, 120, 150, 25, 25]

_dat = 0
_loi: list[str] = []


def kiem(dieu_kien: bool, mo_ta: str) -> None:
    global _dat
    if dieu_kien:
        _dat += 1
        print(f"  ✓ {mo_ta}")
    else:
        _loi.append(mo_ta)
        print(f"  ✗ {mo_ta}")


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
    cn = ket_noi(goc, dict_cursor=True)
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
    cn = ket_noi("information_schema", dict_cursor=True)
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
    mon, _ = nap_mon(cn)
    kg = KhongGianDacTrung.tu_mon(mon)
    mon_theo_id = {m.id: m for m in mon}
    fid = sorted(mon_theo_id)
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
                cap.append((mon_theo_id[f], hd))

            # Vài tín hiệu khác nguồn, nhãn cũng ngẫu nhiên.
            for f in rng.sample(fid, min(4, so) if so else 0):
                cur.execute(
                    "INSERT INTO feedbacks (id, user_id, food_id, rating, "
                    "created_at) VALUES (UUID(), %s, %s, %s, %s)",
                    (uid, f, rng.randint(1, 5),
                     goc + timedelta(days=5, seconds=u * 60)),
                )

            ho_so = dung_ho_so(kg, cap)
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
                    giai_doan(ho_so.n_signals),
                    0,
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

    cn = ket_noi(db)
    try:
        mon, _ = nap_mon(cn)
    finally:
        cn.close()
    kg = KhongGianDacTrung.tu_mon(mon)
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
        ten: str, *, lua_chon=None, thong_tin_them="", so_mon: int = 40
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
            for i, m in enumerate(bo[:so_mon], start=1):
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

    cn = ket_noi(db)
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
    cn = ket_noi(db)
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

    cn = ket_noi(db)
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

    cn = ket_noi(db)
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
             "--kich-hoat", "logistic_regression"]
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
    cn = ket_noi(db)
    try:
        theo_gd: dict[str, str] = {}
        for uid, n in sorted(so_tin_hieu.items(), key=lambda kv: kv[1]):
            theo_gd.setdefault(giai_doan(n), uid)

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
            kq = goi_y(cn, uid, gioi_han=5)
            kiem(
                kq.stage == gd and kq.generation_source == mong_doi_nguon[gd],
                f"{gd}: generation_source = {kq.generation_source}",
            )
            kiem(
                len(kq.ung_vien) == 5,
                f"{gd}: trả về 5 ứng viên hàng đầu",
            )
            kiem(
                all(0.0 <= u.diem <= 1.0 for u in kq.ung_vien),
                f"{gd}: mọi điểm nằm trong [0, 1]",
            )
            kiem(
                all(
                    kq.ung_vien[i].diem >= kq.ung_vien[i + 1].diem
                    for i in range(len(kq.ung_vien) - 1)
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
                    all(u.diem_ml is None for u in kq.ung_vien),
                    "cold: không gọi mô hình chút nào",
                )
            if gd == "hybrid":
                kiem(0 < kq.alpha < 1, f"hybrid: 0 < α = {kq.alpha:.3f} < 1")
            if gd == "ml":
                kiem(kq.alpha == 1.0, "ml: α = 1")

        # ── Bộ lọc F1 thật sự cắt ứng viên ──
        uid = theo_gd["content"]
        truoc = goi_y(cn, uid, gioi_han=1000).so_mon_sau_f1
        dk = dieu_kien_theo_ten(cn, ["Ăn thuần chay", "Dị ứng đậu nành"], "severe")
        with cn.cursor() as cur:
            for d in dk:
                cur.execute(
                    "INSERT INTO user_conditions (id, user_id, condition_id, "
                    "severity) VALUES (UUID(), %s, %s, 'severe')",
                    (uid, d.condition_id),
                )
        cn.commit()
        sau = goi_y(cn, uid, gioi_han=1000).so_mon_sau_f1
        kiem(
            sau < truoc,
            f"thêm bệnh lý thì F1 cắt ứng viên: {truoc} → {sau} món",
        )

        # Món đã dùng trong ngày bị loại.
        kq = goi_y(cn, uid, gioi_han=3)
        da_dung = [u.mon.id for u in kq.ung_vien[:2]]
        kq2 = goi_y(cn, uid, gioi_han=3, mon_da_dung=da_dung)
        kiem(
            all(u.mon.id not in da_dung for u in kq2.ung_vien),
            "món đã dùng trong ngày không xuất hiện lại",
        )

        print("\n5. Hạ cấp có công bố")
        uid_ml = theo_gd["ml"]
        with cn.cursor() as cur:
            cur.execute("UPDATE ml_models SET is_active = 0")
        cn.commit()
        kq = goi_y(cn, uid_ml, gioi_han=3)
        kiem(
            kq.stage == "content" and kq.generation_source == "content_based",
            f"không có mô hình → lùi về content_based (được {kq.stage})",
        )
        kiem(
            any("hạ về Giai đoạn 1" in c for c in kq.canh_bao),
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
        mon, _ = nap_mon(cn)
        kg = KhongGianDacTrung.tu_mon(mon)
        mh, ly_do = nap_mo_hinh_hoat_dong(cn, kg)
        kiem(
            mh is None and ly_do is not None and "cùng is_active" in ly_do,
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
        kq = goi_y(cn, uid_ml, gioi_han=3)
        kiem(
            kq.stage == "cold" and kq.n_signals == 0,
            f"hồ sơ sai phiên bản → lùi về Giai đoạn 0 (được {kq.stage})",
        )
        kiem(
            any("phiên bản đặc trưng" in c for c in kq.canh_bao),
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
        kq = goi_y(cn, uid_ml, gioi_han=3)
        kiem(
            kq.stage == "cold",
            f"hồ sơ thiếu chiều → lùi về Giai đoạn 0 (được {kq.stage})",
        )
        kiem(
            any("chiều" in c for c in kq.canh_bao),
            "việc bỏ qua hồ sơ thiếu chiều được công bố",
        )
    finally:
        cn.close()


def main() -> int:
    in_utf8()
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
        cn = ket_noi(t.db)
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
