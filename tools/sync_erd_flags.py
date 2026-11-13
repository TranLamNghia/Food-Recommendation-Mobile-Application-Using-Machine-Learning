#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Đồng bộ cờ pk / fk / uq / uqc **và giá trị ENUM** trong ERD HTML từ CSDL.

Mỗi cột trên sơ đồ là một mảng bốn phần tử:

    ['role', 'ENUM', 'uq', 'user|admin']
      tên     kiểu   cờ    giá trị ENUM, ngăn bằng dấu |

Phần tử thứ tư chỉ có ở cột ENUM và SET, và **luôn sinh từ
`information_schema`** chứ không chép tay: 30 cột ENUM với 108 giá trị thì
chép tay sẽ sai, và sai kiểu lặng lẽ — sơ đồ vẫn vẽ ra bình thường với một
giá trị không tồn tại.

Cờ trong `docs/database_erd.html` trước đây được gõ tay, và đã sai theo kiểu
rất khó thấy: `body_logs.logged_on` và `meal_plans.plan_date` đeo huy hiệu
`UQ` trần, làm người đọc tưởng **một mình cột đó là duy nhất** — tức hai
người dùng không thể cùng ghi cân nặng trong một ngày. Thực tế ràng buộc là
`UNIQUE (user_id, logged_on)`, hoàn toàn cho phép.

Hướng ngược lại cũng sai: năm ràng buộc UNIQUE ghép khác không được hiển thị
gì cả, nên người đọc không biết chúng tồn tại.

Script này đọc `information_schema` rồi ghi lại cờ, nên sơ đồ không thể lệch
khỏi CSDL nữa. Chạy lại sau mỗi lần đổi lược đồ.

Bốn cờ:
    pk   khóa chính
    fk   khóa ngoại
    uq   duy nhất, MỘT cột
    uqc  duy nhất theo TỔ HỢP nhiều cột

Chạy:
    python tools/sync_erd_flags.py            # ghi vào ERD
    python tools/sync_erd_flags.py --dry-run  # chỉ in khác biệt
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ERD = ROOT / "docs" / "database_erd.html"

# Cột sinh tự động giữ nguyên cờ `gen` — thông tin đó không nằm trong các
# bảng ràng buộc mà nằm ở `extra` của information_schema.
KEEP = {"gen"}


def read_enums(database: str) -> dict[tuple[str, str], str]:
    """Giá trị của từng cột ENUM/SET, nối bằng dấu `|`.

    Giữ đúng **thứ tự khai báo** trong CSDL, không sắp lại: thứ tự của ENUM
    là một phần ngữ nghĩa — `severity_min` đi từ `mild` đến `severe`, và
    MySQL so sánh ENUM theo thứ tự đó.
    """
    import pymysql

    conn = pymysql.connect(
        host=_env.get("MYSQL_HOST", "localhost"),
        port=int(_env.get("MYSQL_PORT", "3306")),
        user=_env.require("MYSQL_USER"),
        password=_env.require("MYSQL_PASSWORD"),
        database=database,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE "
                "FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND DATA_TYPE IN ('enum', 'set')",
                (database,),
            )
            return {
                (table, column): "|".join(
                    re.findall(r"'([^']*)'", column_type)
                )
                for table, column, column_type in cur.fetchall()
            }
    finally:
        conn.close()


def read_keys(database: str) -> dict[tuple[str, str], set[str]]:
    import pymysql

    conn = pymysql.connect(
        host=_env.get("MYSQL_HOST", "localhost"),
        port=int(_env.get("MYSQL_PORT", "3306")),
        user=_env.require("MYSQL_USER"),
        password=_env.require("MYSQL_PASSWORD"),
        database=database, charset="utf8mb4",
    )
    flags: dict[tuple[str, str], set[str]] = {}

    try:
        with conn.cursor() as cur:
            # Khóa chính và khóa duy nhất. Số cột của chỉ mục quyết định
            # `uq` hay `uqc`.
            cur.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME, INDEX_NAME,
                       COUNT(*) OVER (PARTITION BY TABLE_NAME, INDEX_NAME) AS n
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = %s AND NON_UNIQUE = 0
                """,
                (database,),
            )
            for table, column, index, n in cur.fetchall():
                key = (table, column)
                if index == "PRIMARY":
                    flags.setdefault(key, set()).add("pk")
                else:
                    flags.setdefault(key, set()).add("uq" if n == 1 else "uqc")

            cur.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL
                """,
                (database,),
            )
            for table, column in cur.fetchall():
                flags.setdefault((table, column), set()).add("fk")
    finally:
        conn.close()

    return flags


def order(flags: set[str]) -> str:
    """Thứ tự cố định để diff giữa các lần chạy không nhiễu."""
    return " ".join(f for f in ("pk", "fk", "uq", "uqc", "gen") if f in flags)



def _in_utf8() -> None:
    """Bắt stdout nhận tiếng Việt trên Windows (mặc định cp1252).

    Không gọi thì script chết giữa lúc chạy với UnicodeEncodeError ngay khi
    đầu ra bị chuyển hướng qua ống hoặc vào tệp — tức đúng lúc chạy trong CI.
    Bản sao của `tools/_env.use_utf8`; để ở đây vì `tools/baocao/` không chắc
    có `tools/` trên `sys.path`.
    """
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover
            pass

def main() -> int:
    _in_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="nutrition_rec")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    live = read_keys(args.database)
    enums = read_enums(args.database)
    html = ERD.read_text(encoding="utf-8")
    changes: list[str] = []

    def patch_table(match: re.Match) -> str:
        table = match.group(1)
        body = match.group(2)

        def patch_col(cm: re.Match) -> str:
            column = cm.group(1)
            type_ = cm.group(2)
            old = set((cm.group(3) or "").split()) - {""}
            old_values = cm.group(4)

            new = set(live.get((table, column), set())) | (old & KEEP)
            if new != old:
                changes.append(
                    f"  {table}.{column:<22} cờ "
                    f"[{order(old) or '—'}] → [{order(new) or '—'}]"
                )

            values = enums.get((table, column))
            if (values or "") != (old_values or ""):
                changes.append(
                    f"  {table}.{column:<22} ENUM "
                    f"[{old_values or '—'}] → [{values or '—'}]"
                )

            tail = f",'{values}'" if values else ""
            return f"['{column}','{type_}','{order(new)}'{tail}]"

        patched = re.sub(
            r"\['(\w+)','([^']*)'(?:,'([^']*)')?(?:,'([^']*)')?\]",
            patch_col,
            body,
        )
        return match.group(0).replace(body, patched)

    out = re.sub(
        r"\{ id:'(\w+)'.*?cols:\[(.*?)\]\s*\}", patch_table, html, flags=re.S
    )

    if not changes:
        print("Cờ và giá trị ENUM trong ERD đã khớp CSDL, không có gì để sửa.")
        return 0

    print(f"{len(changes)} chỗ cần sửa:\n")
    for line in changes:
        print(line)

    if args.dry_run:
        print("\n(--dry-run: không ghi tệp)")
        return 1

    ERD.write_text(out, encoding="utf-8")
    print(f"\nĐã ghi → {ERD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
