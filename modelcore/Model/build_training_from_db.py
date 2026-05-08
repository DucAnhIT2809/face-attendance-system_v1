from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a filtered training folder from PostgreSQL student records."
    )
    parser.add_argument("--db-host", type=str, default="localhost")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-name", type=str, required=True)
    parser.add_argument("--db-user", type=str, required=True)
    parser.add_argument("--db-password", type=str, required=True)
    parser.add_argument("--class-code", type=str, default=None, help="Optional class filter.")
    parser.add_argument("--output-dir", type=str, default="TrainingSelected")
    parser.add_argument(
        "--link-mode",
        choices=["copy", "symlink"],
        default="copy",
        help="Use symlink for faster builds or copy for portability.",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def reset_output(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"Output already exists: {output_dir}. Use --overwrite.")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def fetch_students(conn, class_code: str | None) -> list[dict]:
    query = """
    SELECT s.student_code, s.face_folder
    FROM students s
    WHERE s.deleted_at IS NULL
      AND s.status = 'active'
    """
    params = []
    if class_code:
        query += " AND s.class_code = %s"
        params.append(class_code)
    query += " ORDER BY s.student_code;"
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, tuple(params))
        return cur.fetchall()


def add_file(source_path: Path, target_path: Path, link_mode: str) -> None:
    if link_mode == "symlink":
        target_path.symlink_to(source_path)
        return
    shutil.copy2(source_path, target_path)


def collect_images(face_folder: Path) -> list[Path]:
    return sorted(
        p
        for p in face_folder.iterdir()
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    )


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    reset_output(output_dir, overwrite=args.overwrite)

    conn = psycopg2.connect(
        host=args.db_host,
        port=args.db_port,
        dbname=args.db_name,
        user=args.db_user,
        password=args.db_password,
    )
    try:
        students = fetch_students(conn, args.class_code)
    finally:
        conn.close()

    if not students:
        raise ValueError("No active students found for training.")

    copied_students = 0
    copied_images = 0
    for student in students:
        student_code = student["student_code"]
        face_folder = Path(student["face_folder"])
        if not face_folder.exists():
            print(f"Skip {student_code}: face folder not found -> {face_folder}")
            continue

        image_paths = collect_images(face_folder)
        if not image_paths:
            print(f"Skip {student_code}: no images found in {face_folder}")
            continue

        dst_folder = output_dir / student_code
        dst_folder.mkdir(parents=True, exist_ok=True)
        for image_path in image_paths:
            add_file(image_path.resolve(), dst_folder / image_path.name, args.link_mode)
            copied_images += 1
        copied_students += 1

    if copied_students == 0:
        raise ValueError("No valid student folders copied to output dataset.")

    print(f"Output dir: {output_dir}")
    print(f"Students included: {copied_students}")
    print(f"Images included: {copied_images}")
    print(
        "Next step: train with `python Model/arcface_train.py --training-dir "
        f"{output_dir}`"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
