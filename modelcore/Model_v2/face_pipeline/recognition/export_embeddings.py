from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import torch
from PIL import Image

from face_pipeline.paths import MODEL_DIR, REPO_ROOT
from face_pipeline.recognition.arcface_train import (
    ArcFaceBackbone,
    FaceDetector,
    IMAGE_EXTENSIONS,
    build_transform,
    resolve_device,
    resolve_model_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export ArcFace embeddings database per identity.")
    parser.add_argument("--checkpoint", type=str, required=True, help="Path to trained ArcFace .pth file.")
    parser.add_argument(
        "--gallery-dir",
        type=str,
        default=str(REPO_ROOT / "TrainingAugmented"),
        help="Folder with structure: gallery_dir/<person_name>/*.jpg",
    )
    parser.add_argument(
        "--output-db",
        type=str,
        default=None,
        help="Output embedding database file (.pt). If omitted, use --class-code path or default face_db.pt.",
    )
    parser.add_argument("--class-code", type=str, default=None, help="Export to <class-output-root>/<class_code>/face_db.pt.")
    parser.add_argument(
        "--class-output-root",
        type=str,
        default=str(MODEL_DIR / "arcface_runs" / "classes"),
        help="Root for class-specific exports when --class-code is set.",
    )
    parser.add_argument("--device", type=str, default="auto")
    parser.add_argument(
        "--detect-face",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Detect and crop the largest face before ArcFace input (default: True).",
    )
    parser.add_argument(
        "--face-detector-weight",
        type=str,
        default="yolov8s-face.pt",
        help="Path to YOLO face detector weight used for pre-cropping.",
    )
    parser.add_argument(
        "--face-detector-conf",
        type=float,
        default=0.25,
        help="Confidence threshold for face detector pre-cropping.",
    )
    return parser.parse_args()


def list_image_paths(person_dir: Path) -> List[Path]:
    return sorted(
        path
        for path in person_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def load_backbone(checkpoint_path: Path, device: torch.device) -> tuple[ArcFaceBackbone, int]:
    checkpoint = torch.load(checkpoint_path, map_location=device)
    embedding_size = int(checkpoint["embedding_size"])
    image_size = int(checkpoint["image_size"])

    backbone = ArcFaceBackbone(embedding_size=embedding_size, pretrained_backbone=False).to(device)
    backbone.load_state_dict(checkpoint["backbone_state_dict"], strict=True)
    backbone.eval()
    return backbone, image_size


@torch.no_grad()
def encode_image(
    backbone: ArcFaceBackbone,
    image_path: Path,
    image_size: int,
    device: torch.device,
    face_detector: FaceDetector | None,
) -> torch.Tensor:
    transform = build_transform(image_size=image_size, train=False)
    image = Image.open(image_path).convert("RGB")
    if face_detector is not None:
        image = face_detector.crop_largest_face(image)
    tensor = transform(image).unsqueeze(0).to(device)
    embedding = backbone(tensor)[0].detach().cpu()
    return embedding


def main() -> None:
    args = parse_args()
    device = resolve_device(args.device)

    checkpoint_path = Path(args.checkpoint).resolve()
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

    gallery_dir = Path(args.gallery_dir).resolve()
    if not gallery_dir.exists():
        raise FileNotFoundError(f"Gallery dir not found: {gallery_dir}")

    face_detector = None
    if args.detect_face:
        face_detector_weight = resolve_model_path(args.face_detector_weight)
        face_detector = FaceDetector(
            model_path=face_detector_weight,
            conf=args.face_detector_conf,
        )

    backbone, image_size = load_backbone(checkpoint_path, device)
    per_person_embeddings: Dict[str, List[torch.Tensor]] = defaultdict(list)

    person_dirs = sorted(path for path in gallery_dir.iterdir() if path.is_dir())
    if not person_dirs:
        raise ValueError(f"No person subfolders found in: {gallery_dir}")

    total_images = 0
    for person_dir in person_dirs:
        image_paths = list_image_paths(person_dir)
        if not image_paths:
            continue

        for image_path in image_paths:
            emb = encode_image(backbone, image_path, image_size, device, face_detector)
            per_person_embeddings[person_dir.name].append(emb)
            total_images += 1

    if not per_person_embeddings:
        raise ValueError(f"No valid images found in: {gallery_dir}")

    mean_embeddings: Dict[str, torch.Tensor] = {}
    samples_per_person: Dict[str, int] = {}
    for person_name, emb_list in per_person_embeddings.items():
        stacked = torch.stack(emb_list, dim=0)
        mean_emb = torch.nn.functional.normalize(stacked.mean(dim=0), p=2, dim=0)
        mean_embeddings[person_name] = mean_emb
        samples_per_person[person_name] = stacked.shape[0]

    if args.output_db:
        output_path = Path(args.output_db).resolve()
    elif args.class_code:
        output_path = (Path(args.class_output_root) / args.class_code / "face_db.pt").resolve()
    else:
        output_path = (MODEL_DIR / "arcface_runs" / "face_db.pt").resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "class_code": args.class_code,
            "checkpoint_path": str(checkpoint_path),
            "gallery_dir": str(gallery_dir),
            "embedding_size": next(iter(mean_embeddings.values())).numel(),
            "image_size": image_size,
            "person_embeddings": mean_embeddings,
            "samples_per_person": samples_per_person,
        },
        output_path,
    )

    print(f"Device: {device}")
    print(f"Checkpoint: {checkpoint_path}")
    print(f"Gallery dir: {gallery_dir}")
    print(f"Persons: {len(mean_embeddings)}")
    print(f"Total images encoded: {total_images}")
    print(f"Saved embedding DB: {output_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
