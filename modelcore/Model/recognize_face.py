from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Tuple

import torch
from PIL import Image

from arcface_train import ArcFaceBackbone, FaceDetector, resolve_device, resolve_model_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recognize a face image using ArcFace embedding database.")
    parser.add_argument("--checkpoint", type=str, required=True, help="Path to trained ArcFace .pth file.")
    parser.add_argument("--embedding-db", type=str, required=True, help="Path to face_db.pt.")
    parser.add_argument("--image", type=str, required=True, help="Path to input face image.")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.4,
        help="Cosine similarity threshold for known identity.",
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
        default="yolov8n-face.pt",
        help="Path to YOLO face detector weight used for pre-cropping.",
    )
    parser.add_argument(
        "--face-detector-conf",
        type=float,
        default=0.25,
        help="Confidence threshold for face detector pre-cropping.",
    )
    return parser.parse_args()


def load_backbone(checkpoint_path: Path, device: torch.device) -> tuple[ArcFaceBackbone, int]:
    checkpoint = torch.load(checkpoint_path, map_location=device)
    embedding_size = int(checkpoint["embedding_size"])
    image_size = int(checkpoint["image_size"])

    backbone = ArcFaceBackbone(embedding_size=embedding_size, pretrained_backbone=False).to(device)
    backbone.load_state_dict(checkpoint["backbone_state_dict"], strict=True)
    backbone.eval()
    return backbone, image_size


def load_embedding_db(db_path: Path) -> Dict[str, torch.Tensor]:
    db = torch.load(db_path, map_location="cpu")
    person_embeddings = db.get("person_embeddings")
    if not isinstance(person_embeddings, dict) or not person_embeddings:
        raise ValueError(f"Invalid embedding DB: {db_path}")

    normalized: Dict[str, torch.Tensor] = {}
    for name, emb in person_embeddings.items():
        tensor = emb.detach().cpu().float()
        normalized[name] = torch.nn.functional.normalize(tensor, p=2, dim=0)
    return normalized


@torch.no_grad()
def encode_image(
    backbone: ArcFaceBackbone,
    image_path: Path,
    image_size: int,
    device: torch.device,
    face_detector: FaceDetector | None,
) -> tuple[torch.Tensor, tuple[int, int, int, int] | None, tuple[int, int]]:
    from arcface_train import build_transform

    transform = build_transform(image_size=image_size, train=False)
    image = Image.open(image_path).convert("RGB")
    source_size = image.size
    face_box = None
    if face_detector is not None:
        face_box = face_detector.detect_largest_face_box(image)
        if face_box is not None:
            image = image.crop(face_box)
    tensor = transform(image).unsqueeze(0).to(device)
    embedding = backbone(tensor)[0].detach().cpu()
    return torch.nn.functional.normalize(embedding, p=2, dim=0), face_box, source_size


def predict_identity(
    query_embedding: torch.Tensor,
    person_embeddings: Dict[str, torch.Tensor],
    threshold: float,
) -> Tuple[str, float]:
    best_name = "unknown"
    best_score = -1.0

    for person_name, ref_embedding in person_embeddings.items():
        score = torch.dot(query_embedding, ref_embedding).item()
        if score > best_score:
            best_score = score
            best_name = person_name

    if best_score < threshold:
        return "unknown", best_score
    return best_name, best_score


def main() -> None:
    args = parse_args()
    device = resolve_device(args.device)

    checkpoint_path = Path(args.checkpoint).resolve()
    db_path = Path(args.embedding_db).resolve()
    image_path = Path(args.image).resolve()

    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
    if not db_path.exists():
        raise FileNotFoundError(f"Embedding DB not found: {db_path}")
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    face_detector = None
    if args.detect_face:
        face_detector_weight = resolve_model_path(args.face_detector_weight)
        face_detector = FaceDetector(
            model_path=face_detector_weight,
            conf=args.face_detector_conf,
        )

    backbone, image_size = load_backbone(checkpoint_path, device)
    person_embeddings = load_embedding_db(db_path)
    query_embedding, face_box, source_size = encode_image(backbone, image_path, image_size, device, face_detector)
    name, score = predict_identity(query_embedding, person_embeddings, args.threshold)

    print(f"Image: {image_path}")
    print(f"Image size: {source_size[0]}x{source_size[1]}")
    if face_box is not None:
        print(f"Face box: {face_box[0]},{face_box[1]},{face_box[2]},{face_box[3]}")
    else:
        print("Face box: none")
    print(f"Prediction: {name}")
    print(f"Cosine score: {score:.4f}")
    print(f"Threshold: {args.threshold:.4f}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
