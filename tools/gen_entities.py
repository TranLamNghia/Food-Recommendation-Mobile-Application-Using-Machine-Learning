#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sinh lớp thực thể C# từ `db/schema.sql`, và soát lại chúng.

Vì sao sinh bằng máy. Hai mươi bốn bảng, 225 cột. Gõ tay từng thuộc tính thì
một cột sai tên hoặc sai tính cho phép NULL sẽ không gây lỗi biên dịch — nó
gây một `MySqlException` lúc chạy, ở một endpoint có thể không ai gọi tới
trong nhiều tuần. Sinh từ chính tệp lược đồ thì khoảng sai đó không tồn tại.

Vì sao KHÔNG dùng `dotnet ef dbcontext scaffold`. Công cụ đó đọc CSDL đang
chạy, nên nó đòi CSDL phải sống đúng lúc dựng mã, và nó sinh cả `OnModelCreating`
với toàn bộ chỉ mục, ràng buộc, collation — hàng nghìn dòng mà không ai đọc.
`db/schema.sql` là nguồn quyền lực theo `db/migrations/applied/README.md`, nên
sinh từ tệp đó là sinh từ đúng nguồn, và mã ra đủ nhỏ để đọc được.

HAI CHẾ ĐỘ
    (mặc định)  soát: mã C# đang có phải khớp lược đồ, cả hai chiều
    --ghi       sinh lại Entities/ và AppDbContext.cs

Chạy:
    python tools/gen_entities.py
    python tools/gen_entities.py --ghi
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "db" / "schema.sql"
API = ROOT / "backend" / "Api"
THUC_THE = API / "Entities"
CONTEXT = API / "Data" / "AppDbContext.cs"
#: Không sinh tự động — chỉ được SOÁT, xem `_soat_enum`.
DTOS = API / "Profile" / "ProfileDtos.cs"

NAMESPACE = "Api.Entities"

#: Từ khóa mở đầu một ràng buộc ở cấp bảng, không phải một cột.
CAP_BANG = (
    "PRIMARY KEY", "FOREIGN KEY", "UNIQUE KEY", "UNIQUE INDEX", "UNIQUE (",
    "INDEX", "KEY ", "CONSTRAINT", "CHECK",
)

TU_KHOA_KIEU = (
    "BIGINT", "INT", "SMALLINT", "TINYINT", "MEDIUMINT", "DECIMAL", "NUMERIC",
    "FLOAT", "DOUBLE", "VARCHAR", "CHAR", "TEXT", "LONGTEXT", "MEDIUMTEXT",
    "JSON", "ENUM", "SET", "DATE", "DATETIME", "TIMESTAMP", "TIME", "YEAR",
    "BOOLEAN", "BOOL", "BLOB", "BINARY",
)

#: Họ kiểu MySQL -> kiểu C#. ENUM và SET thành `string`: ánh xạ chúng sang
#: `enum` của C# nghe gọn hơn, nhưng khi CSDL thêm một giá trị mà mã chưa
#: biết thì EF ném lỗi lúc ĐỌC, và một dòng dữ liệu hợp lệ trở thành không
#: đọc nổi. Giữ `string`, và để tầng validation kiểm theo danh sách ở mục 5
#: của đặc tả API.
KIEU = {
    "CHAR": "string", "VARCHAR": "string", "TEXT": "string",
    "LONGTEXT": "string", "MEDIUMTEXT": "string", "JSON": "string",
    "ENUM": "string", "SET": "string",
    "TINYINT": "byte", "SMALLINT": "ushort", "MEDIUMINT": "int",
    "INT": "uint", "BIGINT": "ulong",
    "DECIMAL": "decimal", "NUMERIC": "decimal",
    "FLOAT": "float", "DOUBLE": "double",
    "DATE": "DateOnly", "DATETIME": "DateTime", "TIMESTAMP": "DateTime",
    "TIME": "TimeOnly", "YEAR": "int",
}

#: `TINYINT(1)` trong MySQL là quy ước cho boolean, không phải số 0..255.
#: Lược đồ dùng nó cho `is_active`, `is_hard`, `was_selected`.


