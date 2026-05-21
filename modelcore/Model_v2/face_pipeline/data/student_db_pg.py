from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from face_pipeline.data.pg_settings import (
    DEFAULT_PG_DBNAME,
    DEFAULT_PG_USER,
    default_pg_password,
)
from face_pipeline.paths import REPO_ROOT


VALID_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VALID_STATUSES = {"active", "inactive", "out_of_class"}


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    dbname: str
    user: str
    password: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage students and face images in PostgreSQL.")
    parser.add_argument("--db-host", type=str, default="localhost")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-name", type=str, default=DEFAULT_PG_DBNAME)
    parser.add_argument("--db-user", type=str, default=DEFAULT_PG_USER)
    parser.add_argument("--db-password", type=str, default=default_pg_password())
    parser.add_argument("--training-dir", type=str, default=str(REPO_ROOT / "Training"))
    parser.add_argument("--command", required=True, choices=[
        "init-schema",
        "add-student",
        "update-student",
        "soft-delete-student",
        "hard-delete-student",
        "add-face-image",
        "list-training-students",
    ])
    parser.add_argument("--student-code", type=str)
    parser.add_argument("--new-student-code", type=str)
    parser.add_argument("--full-name", type=str)
    parser.add_argument("--class-code", type=str)
    parser.add_argument("--email", type=str)
    parser.add_argument("--phone", type=str)
    parser.add_argument("--status", type=str, choices=sorted(VALID_STATUSES))
    parser.add_argument("--image", type=str, help="Path to one face image.")
    parser.add_argument("--is-primary", action="store_true")
    parser.add_argument("--purge-face-folder", action="store_true")
    parser.add_argument("--filter-class-code", type=str, help="Class filter for list-training-students.")
    return parser.parse_args()


def get_connection(config: DbConfig):
    from face_pipeline.data.pg_settings import connect_pg

    return connect_pg(
        host=config.host,
        port=config.port,
        dbname=config.dbname,
        user=config.user,
        password=config.password,
    )


def real_dict_cursor():
    from psycopg2.extras import RealDictCursor

    return RealDictCursor


