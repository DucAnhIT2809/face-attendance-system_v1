from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True)
class Sample:
    image_path: Path
    class_index: int


class FaceFolderDataset(Dataset):
    def __init__(
        self,
        samples: Sequence[Sample],
        transform: transforms.Compose,
        face_detector: "FaceDetector | None" = None,
    ) -> None:
        self.samples = list(samples)
        self.transform = transform
        self.face_detector = face_detector

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> Tuple[torch.Tensor, int]:
        sample = self.samples[index]
        image = Image.open(sample.image_path).convert("RGB")
        if self.face_detector is not None:
            image = self.face_detector.crop_largest_face(image)
        image = self.transform(image)
        return image, sample.class_index


class FaceDetector:
    def __init__(self, model_path: Path, conf: float = 0.25) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("Khong tim thay ultralytics. Hay cai `ultralytics`.") from exc

        self.model = YOLO(str(model_path))
        self.conf = conf

    def detect_face_boxes(self, image: Image.Image) -> list[tuple[int, int, int, int]]:
        result = self.model(image, conf=self.conf, verbose=False)[0]
        boxes = result.boxes
        if boxes is None or boxes.xyxy is None or len(boxes.xyxy) == 0:
            return []

        width, height = image.size
        detected_boxes: list[tuple[float, tuple[int, int, int, int]]] = []
        for box in boxes.xyxy.tolist():
            x1, y1, x2, y2 = box[:4]
            x1 = max(0, min(int(x1), width - 1))
            y1 = max(0, min(int(y1), height - 1))
            x2 = max(0, min(int(x2), width))
            y2 = max(0, min(int(y2), height))
            if x2 <= x1 or y2 <= y1:
                continue
            area = float((x2 - x1) * (y2 - y1))
            detected_boxes.append((area, (x1, y1, x2, y2)))

        detected_boxes.sort(key=lambda item: item[0], reverse=True)
        return [box for _, box in detected_boxes]

    def detect_largest_face_box(self, image: Image.Image) -> tuple[int, int, int, int] | None:
        boxes = self.detect_face_boxes(image)
        if not boxes:
            return None

        return boxes[0]

    def crop_largest_face(self, image: Image.Image) -> Image.Image:
        best_box = self.detect_largest_face_box(image)
        if best_box is None:
            return image
        return image.crop(best_box)