def _tach_dinh_nghia(than: str) -> list[str]:
    """Tách thân CREATE TABLE theo dấu phẩy NGOÀI ngoặc và ngoài dấu nháy.

    Tách theo dòng thì một `ENUM(...)` trải nhiều dòng bị cắt làm nhiều mảnh,
    và mảnh đầu không chứa `NOT NULL` nằm ở dòng dưới.
    """
    ra: list[str] = []
    dem: list[str] = []
    sau = 0
    trong_nhay = False
    i, n = 0, len(than)
    while i < n:
        c = than[i]
        if trong_nhay:
            dem.append(c)
            if c == "\\" and i + 1 < n:
                dem.append(than[i + 1])
                i += 2
                continue
            if c == "'":
                trong_nhay = False
        elif c == "'":
            trong_nhay = True
            dem.append(c)
        elif c == "(":
            sau += 1
            dem.append(c)
        elif c == ")":
            sau -= 1
            dem.append(c)
        elif c == "," and sau == 0:
            ra.append("".join(dem))
            dem = []
        else:
            dem.append(c)
        i += 1
    if "".join(dem).strip():
        ra.append("".join(dem))
    return [" ".join(d.split()) for d in ra if d.strip()]


def _bo_chu_thich(chu: str) -> str:
    """Bỏ chú thích `--` nhưng giữ nguyên nội dung trong dấu nháy."""
    ra: list[str] = []
    trong_nhay = False
    i, n = 0, len(chu)
    while i < n:
        c = chu[i]
        if trong_nhay:
            ra.append(c)
            if c == "\\" and i + 1 < n:
                ra.append(chu[i + 1])
                i += 2
                continue
            if c == "'":
                trong_nhay = False
        elif c == "'":
            trong_nhay = True
            ra.append(c)
        elif chu.startswith("--", i):
            while i < n and chu[i] != "\n":
                i += 1
            continue
        else:
            ra.append(c)
        i += 1
    return "".join(ra)


def pascal(ten: str) -> str:
    return "".join(p.capitalize() for p in ten.split("_"))


def doc_luoc_do(chu: str) -> dict[str, list[dict]]:
    """{tên bảng: [cột...]} với kiểu C# đã suy ra, giữ đúng thứ tự khai báo."""
    sach = _bo_chu_thich(chu)
    bang: dict[str, list[dict]] = {}

    for m in re.finditer(r"CREATE TABLE\s+(\w+)\s*\((.*?)\)\s*ENGINE",
                         sach, re.S):
        ten, than = m.group(1), m.group(2)
        cot: list[dict] = []

        # Khóa chính có thể khai ở CẤP BẢNG: `PRIMARY KEY (food_id, tag_id)`.
        # Bỏ sót chỗ này thì EF ném `requires a primary key to be defined`
        # lúc dựng mô hình — nghĩa là MỌI endpoint 500, không chỉ endpoint
        # chạm vào bảng đó, vì mô hình được dựng một lần cho cả DbContext.
        khoa_cap_bang: list[str] = []
        for dn in _tach_dinh_nghia(than):
            kb = re.match(r"PRIMARY KEY\s*\((.+?)\)", dn.strip(), re.I)
            if kb:
                khoa_cap_bang = [c.strip().strip("`")
                                 for c in kb.group(1).split(",")]

        for dn in _tach_dinh_nghia(than):
            if dn.upper().startswith(CAP_BANG):
                continue
            phan = dn.split(None, 1)
            if len(phan) < 2:
                continue
            ten_cot, remaining = phan[0], phan[1]
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", ten_cot):
                continue
            hoa = remaining.upper()
            if not hoa.startswith(TU_KHOA_KIEU):
                continue

            km = re.match(r"([A-Za-z]+)\s*(?:\((.*?)\))?", remaining, re.S)
            ho = km.group(1).upper() if km else ""
            doi_so = (km.group(2) or "").strip() if km else ""

            # Khóa chính ngầm định NOT NULL dù không viết ra.
            la_pk = "PRIMARY KEY" in hoa
            cho_null = "NOT NULL" not in hoa and not la_pk

            cs = KIEU.get(ho, "string")
            if ho == "TINYINT" and doi_so.strip() == "1":
                cs = "bool"

            # Tập giá trị ENUM/SET, giữ ĐÚNG THỨ TỰ khai báo: MySQL lưu ENUM
            # theo thứ số, nên đổi thứ tự là đổi dữ liệu đã có.
            gt = re.findall(r"'([^']*)'", doi_so) if ho in ("ENUM", "SET") \
                else []

            cot.append({
                "db": ten_cot,
                "cs": pascal(ten_cot),
                "kieu": cs,
                "null": cho_null,
                # Cột GENERATED do CSDL tính; EF phải đọc mà không ghi.
                "sinh": "GENERATED" in hoa,
                "pk": la_pk,
                "gt": gt,
            })

        if khoa_cap_bang:
            for c in cot:
                if c["db"] in khoa_cap_bang:
                    c["pk"] = True

        bang[ten] = cot
    return bang


