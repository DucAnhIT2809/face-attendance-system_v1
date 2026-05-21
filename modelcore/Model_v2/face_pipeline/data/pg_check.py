"""Kiểm tra kết nối PostgreSQL và schema liên quan điểm danh."""

from __future__ import annotations

import argparse
import sys

from face_pipeline.data.pg_settings import (
    DEFAULT_PG_DBNAME,
    DEFAULT_PG_HOST,
    DEFAULT_PG_PORT,
    DEFAULT_PG_USER,
    connect_pg,
    default_pg_password,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kiểm tra kết nối PostgreSQL (face_attendance_db).")
    p.add_argument("--db-host", type=str, default=DEFAULT_PG_HOST)
    p.add_argument("--db-port", type=int, default=DEFAULT_PG_PORT)
    p.add_argument("--db-name", type=str, default=DEFAULT_PG_DBNAME)
    p.add_argument("--db-user", type=str, default=DEFAULT_PG_USER)
    p.add_argument(
        "--db-password",
        type=str,
        default=None,
        help="Mặc định: biến FACE_ATTENDANCE_PG_PASSWORD hoặc 1234",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    pwd = args.db_password if args.db_password is not None else default_pg_password()
    print(f"Thử kết nối: host={args.db_host} port={args.db_port} db={args.db_name} user={args.db_user}")
    try:
        conn = connect_pg(
            host=args.db_host,
            port=args.db_port,
            dbname=args.db_name,
            user=args.db_user,
            password=pwd,
        )
    except Exception as exc:
        print(f"Lỗi kết nối: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    with conn.cursor() as cur:
        cur.execute("SELECT version();")
        print("PostgreSQL:", cur.fetchone()[0][:80], "...")
        cur.execute("SELECT current_database(), current_user;")
        row = cur.fetchone()
        print(f"current_database={row[0]} current_user={row[1]}")

        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name;
            """
        )
        tables = [r[0] for r in cur.fetchall()]
        print("Bảng public:", ", ".join(tables) if tables else "(trống)")

        track_table = "yolo_face_attendance"
        if track_table in tables:
            cur.execute(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position;
                """,
                (track_table,),
            )
            print(f"Cột {track_table} (điểm danh từ webcam track):")
            for col, dtype, nul in cur.fetchall():
                print(f"  - {col}: {dtype} nullable={nul}")
        else:
            print(
                f"(Chưa có bảng {track_table} — sẽ được tạo khi chạy `face_pipeline track` với DB bật)"
            )

        if "attendance_records" in tables:
            print(
                "Lưu ý: Có bảng `attendance_records` (schema app khác). "
                "Pipeline track không ghi vào bảng này để tránh xung đột cột (vd. session_id)."
            )

        if "students" in tables:
            cur.execute("SELECT COUNT(*) FROM students;")
            print("Số bản ghi students:", cur.fetchone()[0])

    conn.close()
    print("Kết nối OK, đã đóng.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