class ArcFaceBackbone(nn.Module):
    def __init__(self, embedding_size: int = 512, pretrained_backbone: bool = False) -> None:
        super().__init__()

        weights = models.ResNet18_Weights.DEFAULT if pretrained_backbone else None
        backbone = models.resnet18(weights=weights)
        feature_dim = backbone.fc.in_features
        backbone.fc = nn.Identity()

        self.backbone = backbone
        self.embedding = nn.Linear(feature_dim, embedding_size)
        self.bn = nn.BatchNorm1d(embedding_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.backbone(x)
        x = self.embedding(x)
        x = self.bn(x)
        return F.normalize(x, p=2, dim=1)


class ArcMarginProduct(nn.Module):
    def __init__(self, in_features: int, out_features: int, scale: float = 64.0, margin: float = 0.5) -> None:
        super().__init__()
        self.weight = nn.Parameter(torch.empty(out_features, in_features))
        nn.init.xavier_uniform_(self.weight)

        self.in_features = in_features
        self.out_features = out_features
        self.scale = scale
        self.margin = margin
        self.cos_m = math.cos(margin)
        self.sin_m = math.sin(margin)
        self.th = math.cos(math.pi - margin)
        self.mm = math.sin(math.pi - margin) * margin

    def forward(self, embeddings: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        cosine = F.linear(F.normalize(embeddings), F.normalize(self.weight))
        sine = torch.sqrt(torch.clamp(1.0 - cosine.pow(2), min=1e-7))
        phi = cosine * self.cos_m - sine * self.sin_m
        phi = torch.where(cosine > self.th, phi, cosine - self.mm)

        one_hot = torch.zeros_like(cosine)
        one_hot.scatter_(1, labels.view(-1, 1), 1.0)
        logits = one_hot * phi + (1.0 - one_hot) * cosine
        return logits * self.scale


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train an ArcFace model from folder-based face images.")
    parser.add_argument("--training-dir", type=str, default="Training")
    parser.add_argument("--output-dir", type=str, default="Model/arcface_runs")
    parser.add_argument("--save-name", type=str, default="arcface_resnet18.pth")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--image-size", type=int, default=112)
    parser.add_argument("--embedding-size", type=int, default=512)
    parser.add_argument("--margin", type=float, default=0.5)
    parser.add_argument("--scale", type=float, default=64.0)
    parser.add_argument("--val-split", type=float, default=0.2)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
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
    parser.add_argument("--pretrained-backbone", action="store_true")
    return parser.parse_args()


def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def resolve_device(device_arg: str) -> torch.device:
    if device_arg == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(device_arg)


def resolve_model_path(weight_arg: str) -> Path:
    candidate = Path(weight_arg)
    if candidate.exists():
        return candidate.resolve()

    script_dir = Path(__file__).resolve().parent
    fallback_candidates = [
        script_dir / weight_arg,
        script_dir.parent / weight_arg,
    ]
    for fallback in fallback_candidates:
        if fallback.exists():
            return fallback.resolve()

    raise FileNotFoundError(f"Weight file not found: {weight_arg}")


def discover_class_names(training_dir: Path) -> List[str]:
    class_names = sorted(item.name for item in training_dir.iterdir() if item.is_dir())
    if not class_names:
        raise ValueError(f"No class folders found inside {training_dir}")
    return class_names


def collect_samples(training_dir: Path, class_names: Sequence[str]) -> List[Sample]:
    class_to_index = {name: index for index, name in enumerate(class_names)}
    samples: List[Sample] = []

    for class_name in class_names:
        class_dir = training_dir / class_name
        for image_path in sorted(class_dir.iterdir()):
            if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS:
                samples.append(Sample(image_path=image_path, class_index=class_to_index[class_name]))

    if not samples:
        raise ValueError(f"No image files found inside {training_dir}")
    return samples


def split_samples_by_class(
    samples: Sequence[Sample],
    num_classes: int,
    val_split: float,
    seed: int,
) -> Tuple[List[Sample], List[Sample]]:
    if not 0.0 <= val_split < 1.0:
        raise ValueError("val_split must be in range [0.0, 1.0)")

    grouped: Dict[int, List[Sample]] = {class_index: [] for class_index in range(num_classes)}
    for sample in samples:
        grouped[sample.class_index].append(sample)

    rng = random.Random(seed)
    train_samples: List[Sample] = []
    val_samples: List[Sample] = []

    for class_index in range(num_classes):
        class_samples = grouped[class_index]
        rng.shuffle(class_samples)

        if len(class_samples) < 2 or val_split == 0.0:
            train_samples.extend(class_samples)
            continue

        val_count = max(1, int(round(len(class_samples) * val_split)))
        val_count = min(val_count, len(class_samples) - 1)

        val_samples.extend(class_samples[:val_count])
        train_samples.extend(class_samples[val_count:])

    return train_samples, val_samples


def build_transform(image_size: int, train: bool) -> transforms.Compose:
    ops: List[transforms.Compose] = [
        transforms.Resize((image_size, image_size)),
    ]
    if train:
        ops.extend(
            [
                transforms.RandomHorizontalFlip(p=0.5),
                transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
            ]
        )
    ops.extend(
        [
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]),
        ]
    )
    return transforms.Compose(ops)


def compute_accuracy(logits: torch.Tensor, labels: torch.Tensor) -> float:
    predictions = logits.argmax(dim=1)
    correct = (predictions == labels).sum().item()
    return correct / max(labels.size(0), 1)


def run_epoch(
    backbone: nn.Module,
    classifier: nn.Module,
    dataloader: DataLoader,
    optimizer: torch.optim.Optimizer | None,
    device: torch.device,
) -> Tuple[float, float]:
    training = optimizer is not None
    backbone.train(training)
    classifier.train(training)

    criterion = nn.CrossEntropyLoss()
    running_loss = 0.0
    running_accuracy = 0.0

    for images, labels in dataloader:
        images = images.to(device)
        labels = labels.to(device)

        if training:
            optimizer.zero_grad()

        with torch.set_grad_enabled(training):
            embeddings = backbone(images)
            logits = classifier(embeddings, labels)
            loss = criterion(logits, labels)

            if training:
                loss.backward()
                optimizer.step()

        running_loss += loss.item()
        running_accuracy += compute_accuracy(logits.detach(), labels)

    mean_loss = running_loss / max(len(dataloader), 1)
    mean_accuracy = running_accuracy / max(len(dataloader), 1)
    return mean_loss, mean_accuracy