# ── Sinh mã ──────────────────────────────────────────────────────────────

DAU = """// <auto-generated>
//     SINH TỰ ĐỘNG từ db/schema.sql bằng tools/gen_entities.py — ĐỪNG SỬA TAY.
//     Sửa lược đồ thì chạy lại:  python tools/gen_entities.py --ghi
//     Soát lại:                  python tools/gen_entities.py
// </auto-generated>

// Header `<auto-generated>` ở trên làm trình biên dịch TẮT ngữ cảnh nullable
// cho cả tệp, nên mọi `string?` sinh ra sẽ kêu CS8669. Bật lại tường minh.
#nullable enable
"""


def _kieu_cs(c: dict) -> str:
    t = c["kieu"]
    if c["null"]:
        return t + "?"
    return t


def _gia_tri_dau(c: dict) -> str:
    """Giá trị khởi tạo, để `Nullable` không cảnh báo thuộc tính chưa gán."""
    if c["null"]:
        return ""
    if c["kieu"] == "string":
        return " = string.Empty;"
    return ""


def sinh_thuc_the(ten: str, cot: list[dict]) -> str:
    lop = pascal(ten)
    dong = [DAU, "", f"namespace {NAMESPACE};", "",
            f"/// <summary>Bảng <c>{ten}</c>.</summary>",
            f"public class {lop}", "{"]
    for c in cot:
        ghi_chu = []
        if c["pk"]:
            ghi_chu.append("khóa chính")
        if c["sinh"]:
            ghi_chu.append("CSDL tự tính — chỉ đọc")
        hau = f"  // {', '.join(ghi_chu)}" if ghi_chu else ""
        dong.append(f"    public {_kieu_cs(c)} {c['cs']} "
                    f"{{ get; set; }}{_gia_tri_dau(c)}{hau}")
    dong += ["}", ""]
    return "\n".join(dong)


def sinh_context(bang: dict[str, list[dict]]) -> str:
    dong = [
        DAU, "",
        "using Api.Entities;",
        "using Microsoft.EntityFrameworkCore;", "",
        "namespace Api.Data;", "",
        "/// <summary>",
        "/// Ánh xạ 24 bảng của <c>db/schema.sql</c>.",
        "///",
        "/// <para><b>KHÔNG dùng EF Migrations.</b> Theo",
        "/// <c>db/migrations/applied/README.md</c>, <c>db/schema.sql</c> là",
        "/// trạng thái hiện hành của lược đồ. Bật Migrations là tạo ra nguồn",
        "/// quyền lực thứ hai cho cùng một lược đồ, và hai cái sẽ lệch nhau —",
        "/// <c>tools/check_schema_sql.py</c> bắt được, nhưng chỉ <i>sau khi</i>",
        "/// đã lệch. Đổi lược đồ thì viết một tệp trong <c>db/migrations/</c>,",
        "/// chạy nó, gộp vào <c>schema.sql</c>, rồi chạy lại",
        "/// <c>python tools/gen_entities.py --ghi</c>.</para>",
        "/// </summary>",
        "public class AppDbContext(DbContextOptions<AppDbContext> options)",
        "    : DbContext(options)",
        "{",
    ]
    for ten in bang:
        dong.append(f"    public DbSet<{pascal(ten)}> {pascal(ten)} "
                    "=> Set<" + pascal(ten) + ">();")
    dong += ["", "    protected override void OnModelCreating("
                 "ModelBuilder b)", "    {"]
    for ten, cot in bang.items():
        lop = pascal(ten)
        dong.append(f"        b.Entity<{lop}>(e =>")
        dong.append("        {")
        dong.append(f'            e.ToTable("{ten}");')
        khoa = [c for c in cot if c["pk"]]
        if len(khoa) == 1:
            dong.append(f"            e.HasKey(x => x.{khoa[0]['cs']});")
        elif len(khoa) > 1:
            # Khóa phức hợp: `food_tags (food_id, tag_id)`.
            bo = ", ".join(f"x.{c['cs']}" for c in khoa)
            dong.append(f"            e.HasKey(x => new {{ {bo} }});")
        else:
            raise AssertionError(
                f"bảng `{ten}` không có khóa chính nào bóc được — EF sẽ ném "
                "`requires a primary key to be defined` lúc dựng mô hình")
        for c in cot:
            dong.append(f'            e.Property(x => x.{c["cs"]})'
                        f'.HasColumnName("{c["db"]}");')
            if c["sinh"]:
                dong.append(f"            e.Property(x => x.{c['cs']})"
                            ".ValueGeneratedOnAddOrUpdate();")
        dong.append("        });")
    dong += ["    }", "}", ""]
    return "\n".join(dong)


