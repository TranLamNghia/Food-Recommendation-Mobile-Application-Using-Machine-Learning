# -*- coding: utf-8 -*-
"""Đọc tệp `.env` ở gốc dự án.

Viết tay thay vì dùng `python-dotenv` để bộ công cụ chạy được ngay sau khi
clone, không cần cài thêm gì. Cả tệp chỉ có một việc: nạp các cặp khóa–giá
trị vào `os.environ` nếu chúng chưa được đặt sẵn.

Biến đã có trong môi trường luôn được ưu tiên hơn tệp `.env`. Nhờ vậy khi
chạy trong CI hay khi muốn thử nhanh một khóa khác, chỉ cần đặt biến môi
trường mà không phải sửa tệp:

    USDA_API_KEY=abc python tools/fill_gaps_usda.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path | None = None) -> dict[str, str]:
    """Nạp `.env` vào `os.environ`. Trả về những khóa đã nạp thêm."""
    env_path = path or ROOT / ".env"
    loaded: dict[str, str] = {}

    if not env_path.exists():
        return loaded

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if not key or not value:
            continue
        # Không ghi đè biến đã có sẵn trong môi trường.
        if key in os.environ:
            continue

        os.environ[key] = value
        loaded[key] = value

    return loaded


def require(name: str, hint: str = "") -> str:
    """Lấy một biến bắt buộc, báo lỗi rõ ràng nếu thiếu."""
    load_env()
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(
            f"Thiếu biến môi trường {name}.\n"
            f"Chép .env.example thành .env rồi điền giá trị."
            + (f"\n{hint}" if hint else "")
        )
    return value


def get(name: str, default: str = "") -> str:
    """Lấy một biến tùy chọn."""
    load_env()
    return os.environ.get(name, default).strip() or default


def in_utf8() -> None:
    """Bắt stdout nhận được tiếng Việt trên Windows (mặc định là cp1252).

    Không gọi hàm này thì mọi bộ kiểm in ký tự ✓ ✗ hay khung kẻ sẽ **chết giữa
    lúc chạy** với UnicodeEncodeError, chứ không phải in ra chữ sai. Chạy trực
    tiếp trên console thì có thể không thấy vì console Windows mới đã là utf-8;
    lỗi chỉ nổ khi đầu ra bị chuyển hướng qua ống hoặc vào tệp — tức là đúng
    lúc chạy trong CI. Cùng một hàm với `ml.db.in_utf8`; để ở hai nơi vì `ml/`
    không phụ thuộc vào `tools/`.
    """
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover - console lạ
            pass
