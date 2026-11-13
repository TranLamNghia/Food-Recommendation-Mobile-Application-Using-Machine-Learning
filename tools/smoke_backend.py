#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Thử đầu-cuối 9 endpoint của đợt 1 và 2, trên CSDL thật.

Đây là phép thử TÍCH HỢP, không phải unit test: nó gọi HTTP thật, ghi vào
MySQL thật, và đọc lại. Vì sao cần cả hai loại — `tools/check_be_parity.py`
kiểm Bước 1 bằng số thuần, không cần máy chủ; tệp này kiểm những thứ chỉ sai
khi có CSDL và có mạng: ánh xạ tên cột, kiểu dữ liệu, giao dịch, vỏ lỗi, thứ
tự claim trong JWT.

Mỗi lần chạy tạo một tài khoản mới với email ngẫu nhiên rồi XÓA nó ở cuối,
nên chạy lại nhiều lần không làm phình CSDL. `ON DELETE CASCADE` của 11 khóa
ngoại tới `users` dọn hết phần còn lại.

Chạy (cần backend đang chạy):
    python tools/run_backend.py          # cửa sổ khác
    python tools/smoke_backend.py
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request
import uuid
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import _env  # noqa: E402

GOC = "http://localhost:5000/api/v1"

_loi: list[str] = []
_so_kiem = 0


def goi(method: str, duong: str, than=None, token: str | None = None):
    """Gọi API, trả `(mã HTTP, thân đã giải mã JSON hoặc None)`."""
    url = GOC + duong
    data = json.dumps(than).encode() if than is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return e.code, {"_raw": raw.decode("utf-8", "replace")[:300]}


def kiem(nhan: str, dat: bool, chi_tiet: str = "") -> bool:
    global _so_kiem
    _so_kiem += 1
    print(f"  {'[ok]' if dat else '[SAI]'} {nhan}"
          + (f"  {chi_tiet}" if chi_tiet and not dat else ""))
    if not dat:
        _loi.append(f"{nhan} — {chi_tiet}" if chi_tiet else nhan)
    return dat


def bang(nhan: str, duoc, mong) -> bool:
    return kiem(nhan, duoc == mong, f"được {duoc!r}, mong {mong!r}")


def ma_loi(than) -> str | None:
    if isinstance(than, dict):
        return (than.get("error") or {}).get("code")
    return None


def _ket_noi():
    import pymysql
    return pymysql.connect(
        host=_env.get("MYSQL_HOST", "localhost"),
        port=int(_env.get("MYSQL_PORT", "3306")),
        user=_env.require("MYSQL_USER"),
        password=_env.require("MYSQL_PASSWORD"),
        database=_env.require("MYSQL_DATABASE"),
        charset="utf8mb4",
    )


def sql(sentence: str, tham=()):
    """Chạy một câu SQL, trả các dòng. Dùng để dựng trạng thái mà API
    không cho dựng — ví dụ khóa một tài khoản."""
    cn = _ket_noi()
    try:
        with cn.cursor() as cur:
            cur.execute(sentence, tham)
            dong = cur.fetchall()
        cn.commit()
        return dong
    finally:
        cn.close()


def xoa_tai_khoan(*email: str) -> None:
    """Dọn các tài khoản thử. `ON DELETE CASCADE` lo phần còn lại."""
    import pymysql
    cn = pymysql.connect(
        host=_env.get("MYSQL_HOST", "localhost"),
        port=int(_env.get("MYSQL_PORT", "3306")),
        user=_env.require("MYSQL_USER"),
        password=_env.require("MYSQL_PASSWORD"),
        database=_env.require("MYSQL_DATABASE"),
        charset="utf8mb4",
    )
    try:
        with cn.cursor() as cur:
            for e in email:
                cur.execute("DELETE FROM users WHERE email = %s", (e,))
        cn.commit()
    finally:
        cn.close()