# ── Soát ─────────────────────────────────────────────────────────────────

RE_THUOC_TINH = re.compile(
    r'e\.Property\(x => x\.(\w+)\)\.HasColumnName\("(\w+)"\);')


def soat(bang: dict[str, list[dict]]) -> list[str]:
    """Mã C# đang có phải khớp lược đồ, cả hai chiều."""
    loi: list[str] = []

    if not CONTEXT.exists():
        return [f"chưa có {CONTEXT.relative_to(ROOT)} — chạy với --ghi"]

    # ── 1. Mỗi bảng một tệp thực thể ──
    co_tep = {p.stem for p in THUC_THE.glob("*.cs")}
    can = {pascal(t) for t in bang}
    for t in sorted(can - co_tep):
        loi.append(f"thiếu lớp thực thể {t}.cs")
    for t in sorted(co_tep - can):
        loi.append(f"{t}.cs không ứng với bảng nào trong schema.sql")

    # ── 2. Mỗi cột một thuộc tính, đúng tên và đúng kiểu ──
    for ten, cot in bang.items():
        tep = THUC_THE / f"{pascal(ten)}.cs"
        if not tep.exists():
            continue
        chu = tep.read_text(encoding="utf-8")
        for c in cot:
            mong = f"public {_kieu_cs(c)} {c['cs']} {{ get; set; }}"
            if mong not in chu:
                loi.append(f"{pascal(ten)}.{c['cs']}: mong đợi "
                           f"`{_kieu_cs(c)}`, không thấy trong "
                           f"{tep.name}")

    # ── 3. Khóa chính phải được khai cho TỪNG bảng ──
    #
    # Thiếu một `HasKey` thì EF không ném lúc biên dịch, nó ném lúc dựng mô
    # hình — tức là ở lượt gọi API ĐẦU TIÊN, và khi đó MỌI endpoint trả 500,
    # không chỉ endpoint chạm vào bảng thiếu khóa. Đúng lỗi đó đã xảy ra với
    # `food_tags`, bảng duy nhất khai `PRIMARY KEY` ở cấp bảng.
    ctx_tam = CONTEXT.read_text(encoding="utf-8")
    for ten, cot in bang.items():
        khoa = [c["cs"] for c in cot if c["pk"]]
        if not khoa:
            loi.append(f"`{ten}` không bóc được khóa chính nào")
            continue
        mong = (f"e.HasKey(x => x.{khoa[0]});" if len(khoa) == 1
                else "e.HasKey(x => new { "
                     + ", ".join(f"x.{k}" for k in khoa) + " });")
        if mong not in ctx_tam:
            loi.append(f"AppDbContext thiếu `{mong}` cho bảng `{ten}`")

    # ── 4. Ánh xạ tên cột trong DbContext phải đủ và đúng ──
    ctx = CONTEXT.read_text(encoding="utf-8")
    anh_xa = set(RE_THUOC_TINH.findall(ctx))
    can_anh_xa = {(c["cs"], c["db"]) for cot in bang.values() for c in cot}
    for cs, db in sorted(can_anh_xa - anh_xa):
        loi.append(f"AppDbContext thiếu ánh xạ {cs} -> `{db}`")

    # ── 5. Danh sách ENUM trong ProfileDtos.cs phải khớp lược đồ ──
    loi += _soat_enum(bang)

    return loi


