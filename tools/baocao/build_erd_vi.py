#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sinh bảng báo cáo ERD bằng tiếng Việt: docs/ERD_TIENG_VIET.md.

Bản báo cáo đặt tên tiếng Anh và tên tiếng Việt CẠNH NHAU cho từng bảng và
từng cột, vì hai cách gọi cùng tồn tại trong đồ án và cần tra qua lại được:

* Sơ đồ ERD nộp (BAOCAO/Diagram.mdj), mã nguồn và CSDL dùng tên tiếng Anh
  không dấu — yêu cầu của môn là tên thực thể, tên thuộc tính không có dấu
  tiếng Việt.
* Phần thuyết minh trong báo cáo gọi bằng tiếng Việt.

Tên tiếng Việt lấy từ `erd_vi.py`, còn kiểu dữ liệu, khóa, ràng buộc và
quan hệ đọc thẳng từ `information_schema` — nên phần kỹ thuật của tài liệu
không thể lệch khỏi CSDL. Chạy lại sau mỗi lần đổi lược đồ.

Script tự kiểm ba thứ trước khi ghi, sai thì dừng chứ không ra tài liệu sai:
    1. Mỗi bảng, mỗi cột trong CSDL có đúng một tên tiếng Việt, không thừa.
    2. Tên tiếng Việt đúng quy tắc: chữ đầu không hoa, không khoảng trắng,
       không gạch dưới.
    3. Tên không trùng nhau trong cùng một bảng, tên bảng không trùng nhau.

Chạy:
    python tools/baocao/build_erd_vi.py
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _env  # noqa: E402
from erd_vi import BANG, COT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
RA = ROOT / "docs" / "ERD_TIENG_VIET.md"
DB_NAME = "nutrition_rec"

NHAY = "'"


