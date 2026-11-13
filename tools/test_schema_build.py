#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dựng `db/schema.sql` + `db/seed.sql` vào một CSDL dùng một lần rồi kiểm.

Vì sao cần một công cụ riêng thay vì chạy thẳng tệp schema: **`db/schema.sql`
mở đầu bằng `DROP DATABASE IF EXISTS nutrition_rec`**. Nó là script dựng lại
từ đầu, nên chạy nó để "thử xem lược đồ có đúng không" sẽ xóa sạch CSDL đang
làm việc.

Chuyện này đã xảy ra thật một lần: một phép thử dựng lại tưởng là chạy trên
CSDL nháp đã xóa 305 món trong CSDL thật, vì câu `USE nutrition_rec` ở đầu tệp
lặng lẽ chuyển kết nối về đó bất chấp tham số `database=` lúc kết nối. Lần đó
không mất gì — toàn bộ món dựng lại được từ `data/foods/*.csv` — nhưng khi
CSDL đã có dữ liệu người dùng thật thì sẽ không may như vậy.

Công cụ này đổi tên CSDL trong cả hai tệp trước khi chạy, rồi **kiểm lại rằng
kết nối thật sự đang ở CSDL nháp** trước khi đo bất cứ thứ gì. Phép kiểm đó
quan trọng không kém phần đổi tên: nếu đổi tên không ăn, mọi con số bên dưới
vẫn trả về đúng vì chúng đang đo CSDL thật, và bài kiểm hóa ra vô nghĩa mà
trông như đã đạt.

Kiểm những gì:
  · quy mô: số bảng, số cột khóa ngoại, số ràng buộc CHECK, tổng số cột
  · không còn khóa UNIQUE nào chứa cột cho phép NULL (xem migration 003)
  · không định danh nào mang dấu tiếng Việt (yêu cầu của bài tập ERD)
  · seed nạp được và các bảng tra cứu có đúng số dòng

Chạy:
    python tools/test_schema_build.py