#: {tên trường trong Api.Profile.Enums: (bảng, cột)}.
#:
#: Khai tường minh chứ không dò tên, vì lược đồ có HAI ENUM tên `gender` với
#: tập giá trị KHÁC nhau: `health_profiles.gender` là
#: ('male','female','other'), còn `rda_reference.gender` là
#: ('male','female','all'). Dò theo tên cột sẽ bắt sai một trong hai.
ENUM_CS = {
    "Gender": ("health_profiles", "gender"),
    "ActivityLevel": ("health_profiles", "activity_level"),
    "Goal": ("health_profiles", "goal"),
    "Severity": ("user_conditions", "severity"),
}

RE_DS_ENUM = re.compile(
    r"public static readonly string\[\]\s+(\w+)\s*=\s*\[(.*?)\]\s*;", re.S)


def _soat_enum(bang: dict[str, list[dict]]) -> list[str]:
    """Bốn mảng trong `Api.Profile.Enums` phải khớp ENUM của lược đồ.

    Bốn mảng đó là tầng DUY NHẤT trả `400 VALIDATION_FAILED` kèm tên trường
    cho một giá trị ngoài ENUM. Thiếu phép kiểm này thì thêm một giá trị vào
    `db/schema.sql` sẽ làm API từ chối chính thứ CSDL cho phép — và không có
    gì báo ra, vì cả hai bên vẫn tự nhất quán.
    """
    loi: list[str] = []
    if not DTOS.exists():
        return [f"chưa có {DTOS.relative_to(ROOT)}"]

    co = {m.group(1): re.findall(r'"([^"]*)"', m.group(2))
          for m in RE_DS_ENUM.finditer(DTOS.read_text(encoding="utf-8"))}

    # Hai chiều: một mảng mới thêm vào mà không khai ở ENUM_CS cũng là lệch —
    # nó trông như được soát mà thật ra không.
    for ten in sorted(set(co) - set(ENUM_CS)):
        loi.append(f"Enums.{ten} không có trong ENUM_CS của gen_entities.py "
                   f"— chưa ai đối chiếu nó với lược đồ")

    for ten, (ten_bang, ten_cot) in ENUM_CS.items():
        if ten not in co:
            loi.append(f"ProfileDtos.cs thiếu `string[] {ten}`")
            continue
        cot = next((c for c in bang.get(ten_bang, [])
                    if c["db"] == ten_cot), None)
        if cot is None:
            loi.append(f"schema.sql không có cột `{ten_bang}.{ten_cot}`")
            continue
        if cot["gt"] != co[ten]:
            loi.append(
                f"Enums.{ten} = {co[ten]} nhưng "
                f"{ten_bang}.{ten_cot} ENUM{tuple(cot['gt'])}")
    return loi


def main(argv: list[str] | None = None) -> int:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ghi", action="store_true",
                    help="sinh lại Entities/ và AppDbContext.cs")
    ts = ap.parse_args(argv)

    bang = doc_luoc_do(SCHEMA.read_text(encoding="utf-8"))
    so_cot = sum(len(c) for c in bang.values())
    print(f"db/schema.sql: {len(bang)} bảng · {so_cot} cột")

    if ts.ghi:
        THUC_THE.mkdir(parents=True, exist_ok=True)
        CONTEXT.parent.mkdir(parents=True, exist_ok=True)
        # Xóa lớp của bảng đã bỏ, nếu không chúng vẫn biên dịch được và vẫn
        # trông như một phần của lược đồ.
        giu = {pascal(t) + ".cs" for t in bang}
        for p in THUC_THE.glob("*.cs"):
            if p.name not in giu:
                p.unlink()
                print(f"  - xóa {p.name} (bảng không còn)")
        for ten, cot in bang.items():
            (THUC_THE / f"{pascal(ten)}.cs").write_text(
                sinh_thuc_the(ten, cot), encoding="utf-8")
        CONTEXT.write_text(sinh_context(bang), encoding="utf-8")
        print(f"  đã ghi {len(bang)} lớp + AppDbContext.cs")

    loi = soat(bang)
    print()
    if loi:
        print(f"{len(loi)} CHỖ LỆCH:")
        for x in loi:
            print("  -", x)
        return 1
    print("Mã C# mô tả đúng lược đồ — từng cột, cả hai chiều.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