# ══════════════════════════════════════════════════════════════════════════
def doc_csdl() -> dict:
    import pymysql

    conn = pymysql.connect(
        host=_env.get("MYSQL_HOST", "localhost"),
        port=int(_env.get("MYSQL_PORT", "3306")),
        user=_env.require("MYSQL_USER"),
        password=_env.require("MYSQL_PASSWORD"),
        database=DB_NAME,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE "
                "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s "
                "ORDER BY TABLE_NAME, ORDINAL_POSITION", (DB_NAME,))
            cot: dict[str, list[dict]] = {}
            for b, t, k, n in cur.fetchall():
                cot.setdefault(b, []).append(
                    {"ten": t, "kieu": k, "null": n == "YES"})

            cur.execute(
                "SELECT TABLE_NAME, COLUMN_NAME, CONSTRAINT_NAME, "
                "       REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
                "FROM information_schema.KEY_COLUMN_USAGE "
                "WHERE TABLE_SCHEMA = %s "
                "ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION",
                (DB_NAME,))
            pk, fk, quan_he = set(), {}, []
            for b, t, rb, bang_cha, cot_cha in cur.fetchall():
                if rb == "PRIMARY":
                    pk.add((b, t))
                if bang_cha:
                    fk[(b, t)] = (bang_cha, cot_cha)
                    quan_he.append((bang_cha, b, t))

            # Phải lấy cả EXPRESSION: với khóa hàm (`uq_food_name`,
            # `uq_rda`) MySQL để COLUMN_NAME là NULL và đặt biểu thức ở
            # EXPRESSION. Gộp bằng GROUP_CONCAT(COLUMN_NAME) sẽ nuốt mất
            # những thành phần đó, và tài liệu sinh ra sẽ mô tả một khóa
            # lỏng hơn khóa thật.
            cur.execute(
                "SELECT TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX, "
                "       COLUMN_NAME, EXPRESSION "
                "FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = %s AND NON_UNIQUE = 0 "
                "ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX", (DB_NAME,))
            thanh_phan: dict[tuple[str, str], list[tuple[str, bool]]] = {}
            for b, ci, _, cn_, bt in cur.fetchall():
                if ci == "PRIMARY":
                    continue
                if cn_ is not None:
                    thanh_phan.setdefault((b, ci), []).append((cn_, True))
                else:
                    thanh_phan.setdefault((b, ci), []).append((gon_bt(bt),
                                                               False))

            uq_don, uq_ghep = set(), {}
            for (b, _), tp in thanh_phan.items():
                if len(tp) == 1 and tp[0][1]:
                    uq_don.add((b, tp[0][0]))
                else:
                    uq_ghep.setdefault(b, []).append(tp)

            return {"cot": cot, "pk": pk, "fk": fk, "uq_don": uq_don,
                    "uq_ghep": uq_ghep, "quan_he": quan_he}
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════
def kiem_ten(db: dict) -> None:
    """Đối chiếu bảng tên tiếng Việt với CSDL và với quy tắc đặt tên."""
    loi: list[str] = []

    thieu = [b for b in db["cot"] if b not in BANG or b not in COT]
    thua = [b for b in set(BANG) | set(COT) if b not in db["cot"]]
    loi += [f"bảng {b}: chưa có tên tiếng Việt" for b in sorted(thieu)]
    loi += [f"bảng {b}: không còn trong CSDL" for b in sorted(thua)]

    for bang, cols in db["cot"].items():
        ds = COT.get(bang, {})
        trong_db = {c["ten"] for c in cols}
        loi += [f"{bang}.{c}: chưa có tên tiếng Việt"
                for c in sorted(trong_db - set(ds))]
        loi += [f"{bang}.{c}: không còn trong CSDL"
                for c in sorted(set(ds) - trong_db)]

        trung = [v for v in set(ds.values())
                 if list(ds.values()).count(v) > 1]
        loi += [f"{bang}: hai cột cùng tên tiếng Việt {v!r}"
                for v in sorted(trung)]

    ten_bang = [v[0] for v in BANG.values()]
    loi += [f"hai bảng cùng tên tiếng Việt {v!r}"
            for v in sorted({v for v in ten_bang if ten_bang.count(v) > 1})]

    # Quy tắc: chữ đầu không hoa, không khoảng trắng, không gạch dưới.
    moi_ten = [(f"bảng {k}", v[0]) for k, v in BANG.items()]
    moi_ten += [(f"{b}.{c}", v) for b, ds in COT.items()
                for c, v in ds.items()]
    for o, ten in moi_ten:
        if not ten:
            loi.append(f"{o}: tên rỗng")
            continue
        if " " in ten or "_" in ten or "-" in ten:
            loi.append(f"{o}: {ten!r} có khoảng trắng hoặc gạch nối")
        # So bằng dạng NFC rồi đổi hoa/thường: ký tự Việt có dấu vẫn phân
        # biệt được hoa thường, nên phép thử này đúng cả với 'Đ' và 'Ư'.
        dau = unicodedata.normalize("NFC", ten)[0]
        if dau != dau.lower():
            loi.append(f"{o}: {ten!r} viết hoa chữ đầu")

    if loi:
        print(f"Bảng tên tiếng Việt chưa khớp CSDL ({len(loi)} chỗ):")
        for d in loi[:30]:
            print("   -", d)
        sys.exit(1)

    print(f"   ✓ {len(BANG)} bảng, "
          f"{sum(len(v) for v in COT.values())} cột đều có tên tiếng Việt "
          f"đúng quy tắc")


# ══════════════════════════════════════════════════════════════════════════
def kieu_gon(raw: str) -> str:
    """Kiểu dữ liệu viết cho người đọc: từ khóa in hoa, ENUM giữ giá trị."""
    m = re.match(r"(\w+)(?:\((.*)\))?(.*)$", raw, re.S)
    if not m:
        return raw.upper()
    tu, arg, duoi = m.group(1).upper(), m.group(2), m.group(3).strip().upper()
    if tu in ("ENUM", "SET"):
        gt = re.findall(NHAY + r"([^" + NHAY + r"]*)" + NHAY, arg or "")
        arg = ", ".join(NHAY + v + NHAY for v in gt)
    return (tu + (f"({arg})" if arg else "") + (f" {duoi}" if duoi else ""))


def khoa(db: dict, bang: str, cot: str) -> str:
    c = []
    if (bang, cot) in db["pk"]:
        c.append("PK")
    if (bang, cot) in db["fk"]:
        c.append("FK")
    if (bang, cot) in db["uq_don"]:
        c.append("UQ")
    # Cột nằm trong khóa ghép, kể cả khi nó chỉ xuất hiện bên trong một
    # biểu thức như `COALESCE(qualifier,'')` — nó vẫn bị khóa ràng buộc.
    for g in db["uq_ghep"].get(bang, []):
        if any(cot == t if la_cot
               else re.search(rf"\b{re.escape(cot)}\b", t)
               for t, la_cot in g):
            c.append("UQ*")
            break
    return " ".join(c)


def o(text: str) -> str:
    """Thoát ký tự `|` để không vỡ ô trong bảng Markdown."""
    return text.replace("|", "\\|")


