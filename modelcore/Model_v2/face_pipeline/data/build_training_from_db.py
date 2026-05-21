from __future__ import annotations

import argparse
import os
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

from face_pipeline.data.pg_settings import (
    DEFAULT_PG_DBNAME,
    DEFAULT_PG_USER,
    default_pg_password,
    connect_pg,
)
from face_pipeline.paths import REPO_ROOT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a filtered training folder from PostgreSQL student records."
    )
    parser.add_argument("--db-host", type=str, default="localhost")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-name", type=str, default=DEFAULT_PG_DBNAME)
    parser.add_argument("--db-user", type=str, default=DEFAULT_PG_USER)
    parser.add_argument("--db-password", type=str, default=default_pg_password())
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Full PostgreSQL URL (overrides --db-* when set).",
    )
    parser.add_argument("--class-code", type=str, default=None, help="Optional course class filter (cc.class_code).")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(REPO_ROOT / "TrainingSelected"),
        help="Output root: one subfolder per student_code.",
    )
    parser.add_argument(
        "--link-mode",
        choices=["copy", "symlink"],
        default="copy",
        help="Use symlink for faster builds or copy for portability.",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--include-pending",
        action="store_true",
        help="Also include PENDING uploaded images.",
    )
    return parser.parse_args()


def reset_output(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"Output already exists: {output_dir}. Use --overwrite.")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def fetch_training_images(conn, class_code: str | None, include_pending: bool) -> list[dict]:
    query = """
    SELECT st.student_code, sfi.image_path
    FROM students st
    JOIN course_class_students ccs ON ccs.student_id = st.id AND ccs.status = 'ACTIVE'
    JOIN course_classes cc ON cc.id = ccs.course_class_id
    JOIN student_face_images sfi ON sfi.student_id = st.id
    WHERE st.status = 'ACTIVE'
      AND (
        sfi.status = 'VALID'
        OR sfi.is_used_for_training = TRUE
    """
    params: list[str] = []
    if include_pending:
        query += " OR sfi.status = 'PENDING'"
    query += ")"
    if class_code:
        query += " AND cc.class_code = %s"
        params.append(class_code)
    query += " ORDER BY st.student_code, sfi.uploaded_at;"
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, tuple(params))
        return cur.fetchall()


def fetch_legacy_face_folders(conn, class_code: str | None) -> list[dict]:
    query = """
    SELECT DISTINCT st.student_code, st.face_folder
    FROM students st
    JOIN course_class_students ccs ON ccs.student_id = st.id AND ccs.status = 'ACTIVE'
    JOIN course_classes cc ON cc.id = ccs.course_class_id
    WHERE st.status = 'ACTIVE'
      AND st.face_folder IS NOT NULL
    """
    params: list[str] = []
    if class_code:
        query += " AND cc.class_code = %s"
        params.append(class_code)
    query += " ORDER BY st.student_code;"
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, tuple(params))
        return cur.fetchall()


def add_file(source_path: Path, target_path: Path, link_mode: str) -> bool:
    if not source_path.exists():
        return False
    if link_mode == "symlink":
        target_path.symlink_to(source_path)
        return True
    shutil.copy2(source_path, target_path)
    return True


def download_http(uri: str, target_path: Path) -> bool:
    with urllib.request.urlopen(uri, timeout=30) as response:
        target_path.write_bytes(response.read())
    return True


def download_s3(uri: str, target_path: Path) -> bool:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("Install boto3 to read s3:// image paths") from exc

    parsed = urllib.parse.urlparse(uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    client = boto3.client(
        "s3",
        region_name=os.getenv("S3_REGION"),
        endpoint_url=os.getenv("S3_ENDPOINT_URL"),
        aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
    )
    obj = client.get_object(Bucket=bucket, Key=key)
    target_path.write_bytes(obj["Body"].read())
    return True


def add_image_uri(uri: str, target_path: Path, link_mode: str) -> bool:
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme in {"http", "https"}:
        return download_http(uri, target_path)
    if parsed.scheme == "s3":
        return download_s3(uri, target_path)
    return add_file(Path(uri), target_path, link_mode)


def collect_images(face_folder: Path) -> list[Path]:
    return sorted(
        p
        for p in face_folder.iterdir()
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    )


def main() -> None:
    args = parse_args()
    if not args.database_url and not (args.db_name and args.db_user):
        raise ValueError("Provide --database-url or --db-name and --db-user (and optional --db-password).")

    output_dir = Path(args.output_dir).resolve()
    reset_output(output_dir, overwrite=args.overwrite)

    if args.database_url:
        conn = psycopg2.connect(args.database_url)
    else:
        conn = connect_pg(
            host=args.db_host,
            port=args.db_port,
            dbname=args.db_name,
            user=args.db_user,
            password=args.db_password,
        )
    try:
        image_rows = fetch_training_images(conn, args.class_code, args.include_pending)
        legacy_folders = fetch_legacy_face_folders(conn, args.class_code)
    finally:
        conn.close()

    copied_student_codes: set[str] = set()
    copied_images = 0

    for row in image_rows:
        student_code = row["student_code"]
        image_uri = row["image_path"]
        if not image_uri:
            continue
        dst_folder = output_dir / student_code
        dst_folder.mkdir(parents=True, exist_ok=True)
        suffix = Path(urllib.parse.urlparse(image_uri).path).suffix or ".jpg"
        dst_path = dst_folder / f"img_{copied_images:05d}{suffix}"
        try:
            if add_image_uri(image_uri, dst_path, args.link_mode):
                copied_images += 1
                copied_student_codes.add(student_code)
        except Exception as exc:
            print(f"Skip {student_code}: cannot read {image_uri} -> {exc}")

    for student in legacy_folders:
        student_code = student["student_code"]
        face_folder = Path(student["face_folder"])
        if not face_folder.exists() or student_code in copied_student_codes:
            continue

        dst_folder = output_dir / student_code
        dst_folder.mkdir(parents=True, exist_ok=True)
        for image_path in collect_images(face_folder):
            if add_file(image_path.resolve(), dst_folder / image_path.name, args.link_mode):
                copied_images += 1
                copied_student_codes.add(student_code)

    if not copied_student_codes:
        raise ValueError("No valid student folders copied to output dataset.")

    print(f"Output dir: {output_dir}")
    print(f"Students included: {len(copied_student_codes)}")
    print(f"Images included: {copied_images}")
    print(
        "Next step: `cd modelcore/Model_v2 && python -m face_pipeline arcface-train --training-dir "
        f"{output_dir}`"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
