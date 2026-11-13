#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Flowchart, đặc tả API và lược đồ CSDL phải mô tả cùng một hệ thống.

Vì sao cần. Mười tám flowchart trong `BAOCAO/Diagram.mdj` gọi tên endpoint,
mã lỗi và tên bảng. Ba thứ đó sống ở ba tệp khác nhau — sơ đồ, đặc tả API,
lược đồ CSDL — và không gì buộc chúng khớp nhau. Đổi tên một endpoint trong
đặc tả thì sơ đồ vẫn vẽ ra bình thường, vẫn in vào báo cáo bình thường, chỉ
là nó mô tả một hệ thống không tồn tại.

Lần chạy đầu tiên của bộ kiểm này bắt được **năm mã lỗi đặt sai** trong
chính bộ sơ đồ vừa vẽ: `EMAIL_EXISTS` trong khi danh mục ghi
`EMAIL_ALREADY_EXISTS`, `FOOD_NOT_FOUND` trong khi danh mục chỉ có
`NOT_FOUND`, và ba mã nữa. Không mã nào gây lỗi gì — đó mới là lý do phải
kiểm bằng máy.

NĂM PHÉP KIỂM
    1. endpoint  sơ đồ -> đặc tả    mọi `METHOD /path` phải có trong §6
    2. mã lỗi    sơ đồ -> đặc tả    mọi mã phải có trong danh mục §4
    3. tên bảng  sơ đồ -> CSDL      mọi bảng phải có trong db/schema.sql
    4. tên cột   sơ đồ -> CSDL      mọi cột phải có trong bảng đi kèm
    5. con số    đặc tả -> đặc tả   "N endpoint công khai" phải bằng số dòng

Phép thứ tư thêm sau, vì phép thứ ba để lọt đúng kiểu lỗi nó sinh ra để
bắt. Sơ đồ viết `ORDER BY log_date` và `UPSERT body_logs theo (user_id,
log_date)`, trong khi cột thật tên `logged_on`; đặc tả API cũng đã trả
một trường `logDate` không ứng với cột nào. Tên BẢNG đúng nên phép thứ
ba cho qua — và một truy vấn có tên bảng đúng với tên cột bịa vẫn đọc ra
trôi chảy, nó chỉ không chạy được.

Chạy:
    python tools/check_flowchart.py