def gon_bt(bt: str) -> str:
    """Dọn biểu thức khóa hàm mà MySQL trả về cho dễ đọc.

    MySQL lưu nguyên văn dạng nội bộ:

        coalesce(`qualifier`,_utf8mb4\\'\\')   ->   COALESCE(qualifier, '')

    Bỏ dấu huyền quanh tên cột, bỏ tiền tố bộ ký tự, bỏ dấu thoát, và viết
    hoa tên hàm cho khớp cách viết trong `schema.sql`.
    """
    s = bt.replace("\\'", "'").replace("`", "")
    s = re.sub(r"_utf8mb4(?=')", "", s)
    s = re.sub(r"^([a-z_]+)\(", lambda m: m.group(1).upper() + "(", s)
    return s.replace(",", ", ")


# ══════════════════════════════════════════════════════════════════════════

def _in_utf8() -> None:
    """Bắt stdout nhận tiếng Việt trên Windows (mặc định cp1252).

    Không gọi thì script chết giữa lúc chạy với UnicodeEncodeError ngay khi
    đầu ra bị chuyển hướng qua ống hoặc vào tệp — tức đúng lúc chạy trong CI.
    Bản sao của `tools/_env.use_utf8`; để ở đây vì `tools/baocao/` không chắc
    có `tools/` trên `sys.path`.
    """
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover
            pass