def init_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'student_status') THEN
                CREATE TYPE student_status AS ENUM ('active', 'inactive', 'out_of_class');
              END IF;
            END$$;
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
              id BIGSERIAL PRIMARY KEY,
              student_code VARCHAR(30) NOT NULL UNIQUE,
              full_name VARCHAR(120) NOT NULL,
              class_code VARCHAR(50) NOT NULL,
              email VARCHAR(120),
              phone VARCHAR(20),
              status student_status NOT NULL DEFAULT 'active',
              face_folder TEXT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              deleted_at TIMESTAMPTZ
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS student_faces (
              id BIGSERIAL PRIMARY KEY,
              student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
              image_path TEXT NOT NULL,
              is_primary BOOLEAN NOT NULL DEFAULT FALSE,
              is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_students_class_status
              ON students(class_code, status)
              WHERE deleted_at IS NULL;
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_faces_student
              ON student_faces(student_id)
              WHERE is_deleted = FALSE;
            """
        )
    conn.commit()


def ensure_valid_image(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")
    if path.suffix.lower() not in VALID_IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image extension: {path.suffix}")


def copy_face_image(source_path: Path, face_folder: Path) -> Path:
    face_folder.mkdir(parents=True, exist_ok=True)
    destination = face_folder / source_path.name
    index = 1
    while destination.exists():
        destination = face_folder / f"{source_path.stem}_{index}{source_path.suffix.lower()}"
        index += 1
    shutil.copy2(source_path, destination)
    return destination


def add_student(
    conn,
    training_dir: Path,
    student_code: str,
    full_name: str,
    class_code: str,
    email: Optional[str],
    phone: Optional[str],
    image_path: Optional[Path],
) -> None:
    face_folder = (training_dir / student_code).resolve()
    face_folder_str = str(face_folder)

    with conn.cursor(cursor_factory=real_dict_cursor()) as cur:
        cur.execute(
            """
            INSERT INTO students (student_code, full_name, class_code, email, phone, status, face_folder)
            VALUES (%s, %s, %s, %s, %s, 'active', %s)
            RETURNING id, student_code;
            """,
            (student_code, full_name, class_code, email, phone, face_folder_str),
        )
        student = cur.fetchone()

        if image_path is not None:
            ensure_valid_image(image_path)
            saved_image_path = copy_face_image(image_path, face_folder)
            cur.execute(
                """
                INSERT INTO student_faces (student_id, image_path, is_primary)
                VALUES (%s, %s, %s);
                """,
                (student["id"], str(saved_image_path), True),
            )
    conn.commit()


def get_student(conn, student_code: str) -> Optional[dict]:
    with conn.cursor(cursor_factory=real_dict_cursor()) as cur:
        cur.execute(
            """
            SELECT id, student_code, full_name, class_code, email, phone, status, face_folder, deleted_at
            FROM students
            WHERE student_code = %s;
            """,
            (student_code,),
        )
        return cur.fetchone()


def update_student(
    conn,
    old_student_code: str,
    new_student_code: Optional[str],
    full_name: Optional[str],
    class_code: Optional[str],
    email: Optional[str],
    phone: Optional[str],
    status: Optional[str],
    image_path: Optional[Path],
) -> None:
    student = get_student(conn, old_student_code)
    if student is None:
        raise ValueError(f"Student not found: {old_student_code}")
    if status is not None and status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")

    target_student_code = new_student_code or student["student_code"]
    target_face_folder = Path(student["face_folder"])
    if target_student_code != student["student_code"]:
        target_face_folder = target_face_folder.parent / target_student_code

    updates = {
        "student_code": target_student_code,
        "full_name": full_name if full_name is not None else student["full_name"],
        "class_code": class_code if class_code is not None else student["class_code"],
        "email": email if email is not None else student["email"],
        "phone": phone if phone is not None else student["phone"],
        "status": status if status is not None else student["status"],
        "face_folder": str(target_face_folder.resolve()),
    }

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE students
            SET student_code = %s,
                full_name = %s,
                class_code = %s,
                email = %s,
                phone = %s,
                status = %s,
                face_folder = %s,
                updated_at = NOW()
            WHERE id = %s;
            """,
            (
                updates["student_code"],
                updates["full_name"],
                updates["class_code"],
                updates["email"],
                updates["phone"],
                updates["status"],
                updates["face_folder"],
                student["id"],
            ),
        )

        old_folder = Path(student["face_folder"])
        new_folder = Path(updates["face_folder"])
        if old_folder.exists() and old_folder != new_folder:
            new_folder.parent.mkdir(parents=True, exist_ok=True)
            old_folder.rename(new_folder)

        if image_path is not None:
            ensure_valid_image(image_path)
            saved_image_path = copy_face_image(image_path, new_folder)
            cur.execute(
                """
                INSERT INTO student_faces (student_id, image_path, is_primary)
                VALUES (%s, %s, %s);
                """,
                (student["id"], str(saved_image_path), False),
            )
    conn.commit()


