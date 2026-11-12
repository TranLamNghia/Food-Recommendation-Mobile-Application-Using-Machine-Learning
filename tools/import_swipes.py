#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nhập một phiếu khảo sát khẩu vị đã điền vào CSDL.

Nửa sau của việc số 10. `tools/make_survey_deck.py` sinh phiếu; tệp này đọc
phiếu đã điền và ghi vào `users`, `health_profiles`, `user_conditions`,
`interactions`, rồi tính `user_preference_profiles` bằng Rocchio.

## Kiểm hết rồi mới ghi

Toàn bộ phép kiểm chạy **trước** câu `INSERT` đầu tiên, và cả lần nhập là
**một giao dịch**. Một phiếu nhập dở — có người dùng nhưng thiếu lượt vuốt,
hoặc có lượt vuốt nhưng thiếu hồ sơ sở thích — tệ hơn hẳn một phiếu chưa
nhập: nó vẫn chạy qua mọi script phía sau và âm thầm góp một người dùng
khuyết vào tập huấn luyện.

## Hai chỗ đặt giá trị thay thế, và vì sao chúng an toàn

`users.password_hash` là `NOT NULL`, nhưng người trả lời phiếu giấy không có
tài khoản để đăng nhập. Đặt `!khong-the-dang-nhap`: dấu `!` ở đầu làm chuỗi
này **không phải** một giá trị băm hợp lệ của bất kỳ thuật toán nào, nên mọi
phép so khi đăng nhập đều thất bại. Đây là quy ước của Django cho "mật khẩu
không dùng được", và nó an toàn hơn hẳn một giá trị băm thật của một mật khẩu
mặc định nào đó — thứ sẽ thành một tài khoản mở cửa.

`users.email` là `UNIQUE NOT NULL`, nhưng không phải ai cũng cho email. Khi
để trống, sinh `khaosat-<n>@local.invalid`: tên miền `.invalid` được RFC 2606
dành riêng và **không bao giờ** phân giải được, nên không có nguy cơ gửi thư
tới một địa chỉ thật của người khác.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.db import in_utf8, ket_noi  # noqa: E402
from ml.f1_filter import dieu_kien_theo_ten, ly_do_loai  # noqa: E402
from ml.features import FEATURE_VERSION, KhongGianDacTrung, nap_mon  # noqa: E402
from ml.rocchio import alpha, dung_ho_so, giai_doan  # noqa: E402

from tools.make_survey_deck import LUA_CHON  # noqa: E402

#: Giá trị băm không dùng được — xem phần đầu tệp.
BAM_KHONG_DUNG_DUOC = "!khong-the-dang-nhap"

#: Mức độ ghi vào `user_conditions.severity`, VÀ mức độ dùng khi chạy Bộ lọc
#: F1 lúc nhập. Một hằng số cho cả hai chỗ, có chủ ý: phiếu giấy không hỏi
#: mức độ, nên nếu hai chỗ dùng hai giá trị khác nhau thì F1 lúc nhập sẽ loại
#: một tập món khác với F1 lúc chạy thật, trên cùng một người.
#:
#: Khác biệt này KHÔNG phải lý thuyết: với `Gút`, F1 loại 0 món ở mức `mild`
#: nhưng 9 món ở mức `moderate`, vì `condition_rules.severity_min` gác từng
#: quy tắc.
SEVERITY_PHIEU = "moderate"

TRUONG_BAT_BUOC = (
    "gioi_tinh",
    "ngay_sinh",
    "chieu_cao_cm",
    "can_nang_kg",
    "muc_van_dong",
    "muc_tieu",
)

GIA_TRI_HOP_LE = {
    "gioi_tinh": ("male", "female", "other"),
    "muc_van_dong": ("sedentary", "light", "moderate", "active", "very_active"),
    "muc_tieu": ("lose_weight", "maintain", "gain_weight", "healthy_eating"),
}


class LoiPhieu(Exception):
    """Phiếu không hợp lệ. Thông điệp phải nói rõ phải sửa dòng nào."""


