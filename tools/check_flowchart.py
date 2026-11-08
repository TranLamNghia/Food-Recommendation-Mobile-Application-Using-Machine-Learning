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

BỐN PHÉP KIỂM
    1. endpoint  sơ đồ -> đặc tả    mọi `METHOD /path` phải có trong §6
    2. mã lỗi    sơ đồ -> đặc tả    mọi mã phải có trong danh mục §4
    3. tên bảng  sơ đồ -> CSDL      mọi bảng phải có trong db/schema.sql
    4. con số    đặc tả -> đặc tả   "N endpoint công khai" phải bằng số dòng

Chạy:
    python tools/check_flowchart.py
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "baocao"))

from flowchart_data import DAU_DE_XUAT, SO_DO  # noqa: E402

APISPEC = ROOT / "docs" / "API_SPECIFICATION.md"
SCHEMA = ROOT / "db" / "schema.sql"

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


def chu_cac_khoi() -> list[tuple[str, str]]:
    """(mã sơ đồ, chữ trong khối) cho mọi khối của cả 18 sơ đồ."""
    return [(ma, k[4]) for ma, _, khoi, _ in SO_DO for k in khoi]


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
    thieu = sorted(set(range(1, khai_cong + 1)) - set(so))
    if thieu:
        loi.append(f"bảng tổng hợp thiếu số thứ tự: {thieu}")
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
    print("\n4. Con số khai ở mục 6 phải khớp số dòng")
    loi += kiem_con_so(spec)

    print("\n5. Còn chờ bổ sung")
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
        print(f"Còn {len(cho)} chỗ chờ bổ sung — xem mục 5.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