def main() -> int:
    _in_utf8()
    db = doc_csdl()
    kiem_ten(db)

    so_cot = sum(len(v) for v in db["cot"].values())
    so_enum = sum(1 for cs in db["cot"].values() for c in cs
                  if c["kieu"].startswith(("enum", "set")))

    d: list[str] = []
    d.append("# ERD — bảng đối chiếu tên tiếng Anh và tên tiếng Việt")
    d.append("")
    d.append("Ứng dụng di động khuyến nghị thực đơn dinh dưỡng cá nhân hóa — "
             "Trần Lâm Nghĩa (22115053122231).")
    d.append("")
    d.append(f"CSDL `{DB_NAME}` · MySQL 8 · InnoDB · utf8mb4_unicode_ci · "
             f"**{len(db['cot'])} bảng, {so_cot} cột, "
             f"{len(db['quan_he'])} khóa ngoại, {so_enum} cột ENUM**.")
    d.append("")
    d.append("> Tài liệu này sinh tự động bằng `tools/baocao/build_erd_vi.py`. "
             "Kiểu dữ liệu và khóa đọc thẳng từ `information_schema`, tên "
             "tiếng Việt lấy từ `tools/baocao/erd_vi.py`. Sửa tay vào đây sẽ "
             "mất khi chạy lại.")
    d.append("")
    d.append("## 1. Quy tắc đặt tên tiếng Việt")
    d.append("")
    d.append("Tên tiếng Anh chuyển thẳng sang tiếng Việt rồi viết dính liền "
             "theo kiểu lạc đà: **chữ cái đầu không viết hoa, không khoảng "
             "trắng, giữ nguyên dấu**.")
    d.append("")
    d.append("| Tên tiếng Anh | Tên tiếng Việt |")
    d.append("|---|---|")
    for a, b in (("users", "ngườiDùng"), ("password_hash", "mãBămMậtKhẩu"),
                 ("meal_plan_items", "mónTrongThựcĐơn"),
                 ("vitamin_a_mcg", "vitaminAMicrogam")):
        d.append(f"| `{a}` | `{b}` |")
    d.append("")
    d.append("Vài quy ước giữ giống nhau ở mọi bảng, để đọc tên là đoán được "
             "ý nghĩa:")
    d.append("")
    d.append("- `id` → `mã`, còn `<bảng>_id` → `mã<Bảng>`.")
    d.append("- Cột `DATETIME` dùng tiền tố `thờiĐiểm`, cột `DATE` dùng "
             "`ngày`. Đọc tên cột là biết cột đó có giờ phút hay không.")
    d.append("- `note` → `ghiChú`, `description` → `môTả`, "
             "`created_at` → `thờiĐiểmTạo`.")
    d.append("")
    d.append("**Sơ đồ ERD nộp kèm vẫn để tên tiếng Anh không dấu**, theo yêu "
             "cầu tên thực thể và tên thuộc tính không có dấu tiếng Việt. "
             "Bảng dưới đây là cầu nối giữa sơ đồ đó và phần thuyết minh "
             "tiếng Việt của báo cáo.")
    d.append("")

    # ── Danh sách bảng ──
    d.append("## 2. Danh sách thực thể")
    d.append("")
    d.append("| STT | Tên tiếng Anh | Tên tiếng Việt | Số cột | Diễn giải |")
    d.append("|---:|---|---|---:|---|")
    for i, (bang, (vi, mo_ta)) in enumerate(BANG.items(), 1):
        d.append(f"| {i} | `{bang}` | `{vi}` | {len(db['cot'][bang])} | "
                 f"{o(mo_ta)} |")
    d.append("")

    # ── Từng bảng ──
    d.append("## 3. Thuộc tính của từng thực thể")
    d.append("")
    d.append("Cột **Khóa**: `PK` khóa chính · `FK` khóa ngoại · `UQ` duy nhất "
             "một cột · `UQ*` duy nhất theo tổ hợp nhiều cột.")
    d.append("")
    for i, (bang, (vi, mo_ta)) in enumerate(BANG.items(), 1):
        d.append(f"### 3.{i}. `{bang}` — `{vi}`")
        d.append("")
        d.append(o(mo_ta))
        d.append("")
        d.append("| # | Tên tiếng Anh | Tên tiếng Việt | Kiểu dữ liệu | "
                 "Khóa | Rỗng |")
        d.append("|---:|---|---|---|---|---|")
        for k, c in enumerate(db["cot"][bang], 1):
            kg = khoa(db, bang, c["ten"])
            tham = ""
            if (bang, c["ten"]) in db["fk"]:
                bc, cc = db["fk"][(bang, c["ten"])]
                tham = f" → `{bc}.{cc}`"
            d.append(f"| {k} | `{c['ten']}`{tham} | `{COT[bang][c['ten']]}` "
                     f"| `{o(kieu_gon(c['kieu']))}` | {kg} | "
                     f"{'có' if c['null'] else '—'} |")
        ghep = db["uq_ghep"].get(bang, [])
        if ghep:
            d.append("")
            for g in ghep:
                # Thành phần là biểu thức thì in nguyên văn: nó không có
                # tên tiếng Việt vì nó không phải là một cột.
                ten_en = ", ".join(f"`{t}`" if la_cot else f"`{t}`"
                                   for t, la_cot in g)
                ten_vi = ", ".join(
                    f"`{COT[bang][t]}`" if la_cot else f"`{t}`"
                    for t, la_cot in g)
                d.append(f"Duy nhất theo tổ hợp: ({ten_en}) — {ten_vi}.")
        d.append("")

    # ── Quan hệ ──
    d.append("## 4. Quan hệ giữa các thực thể")
    d.append("")
    d.append(f"{len(db['quan_he'])} khóa ngoại. Một cặp bảng có thể nối nhau "
             "nhiều lần qua nhiều cột khác nhau — `meal_plan_items` trỏ tới "
             "`foods` hai lần, một lần cho món được xếp và một lần cho món "
             "dùng thay thế.")
    d.append("")
    d.append("| Thực thể cha | Thực thể con | Qua cột | Lượng số |")
    d.append("|---|---|---|---|")
    for cha, con, cot in db["quan_he"]:
        d.append(f"| `{cha}` · `{BANG[cha][0]}` "
                 f"| `{con}` · `{BANG[con][0]}` "
                 f"| `{cot}` · `{COT[con][cot]}` | 1 — 0..* |")
    d.append("")

    # ── Miền giá trị ENUM ──
    d.append("## 5. Miền giá trị của các cột ENUM")
    d.append("")
    d.append(f"{so_enum} cột dùng kiểu liệt kê. Tập giá trị do CSDL quy định "
             "nên không thể nhập sai ở tầng ứng dụng.")
    d.append("")
    d.append("| Thực thể | Cột | Tên tiếng Việt | Giá trị |")
    d.append("|---|---|---|---|")
    for bang in BANG:
        for c in db["cot"][bang]:
            if not c["kieu"].startswith(("enum", "set")):
                continue
            gt = re.findall(NHAY + r"([^" + NHAY + r"]*)" + NHAY, c["kieu"])
            d.append(f"| `{bang}` | `{c['ten']}` | `{COT[bang][c['ten']]}` "
                     f"| {', '.join(f'`{v}`' for v in gt)} |")
    d.append("")

    RA.parent.mkdir(parents=True, exist_ok=True)
    RA.write_text("\n".join(d), encoding="utf-8")
    print(f"Đã ghi {RA.relative_to(ROOT)} — {len(d)} dòng, "
          f"{len(db['cot'])} bảng, {so_cot} cột, {so_enum} cột ENUM")
    return 0


if __name__ == "__main__":
    sys.exit(main())
