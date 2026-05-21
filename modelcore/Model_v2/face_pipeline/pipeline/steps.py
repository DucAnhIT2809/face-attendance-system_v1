from __future__ import annotations

import sys
from typing import Optional

from face_pipeline.paths import MODEL_DIR, REPO_ROOT


def _run_with_argv(main_fn, argv: list[str]) -> None:
    old = sys.argv[:]
    sys.argv = [old[0]] + argv
    try:
        main_fn()
    finally:
        sys.argv = old


def run_train_full(
    *,
    db_host: str,
    db_port: int,
    db_name: str,
    db_user: str,
    db_password: str,
    class_code: Optional[str] = None,
    augment_target_per_class: int = 30,
    arcface_epochs: int = 30,
    arcface_save_name: str = "arcface_resnet18.pth",
) -> None:
    """
    Pipeline: PostgreSQL (active students) -> TrainingSelected -> augment -> ArcFace train -> export face_db.pt
    """
    training_selected = (REPO_ROOT / "TrainingSelected").resolve()
    augmented = (REPO_ROOT / "TrainingAugmented").resolve()
    runs = (MODEL_DIR / "arcface_runs").resolve()
    checkpoint = (runs / arcface_save_name).resolve()
    face_db = (runs / "face_db.pt").resolve()

    from face_pipeline.data.build_training_from_db import main as build_main

    build_argv = [
        "--db-host",
        db_host,
        "--db-port",
        str(db_port),
        "--db-name",
        db_name,
        "--db-user",
        db_user,
        "--db-password",
        db_password,
        "--output-dir",
        str(training_selected),
        "--overwrite",
    ]
    if class_code:
        build_argv += ["--class-code", class_code]
    print("[pipeline] 1/4 Build TrainingSelected from DB")
    _run_with_argv(build_main, build_argv)

    from face_pipeline.recognition.augment_face_folders import main as aug_main

    print("[pipeline] 2/4 Augment face folders")
    _run_with_argv(
        aug_main,
        [
            "--input-dir",
            str(training_selected),
            "--output-dir",
            str(augmented),
            "--target-per-class",
            str(augment_target_per_class),
            "--overwrite",
        ],
    )

    from face_pipeline.recognition.arcface_train import main as train_main

    print("[pipeline] 3/4 Train ArcFace")
    _run_with_argv(
        train_main,
        [
            "--training-dir",
            str(augmented),
            "--output-dir",
            str(runs),
            "--epochs",
            str(arcface_epochs),
            "--save-name",
            arcface_save_name,
        ],
    )

    from face_pipeline.recognition.export_embeddings import main as export_main

    print("[pipeline] 4/4 Export embedding DB")
    _run_with_argv(
        export_main,
        [
            "--checkpoint",
            str(checkpoint),
            "--gallery-dir",
            str(augmented),
            "--output-db",
            str(face_db),
        ],
    )
    print("[pipeline] Xong.")
    print(f"  Checkpoint: {checkpoint}")
    print(f"  face_db.pt: {face_db}")