"""

from __future__ import annotations

import pathlib
import re
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "baocao"))

from flowchart_data import DAU_DE_XUAT, SO_DO  # noqa: E402

APISPEC = ROOT / "docs" / "API_SPECIFICATION.md"
SCHEMA = ROOT / "db" / "schema.sql"
MDJ = ROOT / "BAOCAO" / "Diagram.mdj"

#: `METHOD /đường-dẫn` ở bất cứ đâu trong chữ của một khối.
RE_ENDPOINT = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE) (/[A-Za-z0-9/{}_-]+)")

#: Mã lỗi: chữ in hoa và gạch dưới, ít nhất hai đoạn. Đủ hẹp để không bắt
#: nhầm `NULL`, `SQL` hay `BMI`, đủ rộng để bắt mọi mã trong danh mục.
RE_MA_LOI = re.compile(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b")

#: Những chuỗi in hoa có gạch dưới mà KHÔNG phải mã lỗi.
BO_QUA_MA = {
    "CURRENT_TIMESTAMP", "ON_DELETE", "NOT_NULL", "PRIMARY_KEY",
    "E_TARGET", "C_VALID",
}

#: Tên bảng xuất hiện sau các từ khóa SQL, hoặc được nêu thẳng.
RE_BANG_SQL = re.compile(
    r"\b(?:FROM|INTO|JOIN|UPDATE|UPSERT)\s+([a-z][a-z0-9_]+)")

#: Tên bảng nêu trong văn xuôi của khối, ví dụ "Đọc foods, food_nutrition".
RE_BANG_VAN = re.compile(r"\b([a-z]+(?:_[a-z]+)+)\b")

#: Từ khóa mở đầu một khai báo kiểu, để phân biệt dòng khai báo cột với dòng
#: nối tiếp của một ENUM nhiều dòng hay một biểu thức CHECK.
TU_KHOA_KIEU = (
    "BIGINT", "INT", "SMALLINT", "TINYINT", "MEDIUMINT", "DECIMAL", "NUMERIC",
    "FLOAT", "DOUBLE", "VARCHAR", "CHAR", "TEXT", "LONGTEXT", "MEDIUMTEXT",
    "JSON", "ENUM", "SET", "DATE", "DATETIME", "TIMESTAMP", "TIME", "YEAR",
    "BOOLEAN", "BOOL", "BLOB", "BINARY",
)

#: Chuỗi snake_case trong khối mà KHÔNG phải tên cột: tên trường JSON của API,
#: hoặc một từ ghép dùng trong câu văn.
BO_QUA_COT = {
    "access_token", "refresh_token", "reset_token",
}

# Tên cột MỘT TỪ không lọt qua `RE_BANG_VAN` được, vì mẫu đó đòi ít nhất một
# gạch dưới để không bắt mọi từ tiếng Anh trong câu văn. Đúng khoảng trống đó
# đã để `interactions (source = ...)` đi qua: `source` không có gạch dưới, và
# `interactions` KHÔNG CÓ cột nào tên vậy — cột thật là `action`.
#
# Nên thay vì nới mẫu tên (sẽ bắt cả "theo", "đã", "món"), ba mẫu dưới đây
# bắt theo VỊ TRÍ CÚ PHÁP: chỗ nào trong một câu SQL thì một định danh chữ
# thường chỉ có thể là tên cột. Từ khóa SQL viết hoa trong mọi sơ đồ nên mẫu
# phân biệt hoa thường tự loại chúng, không cần danh sách từ khóa.

#: `cot = ...`, `cot >= ...` — vế trái của một phép so sánh hoặc phép gán.
RE_COT_SS = re.compile(r"\b([a-z][a-z0-9_]*)\s*(?:=|<>|!=|<=|>=|<|>)")

#: `SELECT a, b, c FROM` — danh sách cột được chọn.
RE_COT_SELECT = re.compile(r"\bSELECT\s+(.+?)\s+FROM\b")

#: `INSERT INTO bang (a, b)` · `UPSERT bang (a, b)` — danh sách trong ngoặc.
RE_COT_NGOAC = re.compile(
    r"\b(?:INSERT INTO|UPSERT|UPDATE)\s+[a-z_][a-z0-9_]*\s*\((.+?)\)")

#: `ORDER BY a, b` · `GROUP BY a` — chỉ nhận danh sách định danh ngăn bằng
#: dấu phẩy, không nhận phần câu văn đứng sau. `SET` không cần mẫu riêng vì
#: `RE_COT_SS` đã bắt vế trái của mỗi phép gán.
RE_COT_SAU = re.compile(
    r"\b(?:ORDER BY|GROUP BY)\s+"
    r"([a-z_][a-z0-9_]*(?:\s*,\s*[a-z_][a-z0-9_]*)*)")

#: Chuỗi trong dấu nháy đơn: GIÁ TRỊ, không phải tên cột. Gỡ trước khi bóc
#: ứng viên, nếu không `(role = 'user')` sẽ cho ra một "cột" tên `user`.
RE_HANG_CHU = re.compile(r"'[^']*'")

#: Một phần tử trong danh sách cột: bỏ `*`, hằng số, dấu hỏi tham số.
RE_DINH_DANH = re.compile(r"\b([a-z][a-z0-9_]*)\b")


def chu_cac_khoi() -> list[tuple[str, str]]:
    """(mã sơ đồ, chữ trong khối) cho mọi khối của cả 18 sơ đồ."""
    return [(ma, k[4]) for ma, _, khoi, _ in SO_DO for k in khoi]


def _ten_use_case_mdj() -> list[str]:
    """Tên 18 `UMLUseCase` trong `BAOCAO/Diagram.mdj`."""
    import json

    ra: list[str] = []

    def di(n: Any) -> None:
        if isinstance(n, dict):
            if n.get("_type") == "UMLUseCase":
                ra.append(str(n.get("name")))
            for v in n.values():
                di(v)
        elif isinstance(n, list):
            for v in n:
                di(v)

    di(json.loads(MDJ.read_text(encoding="utf-8")))
    return ra


def kiem_luong_chuong2() -> list[str]:
    """Phép suy ra kịch bản Chương 2 phải còn đúng với 18 sơ đồ.

    `chuong2_data.py` suy luồng chính của từng kịch bản từ chính `SO_DO`,
    dựa trên **quy ước vẽ** (trục chính ở cột 0, đi xuống theo dòng). Quy ước
    đó có thể bị phá bởi một lần sửa sơ đồ hoàn toàn hợp lệ — thêm một ô ghi
    chú bên phải, hay thêm một vòng quay lại — và khi đó kịch bản sinh ra vẫn
    là một danh sách câu đọc được, chỉ là của một luồng không có trên sơ đồ.
    """
    try:
        sys.path.insert(0, str(ROOT / "tools" / "baocao"))
        import chuong2_data  # type: ignore
    except ImportError as e:  # pragma: no cover
        print(f"   ! không nạp được chuong2_data.py: {e}")
        return [f"không nạp được chuong2_data.py: {e}"]

    loi = chuong2_data.kiem_luong_chinh()
    if not loi:
        print(f"   ✓ {len(SO_DO)}/{len(SO_DO)} luồng chính đi tới khối Kết thúc")
    return loi


def kiem_ten_use_case() -> list[str]:
    """Tên use case phải khớp giữa BA nguồn: mdj, flowchart và User story.

    `them_flowchart.py` đã buộc `flowchart_data.SO_DO` khớp với mô hình Use
    case, nhưng **không ai soát `tools/baocao/us_data.py`** — và nó đã lệch:
    hai use case mang tên ngắn hơn trong phần User story của báo cáo so với
    tên trên sơ đồ Use case và trên flowchart:

        sơ đồ: "Điền hoặc Chọn thông tin cá nhân phù hợp với sức khỏe cá nhân"
        story: "Khai báo thông tin cá nhân và tình trạng sức khỏe"

        sơ đồ: "Lựa chọn món ăn yêu thích dựa vào tình trạng sức khỏe"
        story: "Lựa chọn món ăn yêu thích"

    Không chỗ nào gây lỗi — nhưng hội đồng đọc sơ đồ Use case ở mục 2.2.2 rồi
    đọc User story ở mục 1.4 và thấy hai cái tên khác nhau cho cùng một chức
    năng. Docstring của `us_data.py` tự khai là "lấy đúng 18 use case trong
    Diagram.mdj", nên đây là lỗi theo chính hợp đồng nó đặt ra.
    """
    loi: list[str] = []
    mdj = set(_ten_use_case_mdj())
    fc = {ten for _ma, ten, _k, _c in SO_DO}

    try:
        sys.path.insert(0, str(ROOT / "tools" / "baocao"))
        import us_data  # type: ignore
    except ImportError as e:  # pragma: no cover
        print(f"   ! không nạp được us_data.py: {e}")
        return [f"không nạp được us_data.py: {e}"]
    us = {s[0] for s in us_data.STORIES}

    for ten_nguon, tap in (("flowchart_data", fc), ("us_data", us)):
        missing = sorted(mdj - tap)
        thua = sorted(tap - mdj)
        if missing or thua:
            for x in missing:
                loi.append(f"{ten_nguon} thiếu use case {x!r} (có trong mdj)")
            for x in thua:
                loi.append(f"{ten_nguon} có use case {x!r} mà mdj không có")
        else:
            print(f"   ✓ {ten_nguon}: {len(tap)} tên khớp mdj")
    return loi


def _in_utf8() -> None:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover
            pass


def kiem_endpoint(spec: str) -> list[str]:
    loi = []
    thay: set[str] = set()
    for ma, chu in chu_cac_khoi():
        for method, duong in RE_ENDPOINT.findall(chu):
            ep = f"{method} {duong}"
            thay.add(ep)
            if f"`{duong}`" not in spec:
                loi.append(f"{ma}: sơ đồ gọi {ep!r} mà đặc tả không có "
                           f"đường dẫn {duong!r}")
    print(f"   {len(thay)} endpoint phân biệt được nêu trong 18 sơ đồ")
    return loi


def kiem_ma_loi(spec: str) -> list[str]:
    # Danh mục mã lỗi: cột đầu của bảng ở mục 4.
    danh_muc = set(re.findall(r"^\| `([A-Z][A-Z0-9_]+)` \| \d{3} \|",
                              spec, re.M))
    if not danh_muc:
        return ["không đọc được danh mục mã lỗi ở mục 4 của đặc tả"]
    loi = []
    thay: set[str] = set()
    for ma, chu in chu_cac_khoi():
        if "lỗi" not in chu.lower():
            continue
        for x in RE_MA_LOI.findall(chu):
            if x in BO_QUA_MA:
                continue
            thay.add(x)
            if x not in danh_muc:
                loi.append(f"{ma}: sơ đồ hiện mã {x!r} mà danh mục mục 4 "
                           "không có")
    print(f"   {len(danh_muc)} mã trong danh mục, {len(thay)} mã được dùng "
          "trong sơ đồ")
    return loi


def kiem_bang(schema: str) -> list[str]:
    co = set(re.findall(r"^CREATE TABLE (\w+)", schema, re.M))
    loi = []
    thay: set[str] = set()
    for ma, chu in chu_cac_khoi():
        if DAU_DE_XUAT in chu:
            continue
        ung = set(RE_BANG_SQL.findall(chu))
        # Khối CSDL thì mọi định danh snake_case trong đó đều đáng ngờ là
        # tên bảng; chỉ báo khi nó TRÔNG như tên bảng mà không có thật —
        # tên cột cũng là snake_case nên chỉ nhận chuỗi đã biết là bảng.
        ung |= {x for x in RE_BANG_VAN.findall(chu) if x in co}
        for b in ung:
            thay.add(b)
            if b not in co:
                loi.append(f"{ma}: sơ đồ nêu bảng {b!r} mà db/schema.sql "
                           "không có")
    print(f"   {len(thay)} bảng được nêu trong sơ đồ, "
          f"{len(co)} bảng trong lược đồ")
    return loi


def _cot_cua_bang(schema: str) -> dict[str, set[str]]:
    """{tên bảng: tập tên cột} bóc từ db/schema.sql.

    Không cần bóc kiểu hay ràng buộc — `tools/check_schema_sql.py` đã so từng
    cột với CSDL thật. Ở đây chỉ cần biết một tên cột CÓ hay KHÔNG.
    """
    out: dict[str, set[str]] = {}
    for m in re.finditer(r"CREATE TABLE (\w+)\s*\((.*?)\n\) ENGINE",
                         schema, re.S):
        ten, than = m.group(1), m.group(2)
        cot = set()
        for dong in than.split("\n"):
            dong = dong.split("--")[0].strip()
            phan = dong.split(None, 1)
            if len(phan) < 2:
                continue
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", phan[0]):
                continue
            if not phan[1].upper().startswith(TU_KHOA_KIEU):
                continue
            cot.add(phan[0])
        out[ten] = cot
    return out


def kiem_cot(schema: str) -> list[str]:
    """Mọi tên cột nêu trong một khối phải có trong bảng khối đó nhắc tới.

    Phạm vi cố ý hẹp: chỉ xét khối nêu ĐÚNG MỘT bảng. Khối nêu hai bảng trở
    lên là một phép JOIN, và ở đó một tên cột có thật ở bảng này mà không có ở
    bảng kia vẫn hoàn toàn đúng — phép kiểm sẽ báo nhầm. Hẹp mà im lặng tốt
    hơn rộng mà phải nuôi một danh sách ngoại lệ.
    """
    bang_cot = _cot_cua_bang(schema)
    loi = []
    da_xet = 0
    for ma, chu in chu_cac_khoi():
        if DAU_DE_XUAT in chu:
            continue
        bang = {x for x in RE_BANG_SQL.findall(chu) if x in bang_cot}
        bang |= {x for x in RE_BANG_VAN.findall(chu) if x in bang_cot}
        if len(bang) != 1:
            continue
        ten = bang.pop()
        da_xet += 1

        # Gỡ giá trị trong dấu nháy trước khi bóc: chúng không phải tên cột.
        khong_nhay = RE_HANG_CHU.sub(" ", chu)

        # Ứng viên 1 — mọi chuỗi snake_case trong khối.
        ung = set(RE_BANG_VAN.findall(khong_nhay))
        # Ứng viên 2 — định danh ở một vị trí cú pháp chỉ dành cho tên cột.
        ung |= set(RE_COT_SS.findall(khong_nhay))
        for mau in (RE_COT_SELECT, RE_COT_NGOAC, RE_COT_SAU):
            for danh_sach in mau.findall(khong_nhay):
                ung |= set(RE_DINH_DANH.findall(danh_sach))

        for x in sorted(ung):
            if x == ten or x in bang_cot or x in BO_QUA_COT:
                continue
            if x not in bang_cot[ten]:
                loi.append(f"{ma}: sơ đồ nêu {x!r} như cột của {ten!r} mà "
                           "bảng đó không có cột nào tên vậy")
    print(f"   {da_xet} khối nêu đúng một bảng, đã soát tên cột trong đó")
    return loi


def kiem_con_so(spec: str) -> list[str]:
    m = re.search(r"\*\*(\d+) endpoint công khai \+ (\d+) endpoint nội bộ",
                  spec)
    if not m:
        return ["không tìm thấy câu “N endpoint công khai” ở mục 6"]
    khai_cong, khai_noi = int(m.group(1)), int(m.group(2))

    # Khóa là CẶP method + đường dẫn, không phải đường dẫn. `GET /foods` và
    # `POST /foods` là hai endpoint khác nhau dùng chung một đường dẫn —
    # đó là REST bình thường, không phải trùng lặp.
    cong = re.findall(r"^\| \d+ \| .+ \| `(GET|POST|PUT|PATCH|DELETE)` \| "
                      r"`(/[^`]+)` \|", spec, re.M)
    noi = re.findall(r"^\| I\d+ \| .+ \| `(GET|POST)` \| `(/[^`]+)` \|",
                     spec, re.M)
    loi = []
    if len(cong) != khai_cong:
        loi.append(f"mục 6 khai {khai_cong} endpoint công khai mà bảng có "
                   f"{len(cong)} dòng")
    if len(noi) != khai_noi:
        loi.append(f"mục 6 khai {khai_noi} endpoint nội bộ mà bảng có "
                   f"{len(noi)} dòng")
    for x in sorted({t for t in cong if cong.count(t) > 1}):
        loi.append(f"endpoint {x[0]} {x[1]} xuất hiện {cong.count(x)} lần "
                   "trong bảng tổng hợp")

    # Số thứ tự phải liền mạch 1..N, không nhảy cóc và không đụng nhau.
    so = sorted(int(m) for m in re.findall(
        r"^\| (\d+) \| .+ \| `(?:GET|POST|PUT|PATCH|DELETE)` \| `/", spec,
        re.M))
    missing = sorted(set(range(1, khai_cong + 1)) - set(so))
    if missing:
        loi.append(f"bảng tổng hợp thiếu số thứ tự: {missing}")
    for n in sorted({n for n in so if so.count(n) > 1}):
        loi.append(f"số thứ tự {n} dùng cho {so.count(n)} endpoint")
    print(f"   {len(cong)} endpoint công khai + {len(noi)} nội bộ, "
          "khớp con số đã khai")
    return loi


def main() -> int:
    _in_utf8()
    spec = APISPEC.read_text(encoding="utf-8")
    schema = SCHEMA.read_text(encoding="utf-8")

    print("Soát: flowchart ↔ đặc tả API ↔ lược đồ CSDL")
    print("=" * 72)

    loi: list[str] = []
    print("\n1. Endpoint trong sơ đồ phải có trong đặc tả")
    loi += kiem_endpoint(spec)
    print("\n2. Mã lỗi trong sơ đồ phải có trong danh mục mục 4")
    loi += kiem_ma_loi(spec)
    print("\n3. Tên bảng trong sơ đồ phải có trong db/schema.sql")
    loi += kiem_bang(schema)
    print("\n4. Tên cột trong sơ đồ phải có trong bảng của nó")
    loi += kiem_cot(schema)
    print("\n5. Con số khai ở mục 6 phải khớp số dòng")
    loi += kiem_con_so(spec)
    print("\n6. Tên use case phải khớp giữa mdj, flowchart và User story")
    loi += kiem_ten_use_case()

    print("\n7. Luồng chính của 18 kịch bản Chương 2 phải tới được Kết thúc")
    loi += kiem_luong_chuong2()

    print("\n8. Còn chờ bổ sung")
    cho = [(ma, chu) for ma, chu in chu_cac_khoi() if DAU_DE_XUAT in chu]
    for ma, chu in cho:
        print(f"   ! {ma}  {chu}")
    if not cho:
        print("   ✓ không còn chỗ nào")

    print("\n" + "=" * 72)
    if loi:
        print(f"{len(loi)} CHỖ LỆCH:")
        for x in loi:
            print("  -", x)
        return 1
    print("Sơ đồ, đặc tả API và lược đồ CSDL mô tả cùng một hệ thống.")
    if cho:
        print(f"Còn {len(cho)} chỗ chờ bổ sung — xem mục 8.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