def save_checkpoint(
    save_path: Path,
    backbone: ArcFaceBackbone,
    classifier: ArcMarginProduct,
    class_names: Sequence[str],
    args: argparse.Namespace,
    epoch: int,
    best_val_loss: float,
) -> None:
    checkpoint = {
        "epoch": epoch,
        "class_names": list(class_names),
        "backbone_state_dict": backbone.state_dict(),
        "classifier_state_dict": classifier.state_dict(),
        "embedding_size": args.embedding_size,
        "image_size": args.image_size,
        "margin": args.margin,
        "scale": args.scale,
        "backbone_name": "resnet18",
        "best_val_loss": best_val_loss,
    }
    torch.save(checkpoint, save_path)


def save_metadata(save_dir: Path, class_names: Sequence[str], args: argparse.Namespace) -> None:
    metadata = {
        "class_names": list(class_names),
        "training_dir": str(Path(args.training_dir).resolve()),
        "image_size": args.image_size,
        "embedding_size": args.embedding_size,
        "margin": args.margin,
        "scale": args.scale,
    }
    (save_dir / "class_names.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    set_seed(args.seed)

    training_dir = Path(args.training_dir).resolve()
    if not training_dir.exists():
        raise FileNotFoundError(f"Training directory not found: {training_dir}")

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    face_detector = None
    if args.detect_face:
        face_detector_weight = resolve_model_path(args.face_detector_weight)
        face_detector = FaceDetector(
            model_path=face_detector_weight,
            conf=args.face_detector_conf,
        )

    class_names = discover_class_names(training_dir)
    all_samples = collect_samples(training_dir, class_names)
    train_samples, val_samples = split_samples_by_class(
        samples=all_samples,
        num_classes=len(class_names),
        val_split=args.val_split,
        seed=args.seed,
    )

    train_dataset = FaceFolderDataset(
        train_samples,
        build_transform(args.image_size, train=True),
        face_detector=face_detector,
    )
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
    )

    val_loader = None
    if val_samples:
        val_dataset = FaceFolderDataset(
            val_samples,
            build_transform(args.image_size, train=False),
            face_detector=face_detector,
        )
        val_loader = DataLoader(
            val_dataset,
            batch_size=args.batch_size,
            shuffle=False,
            num_workers=args.num_workers,
        )

    device = resolve_device(args.device)
    backbone = ArcFaceBackbone(
        embedding_size=args.embedding_size,
        pretrained_backbone=args.pretrained_backbone,
    ).to(device)
    classifier = ArcMarginProduct(
        in_features=args.embedding_size,
        out_features=len(class_names),
        scale=args.scale,
        margin=args.margin,
    ).to(device)

    optimizer = torch.optim.AdamW(
        list(backbone.parameters()) + list(classifier.parameters()),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(args.epochs, 1))

    save_path = output_dir / args.save_name
    best_val_loss = float("inf")

    print(f"Device: {device}")
    print(f"Training directory: {training_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Classes ({len(class_names)}): {class_names}")
    print(f"Train samples: {len(train_samples)}")
    print(f"Val samples: {len(val_samples)}")

    save_metadata(output_dir, class_names, args)

    for epoch in range(1, args.epochs + 1):
        train_loss, train_acc = run_epoch(backbone, classifier, train_loader, optimizer, device)

        if val_loader is None:
            scheduler.step()
            print(
                f"Epoch {epoch}/{args.epochs} "
                f"- train_loss: {train_loss:.4f} "
                f"- train_acc: {train_acc:.4f}"
            )
            save_checkpoint(save_path, backbone, classifier, class_names, args, epoch, best_val_loss)
            continue

        val_loss, val_acc = run_epoch(backbone, classifier, val_loader, optimizer=None, device=device)
        scheduler.step()

        print(
            f"Epoch {epoch}/{args.epochs} "
            f"- train_loss: {train_loss:.4f} "
            f"- train_acc: {train_acc:.4f} "
            f"- val_loss: {val_loss:.4f} "
            f"- val_acc: {val_acc:.4f}"
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            save_checkpoint(save_path, backbone, classifier, class_names, args, epoch, best_val_loss)
            print(f"Saved best checkpoint to {save_path}")

    print(f"Finished. Latest/best checkpoint: {save_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