"""

from __future__ import annotations

import pathlib
import re
import sys

import _env  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

# Dùng lại bộ tách câu lệnh của `run_sql.py` thay vì chép thêm một bản. Hai
# bản sẽ lệch nhau: bản này sửa được một ca lạ thì bản kia vẫn sai, mà cả hai
# đều chạy lên cùng một CSDL.
from run_sql import split_statements  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "db" / "schema.sql"
SEED = ROOT / "db" / "seed.sql"
SANDBOX = "nutrition_rec_buildtest"

# Số liệu mong đợi. Đối chiếu chứ không chỉ in ra, vì một thay đổi lược đồ
# ngoài ý muốn thường chỉ lệch đúng một con số — in ra thì rất dễ đọc qua.
EXPECTED = {
    "tables": 24,
    "fk_columns": 32,
    "checks": 18,
    "columns": 225,
}

LOOKUP_ROWS = {
    "food_categories": 12,
    "tags": 13,
    "conditions": 13,
    "condition_rules": 20,
    "rda_reference": 12,
}


def read_env() -> dict[str, str]:
    env_file = ROOT / ".env"
    if not env_file.exists():
        sys.exit("Chưa có .env")
    return dict(
        re.findall(r"^(\w+)=(.*)$", env_file.read_text(encoding="utf-8"), re.M)
    )


def rename_database(text: str, real: str) -> str:
    """Trỏ tệp sang CSDL nháp.

    Bắt theo ranh giới từ, nếu không thì `nutrition_rec_buildtest` sẽ bị đổi
    thêm một lần nữa ở những lần khớp sau.
    """
    return re.compile(rf"\b{re.escape(real)}\b").sub(SANDBOX, text)


def assert_no_real_db(label: str, text: str, real: str) -> None:
    """Chốt an toàn cuối: không còn câu DROP DATABASE / USE nào trỏ về thật."""
    for line in text.split("\n"):
        upper = line.upper().strip()
        touches = "DROP DATABASE" in upper or upper.startswith("USE ")
        if touches and re.search(rf"\b{re.escape(real)}\b", line):
            sys.exit(
                f"{label} vẫn còn câu lệnh trỏ vào CSDL thật sau khi đổi tên "
                f"— dừng lại:\n  {line.strip()}"
            )


def main() -> int:
    _env.use_utf8()
    try:
        import pymysql
    except ImportError:
        sys.exit("Cần cài pymysql:  pip install pymysql")

    env = read_env()
    real_db = env.get("MYSQL_DATABASE", "nutrition_rec")

    if SANDBOX == real_db:
        sys.exit(
            f"CSDL nháp trùng tên CSDL thật ({real_db}) — chạy tiếp sẽ xóa "
            f"dữ liệu thật. Dừng lại."
        )

    schema_sql = rename_database(SCHEMA.read_text(encoding="utf-8"), real_db)
    seed_sql = rename_database(SEED.read_text(encoding="utf-8"), real_db)
    assert_no_real_db("schema.sql", schema_sql, real_db)
    assert_no_real_db("seed.sql", seed_sql, real_db)

    print("═" * 70)
    print(f"DỰNG LƯỢC ĐỒ VÀO CSDL NHÁP  {SANDBOX}")
    print(f"(CSDL thật {real_db} không bị chạm tới)")
    print("═" * 70)

    connect = dict(
        host=env.get("MYSQL_HOST", "localhost"),
        port=int(env.get("MYSQL_PORT", "3306")),
        user=env["MYSQL_USER"],
        password=env["MYSQL_PASSWORD"],
        charset="utf8mb4",
        autocommit=True,
    )

    connection = pymysql.connect(**connect)
    failures: list[str] = []

    try:
        with connection.cursor() as cursor:
            for label, text in (
                ("schema.sql", schema_sql),
                ("seed.sql", seed_sql),
            ):
                statements = split_statements(text)
                errors = 0
                for number, statement in enumerate(statements, start=1):
                    try:
                        cursor.execute(statement)
                    except Exception as exc:  # noqa: BLE001
                        errors += 1
                        failures.append(f"{label} câu {number}: {exc}")
                        print(f"  ✗ câu {number}: {exc}")
                        if errors > 3:
                            break
                print(f"{label}: {len(statements)} câu lệnh, {errors} lỗi")

            cursor.execute("SELECT DATABASE()")
            current = cursor.fetchone()[0]
            if current != SANDBOX:
                sys.exit(
                    f"Kết nối đang ở CSDL {current!r}, không phải "
                    f"{SANDBOX!r}. Dừng lại để không đo nhầm CSDL thật."
                )
            print(f"\nđang ở CSDL: {current}")

            # ── Quy mô ──
            cursor.execute("SHOW TABLES")
            measured = {"tables": len(cursor.fetchall())}

            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "  AND REFERENCED_TABLE_NAME IS NOT NULL"
            )
            measured["fk_columns"] = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA = DATABASE() AND CONSTRAINT_TYPE = 'CHECK'"
            )
            measured["checks"] = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE()"
            )
            measured["columns"] = cursor.fetchone()[0]

            print("\nQuy mô:")
            for key, want in EXPECTED.items():
                got = measured[key]
                mark = "✓" if got == want else "✗"
                print(f"  {mark} {key:<12}{got:>5}   (mong đợi {want})")
                if got != want:
                    failures.append(f"{key}: đo {got}, mong đợi {want}")

            # ── Khóa UNIQUE bị NULL vô hiệu hóa ──
            cursor.execute(
                "SELECT s.TABLE_NAME, s.INDEX_NAME,"
                "       GROUP_CONCAT(CASE WHEN s.NULLABLE = 'YES'"
                "                    THEN s.COLUMN_NAME END"
                "                    ORDER BY s.SEQ_IN_INDEX) AS nullable_cols"
                "  FROM information_schema.STATISTICS s"
                " WHERE s.TABLE_SCHEMA = DATABASE() AND s.NON_UNIQUE = 0"
                " GROUP BY s.TABLE_NAME, s.INDEX_NAME"
                " HAVING nullable_cols IS NOT NULL"
            )
            leaky = cursor.fetchall()
            print(f"\nKhóa UNIQUE chứa cột cho phép NULL: {len(leaky)}")
            for table, index, columns in leaky:
                print(f"  ✗ {table}.{index} — cột NULL được: {columns}")
                failures.append(
                    f"{table}.{index} không chặn trùng vì cột {columns} "
                    f"cho phép NULL"
                )
            if not leaky:
                print("  ✓ không còn khóa nào bị NULL vô hiệu hóa")

            # ── Dấu tiếng Việt trong định danh ──
            cursor.execute(
                "SELECT TABLE_NAME, COLUMN_NAME "
                "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE()"
            )
            identifiers: set[str] = set()
            for table, column in cursor.fetchall():
                identifiers.add(table)
                identifiers.add(column)

            accented = sorted(n for n in identifiers if not n.isascii())
            print(
                f"\nĐịnh danh: {len(identifiers)} tên, "
                f"{len(accented)} tên có dấu"
            )
            if accented:
                for name in accented:
                    print(f"  ✗ {name}")
                failures.append(f"{len(accented)} định danh có dấu tiếng Việt")
            else:
                print("  ✓ không tên nào có dấu — đúng yêu cầu bài tập ERD")

            # ── Seed ──
            print("\nBảng tra cứu sau seed:")
            for table, want in LOOKUP_ROWS.items():
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                got = cursor.fetchone()[0]
                mark = "✓" if got == want else "✗"
                print(f"  {mark} {table:<18}{got:>4}   (mong đợi {want})")
                if got != want:
                    failures.append(f"{table}: {got} dòng, mong đợi {want}")
    finally:
        # Dọn bằng một kết nối khác: kết nối đang mở đứng trong chính CSDL
        # sắp xóa.
        cleanup = pymysql.connect(**connect)
        with cleanup.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS {SANDBOX}")
        cleanup.close()
        connection.close()
        print(f"\n(đã xóa CSDL nháp {SANDBOX})")

    print("\n" + "═" * 70)
    if failures:
        print(f"{len(failures)} vấn đề:\n")
        for item in failures:
            print(f"  ✗ {item}")
    else:
        print("LƯỢC ĐỒ DỰNG LẠI ĐƯỢC TỪ ĐẦU — không có vấn đề nào.")
    print("═" * 70)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
