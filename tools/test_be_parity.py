#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Thử phủ định bộ kiểm parity Bước 1 — nó có thật sự so không?

Một bộ kiểm luôn báo đạt thì vô dụng, và không có cách nào biết điều đó từ
việc nhìn nó báo đạt. Tệp này cố ý làm lệch một con số rồi đòi
`dotnet test` và `flutter test` phải THẤT BẠI.

## Vì sao chỉ sửa tệp SINH RA, không sửa mã nguồn

Bản đầu của bài thử này sửa thẳng hằng số trong
`backend/Api/Nutrition/NutritionTargets.cs` rồi khôi phục trong `finally`.
Phiên làm việc bị cắt giữa ca thứ ba, và `finally` không chạy — **lỗi tiêm
`BmiOverweightAsia = 25.0m` nằm lại trong mã thật**, cùng một tệp `.thubak`
không ai để ý. Mã vẫn biên dịch, vẫn chạy, chỉ là nó phân loại BMI theo
ngưỡng quốc tế thay vì ngưỡng châu Á.

Nên bài thử này chỉ sửa `data/buoc1_cases.json` — một tệp do
`tools/gen_buoc1_cases.py` sinh ra. Bị cắt giữa đường thì hậu quả tối đa là
một tệp sinh lại được bằng một lệnh, và chính `check_be_parity.py` sinh lại
nó ở bước 1 của mọi lần chạy.

Phép so là đối xứng: làm lệch phía tệp mẫu chứng minh phép so đang sống,
đúng như làm lệch phía mã nguồn.

Chạy:
    python tools/thu_be_parity.py
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CA = ROOT / "data" / "buoc1_cases.json"
BE = ROOT / "backend"
MOBILE = ROOT / "mobile"
BAI_DART = "test/buoc1_parity_test.dart"

#: (nhãn, đường dẫn trong JSON, hàm làm lệch)
#:
#: Mỗi ca nhắm vào một phần khác nhau của phép tính, để một phép so bị bỏ
#: sót không núp sau một phép so khác.
THU = [
    ("tuoi excess 1", ["age"], lambda v: v + 1),
    ("bmi excess 0.01", ["bmi"], lambda v: round(v + 0.01, 2)),
    ("nhom BMI doi", ["bmiCategory"],
     lambda v: "normal" if v != "normal" else "obese"),
    ("BMR excess 5 kcal", ["bmrKcal"], lambda v: v + 5),
    ("TDEE excess 1 kcal", ["tdeeKcal"], lambda v: v + 1),
    ("he so van dong excess 0.005", ["activityFactor"],
     lambda v: round(v + 0.005, 3)),
    ("han muc nang luong excess 1", ["dailyCaloriesTarget"], lambda v: v + 1),
    ("dam excess 0.1 g", ["proteinG"], lambda v: round(v + 0.1, 1)),
    ("bot duong excess 0.1 g", ["carbsG"], lambda v: round(v + 0.1, 1)),
    ("beo excess 0.1 g", ["fatG"], lambda v: round(v + 0.1, 1)),
    ("kcal bua trua excess 1", ["mealKcal", "lunch"], lambda v: v + 1),
]

#: Hai bảng hệ số ở cấp tệp, không thuộc ca nào — `Bang_he_so_khop_hai_chieu`
#: bên C# và hai phép kiểm tương ứng bên Dart phải bắt.
THU_BANG = [
    ("bang he so: them mot muc van dong",
     lambda m: m["activityFactor"].update({"extreme": 2.1})),
    ("bang he so: doi he so moderate",
     lambda m: m["activityFactor"].update({"moderate": 1.6})),
    ("bang ty le bua: tong khong con 1.0",
     lambda m: m["mealShare"].update({"snack": 0.05})),
]

#: Ca áp lỗi vào. `dac-ta-7.2.3` vì nó là ca của ví dụ trong đặc tả.
CA_NHAM = "dac-ta-7.2.3"


def _in_utf8() -> None:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass


def sinh_lai() -> None:
    subprocess.run(
        [sys.executable, "tools/gen_buoc1_cases.py"], cwd=str(ROOT),
        capture_output=True, text=True,
        env=dict(os.environ, PYTHONIOENCODING="utf-8"), check=True,
    )


def chay_hai_bo() -> bool:
    """`True` nếu CẢ HAI bộ kiểm đều đạt — tức là lỗi tiêm đã LỌT."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    cs = subprocess.run(
        [shutil.which("dotnet") or "dotnet", "test", "--nologo"],
        cwd=str(BE), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env)
    dart = subprocess.run(
        [shutil.which("flutter") or "flutter", "test", BAI_DART],
        cwd=str(MOBILE), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env)
    return cs.returncode == 0 and dart.returncode == 0


def dat_sau(d: dict, duong: list[str], ham) -> bool:
    """Áp `ham` vào giá trị ở `duong`; `False` nếu không có đường đó."""
    cho = d
    for k in duong[:-1]:
        if k not in cho:
            return False
        cho = cho[k]
    cuoi = duong[-1]
    if cuoi not in cho:
        return False
    cho[cuoi] = ham(cho[cuoi])
    return True


def main() -> int:
    _in_utf8()
    print("Thử phủ định: bộ kiểm parity Bước 1 có thật sự so không?")
    print("=" * 72)
    print("Chỉ sửa data/buoc1_cases.json — tệp sinh ra. Mã nguồn không bị")
    print("chạm tới, nên bị cắt giữa đường chỉ cần sinh lại một tệp.")
    print()

    sinh_lai()
    goc = CA.read_text(encoding="utf-8")
    lot: list[str] = []

    try:
        for nhan, duong, ham in THU:
            mau = json.loads(goc)
            ca = next(c for c in mau["cases"] if c["ten"] == CA_NHAM)
            if not dat_sau(ca["ra"], duong, ham):
                print(f"  [BO QUA] {nhan} — không có đường "
                      f"{'.'.join(duong)} trong ca {CA_NHAM}")
                continue
            CA.write_text(json.dumps(mau, ensure_ascii=False, indent=2)
                          + "\n", encoding="utf-8")
            if chay_hai_bo():
                lot.append(nhan)
                print(f"  [LỌT]     {nhan}")
            else:
                print(f"  [bắt được] {nhan}")

        for nhan, ham in THU_BANG:
            mau = json.loads(goc)
            ham(mau)
            CA.write_text(json.dumps(mau, ensure_ascii=False, indent=2)
                          + "\n", encoding="utf-8")
            if chay_hai_bo():
                lot.append(nhan)
                print(f"  [LỌT]     {nhan}")
            else:
                print(f"  [bắt được] {nhan}")
    finally:
        # Khôi phục bằng cách SINH LẠI, không bằng cách ghi lại `goc`: nếu
        # tiến trình bị cắt trước đây thì `check_be_parity.py` vẫn sinh lại
        # ở bước 1, nên tệp không bao giờ ở trạng thái lệch lâu.
        sinh_lai()

    total = len(THU) + len(THU_BANG)
    print()
    print("=" * 72)
    print(f"{total - len(lot)}/{total} lỗi tiêm bị bắt được")
    if lot:
        print("LỌT — bộ kiểm không so những phần này:")
        for x in lot:
            print("  -", x)
        return 1
    print("Bộ kiểm parity so thật, từng con số một.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
