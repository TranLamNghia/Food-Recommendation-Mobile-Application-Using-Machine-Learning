# -*- coding: utf-8 -*-
"""Mở kết nối tới CSDL `nutrition_rec`.

Dùng lại `tools/_env.py` thay vì đọc `.env` lần nữa, để chỉ có **một** chỗ
biết cách lấy mật khẩu. Mật khẩu không bao giờ được in ra.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import _env  # noqa: E402

import pymysql  # noqa: E402
from pymysql.cursors import DictCursor  # noqa: E402

TEN_CSDL = "nutrition_rec"


def ket_noi(database: str | None = None, *, dict_cursor: bool = True):
    """Trả về một kết nối pymysql đã mở.

    `database` để trống thì dùng CSDL thật. Truyền tên khác khi muốn chạy
    thử trên CSDL nháp mà không chạm vào dữ liệu đang có.
    """
    _env.load_env()
    thieu = [k for k in ("MYSQL_USER", "MYSQL_PASSWORD") if not os.environ.get(k)]
    if thieu:
        raise SystemExit(
            "Thiếu biến môi trường: " + ", ".join(thieu) + "\n"
            "Chép .env.example thành .env rồi điền giá trị."
        )

    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=database or TEN_CSDL,
        charset="utf8mb4",
        cursorclass=DictCursor if dict_cursor else pymysql.cursors.Cursor,
        autocommit=False,
    )


def in_utf8() -> None:
    """Bắt stdout nhận được tiếng Việt trên Windows (mặc định là cp1252)."""
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover - console lạ
            pass
