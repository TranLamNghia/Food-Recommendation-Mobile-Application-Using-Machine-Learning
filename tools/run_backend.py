#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chạy backend với biến môi trường lấy từ `.env`.

Vì sao cần. `backend/Api/Program.cs` đọc chuỗi kết nối và khóa ký JWT từ biến
môi trường, không từ `appsettings.json` — repo này là repo công khai, nên một
khóa ký nằm trong tệp được commit thì mọi ai đọc được repo đều ký được token
hợp lệ. Tệp này nối `.env` (đã gitignore) vào tiến trình `dotnet`.

`JWT_SIGNING_KEY` không có trong `.env` thì tệp này SINH một khóa và ghi
thêm vào `.env`. Sinh mới mỗi lần chạy thì mọi token phát ở lần chạy trước
trở thành không hợp lệ, và việc đó trông giống một lỗi xác thực.

Chạy:
    python tools/run_backend.py
    python tools/run_backend.py --build      # chỉ dựng, không chạy
"""

from __future__ import annotations

import argparse
import base64
import os
import pathlib
import secrets
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import _env  # noqa: E402

DU_AN = ROOT / "backend" / "Api"
ENV = ROOT / ".env"


def khoa_ky() -> str:
    """Khóa ký JWT, sinh và ghi vào `.env` nếu chưa có."""
    co = _env.get("JWT_SIGNING_KEY", "")
    if co:
        return co

    moi = base64.b64encode(secrets.token_bytes(48)).decode()
    with ENV.open("a", encoding="utf-8") as f:
        f.write("\n# Khóa ký JWT (HMAC-SHA256). Sinh tự động bởi "
                "tools/run_backend.py.\n")
        f.write("# Đổi khóa này làm mọi accessToken đang sống trở thành "
                "không hợp lệ.\n")
        f.write(f"JWT_SIGNING_KEY={moi}\n")
    print(f"Đã sinh JWT_SIGNING_KEY và ghi vào {ENV.name} "
          "(48 byte, không in ra đây)")
    return moi


def main(argv: list[str] | None = None) -> int:
    _env.in_utf8()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true",
                    help="chỉ `dotnet build`, không chạy")
    ap.add_argument("--urls", default="http://localhost:5000",
                    help="địa chỉ lắng nghe; mặc định theo đặc tả §2.1")
    ts = ap.parse_args(argv)

    moi_truong = dict(os.environ)
    moi_truong["JWT_SIGNING_KEY"] = khoa_ky()
    for ten in ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD",
                "MYSQL_DATABASE"):
        gia_tri = _env.get(ten, "")
        if gia_tri:
            moi_truong[ten] = gia_tri

    missing = [t for t in ("MYSQL_USER", "MYSQL_PASSWORD")
             if not moi_truong.get(t)]
    if missing:
        print(f"Thiếu {', '.join(missing)} trong .env", file=sys.stderr)
        return 1

    if ts.build:
        lenh = ["dotnet", "build", str(DU_AN)]
    else:
        lenh = ["dotnet", "run", "--project", str(DU_AN),
                "--urls", ts.urls]
        print(f"Backend: {ts.urls}/api/v1   "
              f"(CSDL {moi_truong.get('MYSQL_DATABASE', 'nutrition_rec')})")

    return subprocess.call(lenh, env=moi_truong, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
