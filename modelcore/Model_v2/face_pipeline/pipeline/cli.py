from __future__ import annotations

import argparse
import sys

from face_pipeline.data.pg_settings import DEFAULT_PG_DBNAME, DEFAULT_PG_USER, default_pg_password


def main() -> None:
    usage = (
        "Cách chạy: cd modelcore/Model_v2 && python -m face_pipeline <lenh> [tham so ...]\n"
        "Lenh: train-full | check-db | detect | track | compare-yolo | augment | arcface-train | "
        "export-embeddings | recognize | build-training | student-db"
    )
    if len(sys.argv) < 2:
        print(usage)
        sys.exit(1)
    if sys.argv[1] in {"-h", "--help"}:
        print(usage)
        sys.exit(0)

    cmd = sys.argv[1]
    tail = sys.argv[2:]

    if cmd in {"help", "commands"}:
        print(
            usage
        )
        sys.exit(0)

    if cmd == "train-full":
        from face_pipeline.pipeline.steps import run_train_full

        p = argparse.ArgumentParser(prog="face_pipeline train-full")
        p.add_argument("--db-host", type=str, default="localhost")
        p.add_argument("--db-port", type=int, default=5432)
        p.add_argument("--db-name", type=str, default=DEFAULT_PG_DBNAME)
        p.add_argument("--db-user", type=str, default=DEFAULT_PG_USER)
        p.add_argument("--db-password", type=str, default=default_pg_password())
        p.add_argument("--class-code", type=str, default=None)
        p.add_argument("--augment-target-per-class", type=int, default=30)
        p.add_argument("--epochs", type=int, default=30)
        p.add_argument("--save-name", type=str, default="arcface_resnet18.pth")
        ns = p.parse_args(tail)
        run_train_full(
            db_host=ns.db_host,
            db_port=ns.db_port,
            db_name=ns.db_name,
            db_user=ns.db_user,
            db_password=ns.db_password,
            class_code=ns.class_code,
            augment_target_per_class=ns.augment_target_per_class,
            arcface_epochs=ns.epochs,
            arcface_save_name=ns.save_name,
        )
        return

    if cmd == "check-db":
        sys.argv = ["pg_check"] + tail
        from face_pipeline.data.pg_check import main as check_main

        check_main()
        return

    if cmd == "student-db":
        sys.argv = ["student_db_pg"] + tail
        from face_pipeline.data.student_db_pg import main as db_main

        db_main()
        return

    dispatch = {
        "detect": "face_pipeline.detect_tracking.yolo_webcam",
        "track": "face_pipeline.detect_tracking.yolo_track",
        "compare-yolo": "face_pipeline.detect_tracking.yolo_compare",
        "augment": "face_pipeline.recognition.augment_face_folders",
        "arcface-train": "face_pipeline.recognition.arcface_train",
        "export-embeddings": "face_pipeline.recognition.export_embeddings",
        "recognize": "face_pipeline.recognition.recognize_face",
        "build-training": "face_pipeline.data.build_training_from_db",
    }

    if cmd not in dispatch:
        print(f"Khong biet lenh: {cmd}", file=sys.stderr)
        sys.exit(2)

    sys.argv = [dispatch[cmd]] + tail
    mod = __import__(dispatch[cmd], fromlist=["main"])
    mod.main()


if __name__ == "__main__":
    main()
