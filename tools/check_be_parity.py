#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bước 1 phải cho cùng một bộ số ở cả ba bản hiện thực.

    tools/gen_buoc1_cases.py                    Python — bản tham chiếu
    backend/Api/Nutrition/NutritionTargets.cs   C#     — máy chủ
    mobile/lib/data/models/health_profile.dart  Dart   — ứng dụng

Vì sao cần. Ba bản chạy ở ba tầng và không bao giờ gặp nhau. Khi chúng lệch,
**không gì báo ra**: ứng dụng hiện một hạn mức năng lượng, máy chủ sinh thực
đơn theo một hạn mức khác, và cả hai con số đều trông hợp lý. Người dùng
không có cách nào biết, và lập trình viên cũng không — cho tới khi ai đó
ngồi tính tay.

Chuyện đó đã xảy ra, ba lần, và cả ba đều do bộ kiểm này bắt được khi nó
chạy lần đầu:

  · **macro 17/60/23 ở Dart** trong khi cột `DEFAULT` của CSDL và đặc tả API
    đều ghi 15/60/25. Ba nguồn, hai con số.
  · **`mealDistribution` 25/40/27/8 trong đặc tả** trong khi `meal_plan.dart`
    dùng điểm giữa các khoảng của SYSTEM_ARCHITECTURE §3.1, tức
    27.5/37.5/27.5/7.5. Cả hai bộ đều nằm trong khoảng và đều cộng đủ 100 %,
    nên không bộ nào trông sai.
  · **`bmiCategory: "normal"` cho bmi 23.15 trong đặc tả**, trong khi hệ
    thống dùng ngưỡng châu Á 23/25 — ở đó 23.15 là `overweight`.

BA PHÉP KIỂM
    1. sinh lại `data/buoc1_cases.json` từ bản tham chiếu Python
    2. `dotnet test` — 44 phép kiểm C#, không cần CSDL
    3. `flutter test test/buoc1_parity_test.dart` — 32 phép kiểm Dart

Chạy:
    python tools/check_be_parity.py
    python tools/check_be_parity.py --chi-sinh
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import gen_buoc1_cases  # noqa: E402

CA = ROOT / "data" / "buoc1_cases.json"
BE = ROOT / "backend"
MOBILE = ROOT / "mobile"
BAI_DART = "test/buoc1_parity_test.dart"


def _in_utf8() -> None:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass


def chay(lenh: list[str], cwd: pathlib.Path) -> tuple[int, str] | None:
    """Chạy một lệnh ngoài; trả `None` khi không tìm thấy nó trong PATH.

    Phải tra PATH tường minh bằng `shutil.which`: trên Windows `flutter` và
    `dotnet` là tệp `.bat`/`.cmd`, và `CreateProcess` không tự thêm đuôi —
    gọi thẳng `["flutter", ...]` sẽ ném `FileNotFoundError` dù chính lệnh đó
    chạy được từ dòng lệnh.
    """
    duong = shutil.which(lenh[0])
    if duong is None:
        return None
    r = subprocess.run(
        [duong, *lenh[1:]], cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main(argv: list[str] | None = None) -> int:
    _in_utf8()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chi-sinh", action="store_true",
                    help="chỉ sinh tệp ca thử, không gọi hai bộ kiểm")
    ts = ap.parse_args(argv)

    print("Soát: Bước 1 — Python ↔ C# ↔ Dart")
    print("=" * 72)

    # ── 1. Sinh ca thử ───────────────────────────────────────────────────
    print("\n1. Bản tham chiếu Python")
    if gen_buoc1_cases.main([]) != 0:
        return 1
    if ts.chi_sinh:
        return 0

    loi: list[str] = []

    # ── 2. C# ────────────────────────────────────────────────────────────
    print("\n2. C# — backend/Api.Tests")
    kq = chay(["dotnet", "test", "--nologo"], BE)
    if kq is None:
        print("   ! không thấy `dotnet` trong PATH — bỏ qua phần C#")
        print("     chạy bằng tay:  cd backend && dotnet test")
        loi.append("không chạy được phần C# (thiếu `dotnet` trong PATH)")
        ma, chu = 0, ""
    else:
        ma, chu = kq
    for dong in chu.splitlines():
        if "Passed!" in dong or "Failed!" in dong or "error" in dong.lower():
            print(f"   {dong.strip()[:120]}")
    if ma != 0:
        loi.append("dotnet test thất bại")

    # ── 3. Dart ──────────────────────────────────────────────────────────
    print("\n3. Dart — mobile/test/buoc1_parity_test.dart")
    kq = chay(["flutter", "test", BAI_DART], MOBILE)
    if kq is None:
        print("   ! không thấy `flutter` trong PATH — bỏ qua phần Dart")
        print(f"     chạy bằng tay:  cd mobile && flutter test {BAI_DART}")
        loi.append("không chạy được phần Dart (thiếu `flutter` trong PATH)")
        ma, chu = 0, ""
    else:
        ma, chu = kq
    dong_cuoi = [d for d in chu.splitlines() if d.strip()]
    if dong_cuoi:
        print(f"   {dong_cuoi[-1].strip()[:120]}")
    # Những ca bị bỏ qua phải NÓI RA, không được lẫn vào số liệu "đạt":
    # `Gender` của Dart không có `other`, nên ba ca giới tính thứ ba không
    # kiểm được ở bản Dart. Im lặng về chúng là để một khoảng trống thật
    # trông như đã được phủ.
    bo_qua = [d.strip() for d in chu.splitlines()
              if "không có 'other'" in d or "DateTime.now()" in d]
    if bo_qua:
        print(f"   {len(bo_qua)} ca bỏ qua ở bản Dart:")
        for d in sorted(set(bo_qua)):
            print(f"     ~ {d[:110]}")
    if ma != 0:
        loi.append("flutter test thất bại")

    print("\n" + "=" * 72)
    if loi:
        print(f"{len(loi)} CHỖ LỆCH:")
        for x in loi:
            print("  -", x)
        print("\nXem đầu ra đầy đủ:")
        print("    cd backend && dotnet test")
        print(f"    cd mobile  && flutter test {BAI_DART}")
        return 1
    print("Ba bản hiện thực Bước 1 cho cùng một bộ số.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
