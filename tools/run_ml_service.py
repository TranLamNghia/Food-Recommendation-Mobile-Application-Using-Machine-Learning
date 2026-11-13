#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chạy ML Service — bốn endpoint nội bộ ở `API_SPECIFICATION.md` mục 8.

Bản song song của `tools/run_backend.py`, và làm đúng ba việc như nó: nối
`.env` vào tiến trình, sinh khóa nếu chưa có, rồi chạy máy chủ.

`ML_INTERNAL_KEY` không có trong `.env` thì tệp này SINH một khóa và ghi vào
đó. Không đặt khóa mặc định trong mã nguồn: repo này là repo công khai, và
dịch vụ này đọc thẳng cơ sở dữ liệu, kể cả bảng `users`.

Backend đọc cùng biến ấy để đặt header `X-Internal-Key`, nên hai bên khớp
nhau mà không ai phải chép khóa bằng tay.

Chạy:
    python tools/run_ml_service.py                  # http://localhost:8000
    python tools/run_ml_service.py --reload         # nạp lại khi sửa mã
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

ENV = ROOT / ".env"
TEN_KHOA = "ML_INTERNAL_KEY"


def khoa_noi_bo() -> str:
    """Khóa dùng chung giữa Backend và ML Service; sinh nếu `.env` chưa có."""
    co = _env.get(TEN_KHOA, "")
    if co:
        return co

    moi = base64.b64encode(secrets.token_bytes(32)).decode()
    with ENV.open("a", encoding="utf-8") as f:
        f.write(
            "\n# Khóa dùng chung Backend ↔ ML Service, header "
            "X-Internal-Key.\n"
            "# Sinh tự động bởi tools/run_ml_service.py. Backend đọc cùng "
            "biến này.\n"
        )
        f.write(f"{TEN_KHOA}={moi}\n")
    print(f"Đã sinh {TEN_KHOA} và ghi vào {ENV.name} (32 byte, không in ra đây)")
    return moi


def main(argv: list[str] | None = None) -> int:
    _env.in_utf8()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument(
        "--port",
        type=int,
        default=8000,
        help="cổng lắng nghe; mặc định 8000 theo đặc tả §2.1",
    )
    ap.add_argument(
        "--reload", action="store_true", help="nạp lại khi mã nguồn đổi"
    )
    ts = ap.parse_args(argv)

    moi_truong = dict(os.environ)
    moi_truong[TEN_KHOA] = khoa_noi_bo()
    for ten in (
        "MYSQL_HOST",
        "MYSQL_PORT",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
        "MYSQL_DATABASE",
    ):
        gia_tri = _env.get(ten, "")
        if gia_tri:
            moi_truong[ten] = gia_tri

    thieu = [t for t in ("MYSQL_USER", "MYSQL_PASSWORD") if not moi_truong.get(t)]
    if thieu:
        print(f"Thiếu {', '.join(thieu)} trong .env", file=sys.stderr)
        return 1

    # Lắng nghe trên 127.0.0.1 chứ không 0.0.0.0, có chủ ý: đây là dịch vụ
    # NỘI BỘ, đặc tả mục 8 nói rõ "không lộ ra Internet, không đi qua
    # Gateway". Mở ra mọi giao diện mạng thì chỉ còn khóa dùng chung đứng
    # giữa cơ sở dữ liệu và bên ngoài.
    lenh = [
        sys.executable,
        "-m",
        "uvicorn",
        "ml.api:app",
        "--host",
        ts.host,
        "--port",
        str(ts.port),
    ]
    if ts.reload:
        lenh.append("--reload")

    print(
        f"ML Service: http://{ts.host}:{ts.port}   "
        f"(CSDL {moi_truong.get('MYSQL_DATABASE', 'nutrition_rec')})"
    )
    print(f"  tài liệu tương tác: http://{ts.host}:{ts.port}/docs")
    return subprocess.call(lenh, env=moi_truong, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