def doc_phieu(duong_dan: Path) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Tách phần thông tin (`# khóa: giá trị`) và phần bảng."""
    if not duong_dan.exists():
        raise LoiPhieu(f"không thấy tệp {duong_dan}")

    thong_tin: dict[str, str] = {}
    dong_bang: list[str] = []
    for raw in duong_dan.read_text(encoding="utf-8-sig").splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("#"):
            than = s.lstrip("#").strip()
            # Bỏ phần chú thích sau dấu `#` thứ hai trên cùng dòng.
            if ":" in than:
                khoa, _, gt = than.partition(":")
                gt = gt.split("#")[0].strip()
                khoa = khoa.strip()
                if khoa and " " not in khoa:
                    thong_tin[khoa] = gt
            continue
        dong_bang.append(raw)

    if not dong_bang:
        raise LoiPhieu("phiếu không có dòng dữ liệu nào")

    doc = csv.DictReader(dong_bang)
    hang = [d for d in doc]
    thieu_cot = {"ma_mon", "ten_mon", "lua_chon"} - set(doc.fieldnames or ())
    if thieu_cot:
        raise LoiPhieu(f"phiếu thiếu cột: {', '.join(sorted(thieu_cot))}")
    return thong_tin, hang


def kiem_thong_tin(thong_tin: dict[str, str]) -> dict[str, Any]:
    """Kiểm và quy đổi phần thông tin. Ném `LoiPhieu` kèm chỗ phải sửa."""
    thieu = [k for k in TRUONG_BAT_BUOC if not thong_tin.get(k)]
    if thieu:
        raise LoiPhieu(
            "phần thông tin còn trống: "
            + ", ".join(thieu)
            + "\nĐiền vào các dòng `# <khóa>: <giá trị>` ở đầu phiếu."
        )

    for khoa, hop_le in GIA_TRI_HOP_LE.items():
        if thong_tin[khoa] not in hop_le:
            raise LoiPhieu(
                f"`{khoa}` = {thong_tin[khoa]!r} không hợp lệ; "
                f"phải là một trong: {', '.join(hop_le)}"
            )

    try:
        ngay_sinh = date.fromisoformat(thong_tin["ngay_sinh"])
    except ValueError as e:
        raise LoiPhieu(f"`ngay_sinh` phải dạng YYYY-MM-DD: {e}") from e
    if not date(1900, 1, 1) <= ngay_sinh <= date.today():
        raise LoiPhieu(f"`ngay_sinh` = {ngay_sinh} nằm ngoài khoảng hợp lý")

    try:
        cao = float(thong_tin["chieu_cao_cm"])
        nang = float(thong_tin["can_nang_kg"])
    except ValueError as e:
        raise LoiPhieu(f"chiều cao và cân nặng phải là số: {e}") from e
    # Đúng hai ràng buộc CHECK của `health_profiles`, kiểm ở đây để báo lỗi
    # bằng tiếng Việt thay vì để MySQL ném lỗi 3819 khó đọc.
    if not 50 <= cao <= 250:
        raise LoiPhieu(f"`chieu_cao_cm` = {cao:g} phải trong 50–250")
    if not 20 <= nang <= 300:
        raise LoiPhieu(f"`can_nang_kg` = {nang:g} phải trong 20–300")

    ngay_ks = thong_tin.get("ngay_khao_sat", "")
    try:
        ngay_khao_sat = date.fromisoformat(ngay_ks) if ngay_ks else date.today()
    except ValueError as e:
        raise LoiPhieu(f"`ngay_khao_sat` phải dạng YYYY-MM-DD: {e}") from e

    benh = [b.strip() for b in thong_tin.get("benh_ly", "").split(";") if b.strip()]

    return {
        "ho_ten": thong_tin.get("ho_ten", "").strip(),
        "email": thong_tin.get("email", "").strip(),
        "gioi_tinh": thong_tin["gioi_tinh"],
        "ngay_sinh": ngay_sinh,
        "chieu_cao_cm": cao,
        "can_nang_kg": nang,
        "muc_van_dong": thong_tin["muc_van_dong"],
        "muc_tieu": thong_tin["muc_tieu"],
        "benh_ly": benh,
        "ngay_khao_sat": ngay_khao_sat,
    }


def kiem_luot_vuot(
    hang: list[dict[str, str]], mon_theo_id: dict[str, Any]
) -> list[tuple[str, str]]:
    """Kiểm phần bảng. Trả về `[(food_id, action)]` theo thứ tự trong phiếu."""
    ket_qua: list[tuple[str, str]] = []
    loi: list[str] = []
    da_gap: set[str] = set()

    for i, d in enumerate(hang, start=1):
        stt = (d.get("stt") or str(i)).strip()
        ma = (d.get("ma_mon") or "").strip()
        chon = (d.get("lua_chon") or "").strip().lower()

        if not chon:
            continue  # bỏ trống: người trả lời không chọn, không phải lỗi
        if chon not in LUA_CHON:
            loi.append(
                f"  dòng {stt}: `lua_chon` = {chon!r} không hợp lệ; "
                f"phải là {' | '.join(LUA_CHON)}"
            )
            continue
        if ma not in mon_theo_id:
            loi.append(
                f"  dòng {stt}: `ma_mon` = {ma!r} không có trong danh mục món"
            )
            continue
        if ma in da_gap:
            loi.append(f"  dòng {stt}: món {mon_theo_id[ma].name!r} xuất hiện hai lần")
            continue

        da_gap.add(ma)
        ket_qua.append((ma, LUA_CHON[chon]))

    if loi:
        raise LoiPhieu("phiếu có lỗi:\n" + "\n".join(loi))
    if not ket_qua:
        raise LoiPhieu("phiếu chưa điền lựa chọn nào ở cột `lua_chon`")
    return ket_qua


def kiem_benh_ly(cn, ten: list[str]) -> list[int]:
    """Tra `benh_ly` sang `conditions.id`. Ném `LoiPhieu` nếu có tên lạ.

    Chạy ở pha KIỂM, không ở pha ghi. Trước đây phép tra này nằm trong
    `ghi()`, nên một phiếu ghi `benh_ly: tieu_duong` vẫn qua được lần chạy
    thử và chỉ vỡ lúc `--apply`. Với một phiếu thì phiền; với hai mươi lăm
    phiếu phát ra cùng một mẫu sai thì là hai mươi lăm lần vỡ cùng lúc, sau
    khi người trả lời đã điền xong và không còn sửa được.
    """
    if not ten:
        return []
    with cn.cursor() as cur:
        cho = ", ".join(["%s"] * len(ten))
        cur.execute(
            f"SELECT id, name_vi FROM conditions WHERE name_vi IN ({cho})",
            tuple(ten),
        )
        tim = {d["name_vi"]: int(d["id"]) for d in cur.fetchall()}
        thieu = [b for b in ten if b not in tim]
        if thieu:
            cur.execute("SELECT name_vi FROM conditions ORDER BY id")
            co = ", ".join(d["name_vi"] for d in cur.fetchall())
            raise LoiPhieu(
                "`benh_ly` có tên không khớp `conditions`: "
                + ", ".join(repr(x) for x in thieu)
                + f"\nPhải viết ĐÚNG tên tiếng Việt có dấu. Dùng được: {co}"
            )
    return [tim[b] for b in ten]


def loc_theo_f1(
    cn,
    ten_benh: list[str],
    luot: list[tuple[str, str]],
    mon_theo_id: dict[str, Any],
) -> tuple[list[tuple[str, str]], list[tuple[str, str, list[str]]]]:
    """Bỏ các lượt vuốt trên món mà Bộ lọc F1 không cho người này ăn.

    ## Vì sao phải làm, và vì sao làm ở ĐÂY

    Phiếu giấy dùng **một bộ món cố định cho mọi người**, vì không in riêng
    cho từng người được — và vì bộ cố định mới cho đủ quan sát trên mỗi món
    để tính được độ phổ biến (25 người × 40 món = ~25 lượt/món; cá nhân hóa
    thì 1000 lượt rải trên 318 món, còn ~3 lượt/món, và chặn dưới Wilson với
    3 quan sát thì vô dụng).

    Nhưng bộ cố định buộc người trả lời đánh giá cả món họ **không thể ăn**.
    Đo trên đúng bộ 40 món của phiếu:

        Dị ứng hải sản        loại  9/40  (22%)
        Ăn thuần chay         loại 22/40  (55%)
        Gút + Tăng huyết áp   loại  9/40  (22%)

    Người ăn thuần chay sẽ đánh `khong_thich` cho 22 món, và mô hình đọc đó
    là "không thích phở, không thích cá" thay vì "ăn thuần chay" — 55 % tín
    hiệu của họ là **ràng buộc giả dạng khẩu vị**. Tệ hơn, nó đầu độc cả độ
    phổ biến TOÀN CỤC: năm người thuần chay trong hai mươi lăm làm phở bò
    nhận năm lượt không-thích không phải vì phở dở.

    Trong app thì chuyện này không xảy ra — `GET /onboarding/survey` chạy F1
    **trước khi hỏi** (đặc tả §7.4.1). Phiếu giấy không làm được thế, nên nó
    chạy F1 **sau khi hỏi, trước khi ghi**. Khác thời điểm, nhưng thứ vào CSDL
    là như nhau.

    Bỏ hẳn chứ không ghi thành `unknown`: F1 vốn đã không bao giờ gợi ý những
    món đó cho người này, nên khẩu vị của họ trên chúng không được dùng ở đâu
    cả — còn `unknown` lại có nghĩa riêng là "chưa từng ăn", không phải
    "không được ăn".

    Trả về `(luot_con_lai, [(food_id, action, [lý do...])])`.
    """
    if not ten_benh:
        return luot, []

    # Cùng `severity` với dòng sẽ ghi vào `user_conditions` — xem
    # `SEVERITY_PHIEU`.
    dieu_kien = dieu_kien_theo_ten(cn, ten_benh, severity=SEVERITY_PHIEU)

    # `chi_mon_chung=True`: người trả lời phiếu giấy không có món riêng, và
    # cả bộ khảo sát là món chung.
    bi_loai_theo_mon = ly_do_loai(cn, dieu_kien=dieu_kien, chi_mon_chung=True)

    giu: list[tuple[str, str]] = []
    bo: list[tuple[str, str, list[str]]] = []
    for food_id, action in luot:
        ly_do = bi_loai_theo_mon.get(food_id)
        if ly_do:
            bo.append((food_id, action, [_ly_do_ngan(x) for x in ly_do]))
        else:
            giu.append((food_id, action))
    return giu, bo


def _ly_do_ngan(x: Any) -> str:
    """Một dòng đọc được từ `LyDoLoai`.

    `LyDoLoai` là dataclass mười ba trường; `str()` của nó dump hết và làm
    phần báo cáo không đọc nổi. `note` là câu đã viết sẵn cho người đọc.
    """
    benh = getattr(x, "benh", None) or "?"
    note = getattr(x, "note", None)
    if note:
        return f"{benh}: {note}"
    loai = getattr(x, "rule_type", None) or "?"
    the = getattr(x, "the", None) or getattr(x, "nutrient", None) or ""
    return f"{benh}: {loai} {the}".strip()


# ── Ghi ───────────────────────────────────────────────────────────────


def _email_moi(cn, cho: str) -> str:
    if cho:
        return cho
    with cn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) n FROM users WHERE email LIKE 'khaosat-%@local.invalid'"
        )
        n = int(cur.fetchone()["n"])
    return f"khaosat-{n + 1}@local.invalid"


def ghi(
    cn,
    tt: dict[str, Any],
    luot: list[tuple[str, str]],
    kg: KhongGianDacTrung,
    mon_theo_id: dict[str, Any],
) -> dict[str, Any]:
    """Ghi cả phiếu trong một giao dịch. Trả về thông tin để báo lại."""
    email = _email_moi(cn, tt["email"])
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    with cn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone() is not None:
            raise LoiPhieu(
                f"đã có người dùng với email {email!r}. Phiếu này có thể đã "
                f"được nhập; đổi email hoặc xóa người dùng cũ trước."
            )

        # Bệnh lý đã được `kiem_benh_ly` tra ở pha kiểm; tra lại ở đây để
        # `ghi()` không phụ thuộc vào việc người gọi đã kiểm hay chưa.
        ma_benh: list[int] = kiem_benh_ly(cn, tt["benh_ly"])

        cur.execute(
            "INSERT INTO users (id, email, password_hash, display_name, "
            "onboarding_completed_at) VALUES (%s, %s, %s, %s, %s)",
            (
                user_id,
                email,
                BAM_KHONG_DUNG_DUOC,
                tt["ho_ten"] or "Người khảo sát",
                datetime.combine(tt["ngay_khao_sat"], datetime.min.time()),
            ),
        )
        cur.execute(
            "INSERT INTO health_profiles (id, user_id, gender, date_of_birth, "
            "height_cm, weight_kg, activity_level, goal) "
            "VALUES (UUID(), %s, %s, %s, %s, %s, %s, %s)",
            (
                user_id,
                tt["gioi_tinh"],
                tt["ngay_sinh"],
                tt["chieu_cao_cm"],
                tt["can_nang_kg"],
                tt["muc_van_dong"],
                tt["muc_tieu"],
            ),
        )
        for cid in ma_benh:
            cur.execute(
                "INSERT INTO user_conditions (id, user_id, condition_id, severity) "
                "VALUES (UUID(), %s, %s, %s)",
                (user_id, cid, SEVERITY_PHIEU),
            )

        # Rải thời điểm cách nhau 1 giây trong ngày khảo sát. Thứ tự giữ đúng
        # thứ tự trên phiếu, vì `profile_snapshot` khi dựng tập huấn luyện
        # phát lại theo thứ tự thời gian.
        goc = datetime.combine(tt["ngay_khao_sat"], datetime.min.time()).replace(
            hour=9
        )
        for i, (food_id, action) in enumerate(luot):
            cur.execute(
                "INSERT INTO interactions (id, user_id, food_id, action, "
                "session_id, interacted_at) VALUES (UUID(), %s, %s, %s, %s, %s)",
                (user_id, food_id, action, session_id, goc + timedelta(seconds=i)),
            )

        ho_so = dung_ho_so(kg, [(mon_theo_id[f], a) for f, a in luot])
        cur.execute(
            "INSERT INTO user_preference_profiles (user_id, feature_version, "
            "weights, sum_abs_weight, n_signals, stage, alpha) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                user_id,
                FEATURE_VERSION,
                json.dumps(list(ho_so.weights)),
                ho_so.sum_abs_weight,
                ho_so.n_signals,
                giai_doan(ho_so.n_signals),
                round(alpha(ho_so.n_signals), 3),
            ),
        )

    cn.commit()
    return {
        "user_id": user_id,
        "email": email,
        "n_signals": ho_so.n_signals,
        "stage": giai_doan(ho_so.n_signals),
        "ho_so": ho_so,
    }


def main() -> int:
    in_utf8()
    bo = argparse.ArgumentParser(description=__doc__)
    bo.add_argument("--phieu", required=True, type=Path, help="tệp phiếu đã điền")
    bo.add_argument("--db", default=None)
    bo.add_argument("--apply", action="store_true", help="ghi vào CSDL")
    t = bo.parse_args()

    cn = ket_noi(t.db)
    try:
        mon, _ = nap_mon(cn)
        kg = KhongGianDacTrung.tu_mon(mon)
        mon_theo_id = {m.id: m for m in mon}

        try:
            thong_tin, hang = doc_phieu(t.phieu)
            tt = kiem_thong_tin(thong_tin)
            luot = kiem_luot_vuot(hang, mon_theo_id)
            kiem_benh_ly(cn, tt["benh_ly"])
        except LoiPhieu as e:
            print(f"Phiếu không dùng được.\n{e}", file=sys.stderr)
            return 1

        # Bộ lọc F1 chạy TRƯỚC khi dựng vector sở thích, không chỉ trước khi
        # ghi `interactions`. Lọc sau khi dựng thì vector vẫn mang nguyên
        # phần ràng buộc giả dạng khẩu vị, và `n_signals` vẫn đếm cả những
        # lượt đó nên giai đoạn cũng bị tính sai.
        luot_tho = luot
        luot, bi_loai = loc_theo_f1(cn, tt["benh_ly"], luot, mon_theo_id)
        if not luot:
            print(
                "Phiếu không dùng được.\nBộ lọc F1 loại toàn bộ "
                f"{len(luot_tho)} lượt đã điền — mọi món trong phiếu đều vi "
                "phạm ràng buộc cứng của người này. Cần một bộ món khác cho "
                "trường hợp này.",
                file=sys.stderr,
            )
            return 1

        dem: dict[str, int] = {}
        for _, a in luot:
            dem[a] = dem.get(a, 0) + 1
        ho_so = dung_ho_so(kg, [(mon_theo_id[f], a) for f, a in luot])

        print(f"Phiếu: {t.phieu}")
        print(
            f"  {tt['ho_ten'] or '(không ghi tên)'} · {tt['gioi_tinh']} · "
            f"sinh {tt['ngay_sinh']} · {tt['chieu_cao_cm']:g} cm / "
            f"{tt['can_nang_kg']:g} kg"
        )
        print(f"  mục tiêu {tt['muc_tieu']} · vận động {tt['muc_van_dong']}")
        print(f"  bệnh lý: {', '.join(tt['benh_ly']) or '(không có)'}")

        if bi_loai:
            print(
                f"  Bộ lọc F1 loại {len(bi_loai)}/{len(luot_tho)} lượt "
                f"({len(bi_loai) / len(luot_tho) * 100:.0f}%) — món người "
                "này không được ăn:"
            )
            # Gom theo lý do, không liệt kê từng món một: một người ăn thuần
            # chay bị loại 22 món vì ĐÚNG MỘT quy tắc, và in 22 dòng giống
            # nhau thì che mất chuyện đó.
            theo_ly_do: dict[str, list[str]] = {}
            for food_id, action, ly_do in bi_loai:
                ten = getattr(mon_theo_id[food_id], "name", food_id)
                theo_ly_do.setdefault(ly_do[0], []).append(f"{ten}[{action}]")
            for ly, mon_ds in sorted(theo_ly_do.items()):
                print(f"      {ly} → {len(mon_ds)} món")
                dau = ", ".join(mon_ds[:3])
                con = f", … và {len(mon_ds) - 3} món nữa" if len(mon_ds) > 3 else ""
                print(f"        {dau}{con}")
            print(
                "    Những lượt này KHÔNG được ghi và KHÔNG vào vector sở "
                "thích: chúng là ràng buộc, không phải khẩu vị."
            )

        print(
            f"  {len(luot)} lượt dùng được: "
            + "  ".join(f"{k}={v}" for k, v in sorted(dem.items()))
        )
        print(
            f"  → n_signals = {ho_so.n_signals} "
            f"(lượt `unknown` không được đếm) · "
            f"giai đoạn {giai_doan(ho_so.n_signals)}"
        )

        # Ba chiều mạnh nhất, để người nhập tự thấy vector có hợp lý không.
        manh = sorted(
            zip(ho_so.weights, kg.labels), key=lambda t_: -abs(t_[0])
        )[:4]
        print(
            "  chiều mạnh nhất: "
            + ", ".join(f"{nh} {w:+.3f}" for w, nh in manh)
        )

        if not t.apply:
            print("\nChạy thử — chưa ghi gì. Thêm --apply để nhập vào CSDL.")
            return 0

        try:
            kq = ghi(cn, tt, luot, kg, mon_theo_id)
        except LoiPhieu as e:
            cn.rollback()
            print(f"Không nhập được.\n{e}", file=sys.stderr)
            return 1

        print(f"\nĐã nhập: user_id = {kq['user_id']}, email = {kq['email']}")
        print(
            "Bước sau, khi đã nhập đủ số người:\n"
            "    python tools/update_popularity.py --apply\n"
            "    python -m ml.build_dataset --version d1 --apply\n"
            "    python -m ml.train --dataset d1 --apply\n"
            "    python -m ml.evaluate --dataset d1 --model <version> --apply"
        )
        return 0
    finally:
        cn.close()


if __name__ == "__main__":
    raise SystemExit(main())