def soft_delete_student(conn, student_code: str, purge_face_folder: bool) -> None:
    student = get_student(conn, student_code)
    if student is None:
        raise ValueError(f"Student not found: {student_code}")
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE students
            SET status = 'out_of_class',
                deleted_at = NOW(),
                updated_at = NOW()
            WHERE id = %s;
            """,
            (student["id"],),
        )
        cur.execute(
            """
            UPDATE student_faces
            SET is_deleted = TRUE
            WHERE student_id = %s;
            """,
            (student["id"],),
        )
    conn.commit()

    if purge_face_folder:
        face_folder = Path(student["face_folder"])
        if face_folder.exists():
            shutil.rmtree(face_folder)


def hard_delete_student(conn, student_code: str, purge_face_folder: bool) -> None:
    student = get_student(conn, student_code)
    if student is None:
        raise ValueError(f"Student not found: {student_code}")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM students WHERE id = %s;", (student["id"],))
    conn.commit()

    if purge_face_folder:
        face_folder = Path(student["face_folder"])
        if face_folder.exists():
            shutil.rmtree(face_folder)


def add_face_image(conn, student_code: str, image_path: Path, is_primary: bool) -> None:
    student = get_student(conn, student_code)
    if student is None:
        raise ValueError(f"Student not found: {student_code}")
    ensure_valid_image(image_path)
    face_folder = Path(student["face_folder"])
    saved_image_path = copy_face_image(image_path, face_folder)

    with conn.cursor() as cur:
        if is_primary:
            cur.execute("UPDATE student_faces SET is_primary = FALSE WHERE student_id = %s;", (student["id"],))
        cur.execute(
            """
            INSERT INTO student_faces (student_id, image_path, is_primary)
            VALUES (%s, %s, %s);
            """,
            (student["id"], str(saved_image_path), is_primary),
        )
        cur.execute("UPDATE students SET updated_at = NOW() WHERE id = %s;", (student["id"],))
    conn.commit()


def list_training_students(conn, class_code: Optional[str]) -> Iterable[dict]:
    query = """
    SELECT s.id, s.student_code, s.full_name, s.class_code, s.face_folder,
           COUNT(sf.id) FILTER (WHERE sf.is_deleted = FALSE) AS face_image_count
    FROM students s
    LEFT JOIN student_faces sf ON sf.student_id = s.id
    WHERE s.deleted_at IS NULL
      AND s.status = 'active'
    """
    params = []
    if class_code:
        query += " AND s.class_code = %s"
        params.append(class_code)
    query += """
    GROUP BY s.id
    ORDER BY s.class_code, s.student_code;
    """
    with conn.cursor(cursor_factory=real_dict_cursor()) as cur:
        cur.execute(query, tuple(params))
        return cur.fetchall()


def require_args(args: argparse.Namespace, names: list[str]) -> None:
    missing = [name for name in names if getattr(args, name.replace("-", "_")) in (None, "")]
    if missing:
        raise ValueError(f"Missing required args for command: {', '.join(missing)}")


def main() -> None:
    args = parse_args()
    config = DbConfig(
        host=args.db_host,
        port=args.db_port,
        dbname=args.db_name,
        user=args.db_user,
        password=args.db_password,
    )
    training_dir = Path(args.training_dir).resolve()
    training_dir.mkdir(parents=True, exist_ok=True)

    with get_connection(config) as conn:
        command = args.command
        if command == "init-schema":
            init_schema(conn)
            print("Initialized PostgreSQL schema successfully.")
            return

        if command == "add-student":
            require_args(args, ["student_code", "full_name", "class_code"])
            image_path = Path(args.image).resolve() if args.image else None
            add_student(
                conn=conn,
                training_dir=training_dir,
                student_code=args.student_code,
                full_name=args.full_name,
                class_code=args.class_code,
                email=args.email,
                phone=args.phone,
                image_path=image_path,
            )
            print(f"Added student: {args.student_code}")
            return

        if command == "update-student":
            require_args(args, ["student_code"])
            image_path = Path(args.image).resolve() if args.image else None
            update_student(
                conn=conn,
                old_student_code=args.student_code,
                new_student_code=args.new_student_code,
                full_name=args.full_name,
                class_code=args.class_code,
                email=args.email,
                phone=args.phone,
                status=args.status,
                image_path=image_path,
            )
            print(f"Updated student: {args.student_code}")
            return

        if command == "soft-delete-student":
            require_args(args, ["student_code"])
            soft_delete_student(conn, args.student_code, args.purge_face_folder)
            print(f"Soft-deleted student: {args.student_code}")
            return

        if command == "hard-delete-student":
            require_args(args, ["student_code"])
            hard_delete_student(conn, args.student_code, args.purge_face_folder)
            print(f"Hard-deleted student: {args.student_code}")
            return

        if command == "add-face-image":
            require_args(args, ["student_code", "image"])
            add_face_image(conn, args.student_code, Path(args.image).resolve(), args.is_primary)
            print(f"Added face image for: {args.student_code}")
            return

        if command == "list-training-students":
            rows = list_training_students(conn, args.filter_class_code)
            print(f"Training students: {len(rows)}")
            for row in rows:
                print(
                    f"{row['student_code']} | {row['full_name']} | "
                    f"{row['class_code']} | images={row['face_image_count']} | {row['face_folder']}"
                )
            return

        raise ValueError(f"Unsupported command: {command}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