def main(argv: list[str] | None = None) -> int:
    _env.use_utf8()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--giu", action="store_true",
                    help="không xóa tài khoản thử, để soi trong CSDL")
    ts = ap.parse_args(argv)

    email = f"smoke-{uuid.uuid4().hex[:12]}@example.test"
    mat_khau = "MatKhau123"
    print(f"Thử đầu-cuối trên {GOC}")
    print(f"Tài khoản thử: {email}")
    print("=" * 72)

    # ── 7.1.1 Đăng ký ────────────────────────────────────────────────────
    print("\n7.1.1  POST /auth/register")
    ma, than = goi("POST", "/auth/register", {
        "email": email, "password": mat_khau, "displayName": "Người Thử"})
    bang("201 Created", ma, 201)
    if ma != 201:
        print(f"\nKhông đăng ký được, dừng: {than}")
        return 1

    token = than["accessToken"]
    refresh = than["refreshToken"]
    uid = than["user"]["id"]
    bang("tokenType là Bearer", than["tokenType"], "Bearer")
    bang("expiresIn 3600 giây (đặc tả §2.4)", than["expiresIn"], 3600)
    kiem("user.id là UUID 36 ký tự", len(uid) == 36, f"dài {len(uid)}")
    bang("email đã chuẩn hóa chữ thường", than["user"]["email"], email)
    bang("onboardingCompletedAt là null",
         than["user"]["onboardingCompletedAt"], None)
    kiem("avatarUrl có mặt và là null (§2.3: null, không bỏ trường)",
         "avatarUrl" in than["user"] and than["user"]["avatarUrl"] is None)

    # `sub` phải là UUID, không phải số nguyên — §2.3.
    import base64
    phan = token.split(".")[1]
    phan += "=" * (-len(phan) % 4)
    tai = json.loads(base64.urlsafe_b64decode(phan))
    bang("JWT `sub` là users.id (UUID)", tai.get("sub"), uid)
    bang("JWT `role` là user", tai.get("role"), "user")
    bang("JWT `onboarded` là false", tai.get("onboarded"), "false")

    # ── Đăng ký trùng email ──────────────────────────────────────────────
    print("\n7.1.1  đăng ký lại cùng email")
    ma, than = goi("POST", "/auth/register", {
        "email": email.upper(), "password": mat_khau, "displayName": "Khác"})
    bang("409", ma, 409)
    bang("EMAIL_ALREADY_EXISTS (hoa thường không làm lệch)",
         ma_loi(than), "EMAIL_ALREADY_EXISTS")

    # ── Lỗi validation phải ra đúng vỏ §2.5 ──────────────────────────────
    print("\n§2.5  vỏ lỗi validation")
    ma, than = goi("POST", "/auth/register", {
        "email": "khong-phai-email", "password": "ngan", "displayName": "a"})
    bang("400", ma, 400)
    bang("VALIDATION_FAILED", ma_loi(than), "VALIDATION_FAILED")
    chi_tiet = (than.get("error") or {}).get("details") or []
    truong = {d.get("field") for d in chi_tiet}
    kiem("details nêu từng trường sai, tên camelCase",
         {"email", "password", "displayName"} <= truong, f"thấy {truong}")
    kiem("có traceId", bool((than.get("error") or {}).get("traceId")))

    # ── Mật khẩu dài hơn 72 byte phải bị TỪ CHỐI, không bị cắt ───────────
    #
    # BCrypt chỉ dùng 72 byte đầu và lặng lẽ bỏ phần còn lại, nên không có
    # chặn trên thì hai mật khẩu trùng 72 byte đầu đăng nhập được lẫn nhau.
    # Chặn đếm theo BYTE: 30 chữ "ậ" là 30 ký tự nhưng 90 byte UTF-8, nên một
    # `MaxLength(72)` theo ký tự sẽ cho nó đi qua rồi bị cắt.
    print("\n§7.1.1  chặn trên mật khẩu tính theo byte UTF-8")
    dai_ky_tu = "Aa1" + "ậ" * 30          # 33 ký tự · 93 byte
    ma, than = goi("POST", "/auth/register", {
        "email": f"dai-{email}", "password": dai_ky_tu,
        "displayName": "Thử byte"})
    bang("400 với 33 ký tự nhưng 93 byte", ma, 400)
    bang("VALIDATION_FAILED", ma_loi(than), "VALIDATION_FAILED")
    chi_tiet = (than.get("error") or {}).get("details") or []
    kiem("details chỉ đúng trường password",
         {d.get("field") for d in chi_tiet} == {"password"},
         f"thấy {[d.get('field') for d in chi_tiet]}")
    kiem("93 byte > 72 — đúng là bài kiểm có nghĩa",
         len(dai_ky_tu.encode("utf-8")) > 72
         and len(dai_ky_tu) <= 72,
         f"{len(dai_ky_tu)} ký tự / "
         f"{len(dai_ky_tu.encode('utf-8'))} byte")

    # Đúng 72 byte thì PHẢI đi qua — chặn trên không được chặn quá tay.
    ma, _ = goi("POST", "/auth/register", {
        "email": f"vua-{email}", "password": "Aa1" + "b" * 69,
        "displayName": "Thử byte"})
    bang("201 với đúng 72 byte", ma, 201)

    # ── 7.1.2 Đăng nhập ──────────────────────────────────────────────────
    print("\n7.1.2  POST /auth/login")
    ma, than = goi("POST", "/auth/login",
                   {"email": email, "password": mat_khau})
    bang("200", ma, 200)
    kiem("trả accessToken mới", bool(than and than.get("accessToken")))

    ma, than = goi("POST", "/auth/login",
                   {"email": email, "password": "SaiMatKhau9"})
    bang("401 khi sai mật khẩu", ma, 401)
    bang("INVALID_CREDENTIALS", ma_loi(than), "INVALID_CREDENTIALS")

    ma, than = goi("POST", "/auth/login",
                   {"email": "khong-ton-tai@example.test",
                    "password": mat_khau})
    bang("401 khi email không tồn tại", ma, 401)
    bang("cùng mã lỗi — không lộ email nào đã đăng ký",
         ma_loi(than), "INVALID_CREDENTIALS")

    # ── 7.1.4 Thông tin tài khoản ────────────────────────────────────────
    print("\n7.1.4  GET /auth/me")
    ma, than = goi("GET", "/auth/me", token=token)
    bang("200", ma, 200)
    bang("hasHealthProfile false khi chưa khai",
         than and than.get("hasHealthProfile"), False)
    bang("preferenceStage cold khi chưa có tín hiệu",
         than and than.get("preferenceStage"), "cold")

    ma, than = goi("GET", "/auth/me")
    bang("401 khi không có token", ma, 401)
    ma, than = goi("GET", "/auth/me", token="rac.rac.rac")
    bang("401 TOKEN_INVALID khi token hỏng", ma_loi(than), "TOKEN_INVALID")

    # ── 7.2.3 Hạn mức trước khi có hồ sơ ─────────────────────────────────
    print("\n7.2.3  GET /profile/nutrition-targets khi chưa có hồ sơ")
    ma, than = goi("GET", "/profile/nutrition-targets", token=token)
    bang("409", ma, 409)
    bang("PROFILE_REQUIRED, không phải 404", ma_loi(than),
         "PROFILE_REQUIRED")

    print("\n7.2.1  GET /profile khi chưa có hồ sơ")
    ma, than = goi("GET", "/profile", token=token)
    bang("404 NOT_FOUND", (ma, ma_loi(than)), (404, "NOT_FOUND"))

    # ── 7.2.2 Tạo hồ sơ ──────────────────────────────────────────────────
    print("\n7.2.2  PUT /profile — tạo mới")
    # Ngày sinh SUY TỪ HÔM NAY để tuổi luôn đúng 22, không gán cứng
    # `2004-11-14` như ví dụ trong đặc tả.
    #
    # Bản đầu của tệp này gán cứng ngày đó và mong `age: 22`, rồi báo sai 12
    # phép kiểm — mà mã backend hoàn toàn đúng: hôm chạy là 08/11, sinh nhật
    # 14/11 chưa tới, nên tuổi là 21 và BMR là 1660 chứ không phải 1655. Một
    # phép thử đổi kết quả vào đúng một ngày trong năm thì không thử được gì.
    hom_nay = date.today()
    ngay_sinh = date(hom_nay.year - 22, hom_nay.month, hom_nay.day)
    ho_so = {"gender": "male", "dateOfBirth": ngay_sinh.isoformat(),
             "heightCm": 172.0, "weightKg": 68.5,
             "activityLevel": "moderate", "goal": "maintain"}
    ma, than = goi("PUT", "/profile", ho_so, token=token)
    bang("201 Created lần đầu", ma, 201)
    if ma not in (200, 201):
        print(f"\nKhông tạo được hồ sơ, dừng: {than}")
        if not ts.giu:
            xoa_tai_khoan(email)
        return 1

    hm = than["nutritionTargets"]
    # Đúng bộ số của ví dụ ở §7.2.3, sau khi sửa lỗi số học 1660 -> 1655.
    bang("bmi 23.15", float(hm["bmi"]), 23.15)
    # 23.15 vượt ngưỡng 23 của WHO 2004 cho người châu Á. Với ngưỡng quốc
    # tế 25/30 thì nó là `normal` — và đó là con số bản đặc tả cũ ghi.
    bang("bmiCategory overweight (ngưỡng châu Á 23/25)",
         hm["bmiCategory"], "overweight")
    bang("bmrKcal 1655 (không phải 1660 như bản đặc tả cũ)",
         hm["bmrKcal"], 1655)
    bang("tdeeKcal 2565", hm["tdeeKcal"], 2565)
    bang("activityFactor 1.550", float(hm["activityFactor"]), 1.55)
    bang("dailyCaloriesTarget 2565", hm["dailyCaloriesTarget"], 2565)
    bang("goalAdjustmentKcal 0 với maintain", hm["goalAdjustmentKcal"], 0)
    mt = hm["macroTargets"]
    bang("macro % đọc từ mặc định lược đồ 15/60/25",
         (mt["proteinPct"], mt["carbsPct"], mt["fatPct"]), (15, 60, 25))
    bang("proteinG 96.2", float(mt["proteinG"]), 96.2)
    bang("carbsG 384.8", float(mt["carbsG"]), 384.8)
    bang("fatG 71.3", float(mt["fatG"]), 71.3)
    bua = {m["mealType"]: m for m in hm["mealDistribution"]}
    bang("4 bữa", sorted(bua), ["breakfast", "dinner", "lunch", "snack"])
    bang("tỷ lệ bữa là điểm giữa khoảng §3.1",
         [float(bua[k]["pct"]) for k in
          ("breakfast", "lunch", "dinner", "snack")],
         [27.5, 37.5, 27.5, 7.5])
    bang("kcal từng bữa", [bua[k]["caloriesKcal"] for k in
                           ("breakfast", "lunch", "dinner", "snack")],
         [705, 962, 705, 192])
    kiem("formula.expression kết thúc bằng = 1655",
         hm["formula"]["expression"].endswith("= 1655"),
         hm["formula"]["expression"])
    bang("profile.age 22", than["profile"]["age"], 22)

    print("\n7.2.2  PUT /profile — gọi lại")
    ma, than = goi("PUT", "/profile", ho_so, token=token)
    bang("200, không 201", ma, 200)

    print("\n7.2.2  PUT /profile — số ngoài khoảng")
    ma, than = goi("PUT", "/profile", {**ho_so, "heightCm": 300},
                   token=token)
    bang("400 VALIDATION_FAILED", (ma, ma_loi(than)),
         (400, "VALIDATION_FAILED"))
    ma, than = goi("PUT", "/profile", {**ho_so, "gender": "nam"},
                   token=token)
    bang("400 khi enum sai", (ma, ma_loi(than)),
         (400, "VALIDATION_FAILED"))
    ma, than = goi("PUT", "/profile",
                   {**ho_so,
                    "dateOfBirth": date(hom_nay.year - 5, 1, 1).isoformat()},
                   token=token)
    bang("400 khi tuổi dưới 13", (ma, ma_loi(than)),
         (400, "VALIDATION_FAILED"))

    # ── Mục tiêu giảm cân: ràng buộc an toàn không xuống dưới BMR ───────
    print("\n7.2.2  lose_weight — hạn mức không được dưới BMR")
    ma, than = goi("PUT", "/profile",
                   {**ho_so, "goal": "lose_weight",
                    "activityLevel": "sedentary"}, token=token)
    hm2 = than["nutritionTargets"]
    kiem("dailyCaloriesTarget >= bmrKcal",
         hm2["dailyCaloriesTarget"] >= hm2["bmrKcal"],
         f"{hm2['dailyCaloriesTarget']} < {hm2['bmrKcal']}")
    # BMR 1655 * 1.2 = 1986; 1986 - 500 = 1486 < 1655 -> kẹp về BMR.
    bang("kẹp đúng về BMR", hm2["dailyCaloriesTarget"], 1655)
    goi("PUT", "/profile", ho_so, token=token)   # trả lại maintain

    # ── 7.2.1 và 7.2.3 sau khi có hồ sơ ─────────────────────────────────
    print("\n7.2.1 / 7.2.3  sau khi có hồ sơ")
    ma, than = goi("GET", "/profile", token=token)
    bang("GET /profile 200", ma, 200)
    bang("conditions là mảng rỗng", than and than.get("conditions"), [])
    ma, than = goi("GET", "/profile/nutrition-targets", token=token)
    bang("GET nutrition-targets 200", ma, 200)
    bang("bmrKcal vẫn 1655", than and than.get("bmrKcal"), 1655)

    ma, than = goi("GET", "/auth/me", token=token)
    bang("hasHealthProfile giờ là true",
         than and than.get("hasHealthProfile"), True)

    # ── 7.2.4 và 7.2.5 bệnh lý ───────────────────────────────────────────
    print("\n7.2.4 / 7.2.5  bệnh lý")
    ma, than = goi("GET", "/profile/conditions", token=token)
    bang("200, mảng thuần", (ma, than), (200, []))

    ma, than = goi("PUT", "/profile/conditions", {"conditions": [
        {"conditionId": 2, "severity": "mild", "note": None},
        {"conditionId": 6, "severity": "severe", "note": "Thử"},
    ]}, token=token)
    bang("200", ma, 200)
    kiem("trả về 2 bệnh lý kèm nameVi tra từ bảng conditions",
         isinstance(than, list) and len(than) == 2
         and all(x.get("nameVi") for x in than), str(than)[:120])

    ma, than = goi("PUT", "/profile/conditions", {"conditions": [
        {"conditionId": 2, "severity": "mild"},
        {"conditionId": 2, "severity": "severe"},
    ]}, token=token)
    bang("400 khi conditionId lặp", (ma, ma_loi(than)),
         (400, "VALIDATION_FAILED"))

    ma, than = goi("PUT", "/profile/conditions", {"conditions": [
        {"conditionId": 99999, "severity": "mild"}]}, token=token)
    bang("400 khi conditionId không tồn tại", (ma, ma_loi(than)),
         (400, "VALIDATION_FAILED"))

    ma, than = goi("GET", "/profile/conditions", token=token)
    kiem("yêu cầu lỗi KHÔNG làm mất danh sách đang có (giao dịch)",
         isinstance(than, list) and len(than) == 2, str(than)[:120])

    ma, than = goi("PUT", "/profile/conditions", {}, token=token)
    bang("400 khi thiếu hẳn trường `conditions`", (ma, ma_loi(than)),
         (400, "VALIDATION_FAILED"))
    ma, than = goi("GET", "/profile/conditions", token=token)
    kiem("thân {} không xóa sạch bệnh lý",
         isinstance(than, list) and len(than) == 2, str(than)[:120])

    ma, than = goi("PUT", "/profile/conditions", {"conditions": []},
                   token=token)
    bang("mảng rỗng thì xóa hết", (ma, than), (200, []))

    # ── 7.1.3 Làm mới token và phát hiện tái dùng ───────────────────────
    print("\n7.1.3  POST /auth/refresh")
    ma, than = goi("POST", "/auth/refresh", {"refreshToken": refresh})
    bang("200", ma, 200)
    refresh2 = than and than.get("refreshToken")
    kiem("refreshToken được xoay vòng (token mới khác token cũ)",
         bool(refresh2) and refresh2 != refresh)
    kiem("phản hồi KHÔNG mang `user` (đặc tả §7.1.3)",
         isinstance(than, dict) and "user" not in than)

    ma, than = goi("POST", "/auth/refresh", {"refreshToken": refresh})
    bang("401 khi nộp lại token đã xoay vòng", ma, 401)
    bang("TOKEN_INVALID", ma_loi(than), "TOKEN_INVALID")

    ma, than = goi("POST", "/auth/refresh", {"refreshToken": refresh2})
    bang("token MỚI cũng bị thu hồi — cả họ bị cắt khi phát hiện tái dùng",
         ma, 401)

    ma, than = goi("POST", "/auth/refresh", {"refreshToken": "khong-co-that"})
    bang("401 với token bịa", (ma, ma_loi(than)), (401, "TOKEN_INVALID"))

    # ── 7.1.3  hai lượt refresh ĐỒNG THỜI cùng một token ────────────────
    #
    # Bản trước ĐỌC dòng token rồi mới GHI, nên hai yêu cầu song song đều
    # thấy `revoked_at IS NULL` và cả hai đều đi qua: hai token sống trong
    # một họ, không bên nào bị coi là tái dùng, và phép phát hiện tái dùng
    # chỉ còn là trang trí. Giờ việc đoạt dòng là MỘT lệnh
    # `UPDATE … WHERE revoked_at IS NULL`, nên đúng một lệnh thắng.
    print("\n7.1.3  hai lượt refresh đồng thời (cuộc đua)")
    ma, than = goi("POST", "/auth/login",
                   {"email": email, "password": mat_khau})
    dua = than and than.get("refreshToken")
    kiem("có token để thử đua", bool(dua))

    # TÁM luồng, không hai. Phép kiểm này là XÁC SUẤT: nó chỉ phân biệt được
    # mã cũ với mã mới khi các yêu cầu THẬT SỰ chồng nhau. Với hai luồng mà
    # chúng tình cờ xếp hàng thì mã CŨ cũng trả [200, 401] — lượt sau thấy
    # dòng đã thu hồi và báo tái dùng — nên bài kiểm sẽ đạt với cả mã hỏng.
    #
    # Tám luồng cùng bắn một token làm chồng lấn gần như chắc chắn, và bất
    # biến cần kiểm là: ĐÚNG MỘT lượt được 200. Mã cũ đọc-rồi-ghi sẽ cho
    # nhiều lượt 200 ngay khi có hai lượt chồng nhau.
    import concurrent.futures as cf
    SO_LUONG = 8
    with cf.ThreadPoolExecutor(max_workers=SO_LUONG) as bom:
        ket = [f.result() for f in [
            bom.submit(goi, "POST", "/auth/refresh", {"refreshToken": dua})
            for _ in range(SO_LUONG)]]
    mas = [m for m, _ in ket]
    kiem(f"đúng MỘT lượt 200 trong {SO_LUONG} lượt đồng thời",
         mas.count(200) == 1, f"mã trả về: {sorted(mas)}")
    kiem("các lượt còn lại đều 401, không 500",
         all(m == 401 for m in mas if m != 200), f"mã trả về: {sorted(mas)}")

    # Và họ token phải bị cắt: lượt thắng cũng không dùng được nữa, vì lượt
    # thua đã kích hoạt thu hồi cả chuỗi.
    thang = next((t for m, t in ket if m == 200), None)
    ma, _ = goi("POST", "/auth/refresh",
                {"refreshToken": (thang or {}).get("refreshToken", "x")})
    bang("token của lượt thắng cũng bị thu hồi theo cả họ", ma, 401)

    # Đếm theo HỌ, không theo bảng. Bài thử này đăng nhập nhiều lần, và mỗi
    # lượt đăng nhập mở một họ token RIÊNG — những họ đó còn sống là đúng.
    # Lần đầu viết phép kiểm này tôi đếm cả bảng và nó báo sai trong khi mã
    # hoàn toàn đúng.
    #
    # Lần theo `replaced_by` từ chính token đã nộp: cả chuỗi phải chết.
    import hashlib
    bam = hashlib.sha256(dua.encode()).hexdigest()
    ho = sql(
        "WITH RECURSIVE chuoi AS ("
        "  SELECT id, replaced_by, revoked_at FROM refresh_tokens"
        "   WHERE token_hash = %s"
        "  UNION ALL"
        "  SELECT t.id, t.replaced_by, t.revoked_at FROM refresh_tokens t"
        "   JOIN chuoi c ON t.id = c.replaced_by)"
        " SELECT COUNT(*), SUM(revoked_at IS NULL) FROM chuoi", (bam,))[0]
    kiem("cả họ token bị cắt, không sót mắt nào",
         ho[0] >= 2 and ho[1] == 0,
         f"{ho[0]} mắt trong chuỗi, {ho[1]} còn sống")

    # ── Múi giờ: DATETIME do Backend ghi phải khớp NOW() của MySQL ───────
    #
    # Backend từng ghi `DateTime.UtcNow`, lệch 7 giờ so với 27 cột
    # `DEFAULT CURRENT_TIMESTAMP` của lược đồ và so với mọi `NOW()` trong
    # tools/*.py. Sắp theo `created_at` khi đó là trộn hai đồng hồ.
    print("\n§2.3  mọi DATETIME theo một đồng hồ: Asia/Ho_Chi_Minh")
    excess = sql(
        "SELECT TIMESTAMPDIFF(MINUTE, created_at, NOW()) FROM users "
        "WHERE email = %s", (email,))[0][0]
    kiem("users.created_at lệch NOW() dưới 5 phút",
         excess is not None and abs(excess) < 5,
         f"lệch {excess} phút — 420 phút nghĩa là vẫn đang ghi UTC")

    # ── Tài khoản bị khóa: bộ lọc toàn cục phải chặn MỌI endpoint ────────
    #
    # `/auth/me` vẫn kiểm `is_active` từ trước, nhưng `/profile` thì không:
    # tài khoản bị khóa đọc ghi hồ sơ được tới một giờ, tới khi accessToken
    # hết hạn. Giờ `TaiKhoanConHoatDongFilter` chặn ở tầng bộ lọc nên endpoint
    # mới được bảo vệ mặc định.
    print("\n§4  tài khoản bị khóa — chặn ở mọi endpoint đã xác thực")
    ma, than = goi("POST", "/auth/login",
                   {"email": email, "password": mat_khau})
    tk = than and than.get("accessToken")
    rf = than and than.get("refreshToken")
    kiem("lấy được token trước khi khóa", bool(tk))

    sql("UPDATE users SET is_active = 0 WHERE email = %s", (email,))

    for duong in ("/auth/me", "/profile", "/profile/nutrition-targets",
                  "/profile/conditions"):
        ma, than = goi("GET", duong, token=tk)
        bang(f"403 ACCOUNT_DISABLED ở GET {duong}",
             (ma, ma_loi(than)), (403, "ACCOUNT_DISABLED"))

    ma, than = goi("PUT", "/profile/conditions", {"conditions": []}, token=tk)
    bang("403 cả với PUT, không chỉ GET", (ma, ma_loi(than)),
         (403, "ACCOUNT_DISABLED"))

    # Và không làm mới token được nữa — nếu không thì khóa tài khoản chỉ có
    # hiệu lực tối đa một giờ.
    ma, than = goi("POST", "/auth/refresh", {"refreshToken": rf})
    bang("401 khi refresh bằng tài khoản đã khóa", ma, 401)

    ma, than = goi("POST", "/auth/login",
                   {"email": email, "password": mat_khau})
    bang("403 ACCOUNT_DISABLED khi đăng nhập lại",
         (ma, ma_loi(than)), (403, "ACCOUNT_DISABLED"))

    sql("UPDATE users SET is_active = 1 WHERE email = %s", (email,))

    # ── Dọn ──────────────────────────────────────────────────────────────
    print()
    if ts.giu:
        print(f"Giữ lại tài khoản thử {email} (--giu)")
    else:
        # `fits-` là tài khoản của phép kiểm mật khẩu đúng 72 byte; `dai-`
        # không bao giờ tạo được dòng nào nhưng vẫn xóa cho chắc, để một lần
        # đổi chặn trên sau này không để lại rác.
        xoa_tai_khoan(email, f"vua-{email}", f"dai-{email}")
        print("Đã xóa 2 tài khoản thử; CASCADE dọn hồ sơ và token")

    print("=" * 72)
    if _loi:
        print(f"{len(_loi)}/{_so_kiem} PHÉP KIỂM SAI:")
        for x in _loi:
            print("  -", x)
        return 1
    print(f"{_so_kiem}/{_so_kiem} phép kiểm đạt — 9 endpoint chạy đúng đặc tả "
          "trên CSDL thật.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
