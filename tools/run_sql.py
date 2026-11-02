#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chạy tệp .sql lên MySQL qua pymysql.

Tồn tại vì máy phát triển không có `mysql` CLI trong PATH, mà tách câu lệnh
bằng `split(';')` là sai: dấu chấm phẩy nằm trong chuỗi hoặc trong chú thích
sẽ cắt câu lệnh làm đôi. Bộ tách ở đây duyệt từng ký tự và theo dõi trạng
thái chuỗi, nên chỉ cắt ở dấu chấm phẩy thật sự kết thúc câu lệnh.

Chạy:
    python tools/run_sql.py db/schema.sql
    python tools/run_sql.py db/seed.sql --database nutrition_rec
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402


def split_statements(sql: str) -> list[str]:
    """Tách thành từng câu lệnh, bỏ qua dấu ; trong chuỗi và chú thích."""
    out: list[str] = []
    buf: list[str] = []
    i, n = 0, len(sql)
    quote: str | None = None

    while i < n:
        ch = sql[i]

        if quote:
            buf.append(ch)
            if ch == "\\" and i + 1 < n:          # ký tự thoát
                buf.append(sql[i + 1])
                i += 2
                continue
            if ch == quote:
                # Hai dấu nháy liền nhau là một dấu nháy nằm trong chuỗi.
                if i + 1 < n and sql[i + 1] == quote:
                    buf.append(sql[i + 1])
                    i += 2
                    continue
                quote = None
            i += 1
            continue

        # Chú thích một dòng: bỏ tới hết dòng.
        if sql.startswith("--", i) or sql.startswith("#", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j
            continue

        # Chú thích khối.
        if sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue

        if ch in ("'", '"', "`"):
            quote = ch
            buf.append(ch)
            i += 1
            continue

        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument(
        "--database", default=None,
        help="chọn CSDL trước khi chạy; bỏ qua nếu tệp tự CREATE/USE",
    )
    args = parser.parse_args()

    try:
        import pymysql
    except ImportError:
        sys.exit("Cần cài pymysql:  pip install pymysql")

    conn = pymysql.connect(
        host=_env.get("MYSQL_HOST", "localhost"),
        port=int(_env.get("MYSQL_PORT", "3306")),
        user=_env.require("MYSQL_USER"),
        password=_env.require("MYSQL_PASSWORD"),
        charset="utf8mb4",
        autocommit=False,
    )

    try:
        with conn.cursor() as cur:
            if args.database:
                cur.execute(f"USE `{args.database}`")

            for path in args.files:
                statements = split_statements(path.read_text(encoding="utf-8"))
                print(f"\n{path}  —  {len(statements)} câu lệnh")

                for idx, stmt in enumerate(statements, start=1):
                    try:
                        cur.execute(stmt)
                    except Exception as exc:
                        conn.rollback()
                        head = " ".join(stmt.split())[:160]
                        sys.exit(
                            f"\nLỖI ở câu lệnh {idx}/{len(statements)} của {path}\n"
                            f"  {head}…\n\n{exc}\n\nĐã hoàn tác."
                        )
                print(f"  → chạy xong")

        conn.commit()
        print("\nĐã commit.")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
