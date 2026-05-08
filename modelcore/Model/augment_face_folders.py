from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from PIL import Image, ImageEnhance, ImageFilter


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True)
class AugmentConfig:
    target_per_class: int
    image_size: int
    seed: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Augment face images in folder-based classes and write them to a new dataset directory."
    )
    parser.add_argument("--input-dir", type=str, default="Training")
    parser.add_argument("--output-dir", type=str, default="TrainingAugmented")
    parser.add_argument("--target-per-class", type=int, default=30)
    parser.add_argument("--image-size", type=int, default=112)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def discover_class_dirs(input_dir: Path) -> List[Path]:
    class_dirs = sorted(path for path in input_dir.iterdir() if path.is_dir())
    if not class_dirs:
        raise ValueError(f"No class folders found inside {input_dir}")
    return class_dirs


def discover_images(class_dir: Path) -> List[Path]:
    images = sorted(
        path for path in class_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not images:
        raise ValueError(f"No images found inside {class_dir}")
    return images


def reset_output_dir(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"Output directory already exists: {output_dir}. Use --overwrite to recreate it."
            )
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def load_image(image_path: Path, image_size: int) -> Image.Image:
    image = Image.open(image_path).convert("RGB")
    return image.resize((image_size, image_size))


def maybe_flip(image: Image.Image, rng: random.Random) -> Image.Image:
    if rng.random() < 0.5:
        return image.transpose(Image.FLIP_LEFT_RIGHT)
    return image


def maybe_rotate(image: Image.Image, rng: random.Random) -> Image.Image:
    angle = rng.uniform(-15.0, 15.0)
    return image.rotate(angle, resample=Image.BILINEAR)


def maybe_translate(image: Image.Image, rng: random.Random) -> Image.Image:
    width, height = image.size
    shift_x = int(rng.uniform(-0.06, 0.06) * width)
    shift_y = int(rng.uniform(-0.06, 0.06) * height)
    return image.transform(
        image.size,
        Image.AFFINE,
        (1, 0, shift_x, 0, 1, shift_y),
        resample=Image.BILINEAR,
    )


def maybe_zoom(image: Image.Image, rng: random.Random) -> Image.Image:
    width, height = image.size
    zoom = rng.uniform(0.92, 1.08)
    new_width = max(1, int(width * zoom))
    new_height = max(1, int(height * zoom))

    resized = image.resize((new_width, new_height), resample=Image.BILINEAR)
    if zoom >= 1.0:
        left = (new_width - width) // 2
        top = (new_height - height) // 2
        return resized.crop((left, top, left + width, top + height))

    canvas = Image.new("RGB", (width, height), (0, 0, 0))
    left = (width - new_width) // 2
    top = (height - new_height) // 2
    canvas.paste(resized, (left, top))
    return canvas


def maybe_color_jitter(image: Image.Image, rng: random.Random) -> Image.Image:
    brightness = ImageEnhance.Brightness(image).enhance(rng.uniform(0.8, 1.2))
    contrast = ImageEnhance.Contrast(brightness).enhance(rng.uniform(0.8, 1.2))
    color = ImageEnhance.Color(contrast).enhance(rng.uniform(0.85, 1.15))
    return color


def maybe_blur(image: Image.Image, rng: random.Random) -> Image.Image:
    if rng.random() < 0.35:
        return image.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.2, 1.0)))
    return image


def augment_image(image: Image.Image, rng: random.Random) -> Image.Image:
    image = maybe_flip(image, rng)
    image = maybe_rotate(image, rng)
    image = maybe_translate(image, rng)
    image = maybe_zoom(image, rng)
    image = maybe_color_jitter(image, rng)
    image = maybe_blur(image, rng)
    return image


def save_image(image: Image.Image, destination: Path) -> None:
    image.save(destination, format="JPEG", quality=95)


def copy_originals(image_paths: List[Path], output_class_dir: Path, image_size: int) -> int:
    count = 0
    for index, image_path in enumerate(image_paths):
        image = load_image(image_path, image_size)
        destination = output_class_dir / f"orig_{index:04d}.jpg"
        save_image(image, destination)
        count += 1
    return count


def augment_class(
    class_dir: Path,
    output_class_dir: Path,
    config: AugmentConfig,
) -> Dict[str, int]:
    rng = random.Random(config.seed + sum(ord(ch) for ch in class_dir.name))
    image_paths = discover_images(class_dir)

    output_class_dir.mkdir(parents=True, exist_ok=True)
    original_count = copy_originals(image_paths, output_class_dir, config.image_size)
    total_count = original_count
    generated_count = 0

    if total_count >= config.target_per_class:
        return {
            "original_count": original_count,
            "generated_count": generated_count,
            "final_count": total_count,
        }

    base_images = [load_image(image_path, config.image_size) for image_path in image_paths]
    while total_count < config.target_per_class:
        source_image = rng.choice(base_images)
        augmented = augment_image(source_image.copy(), rng)
        destination = output_class_dir / f"aug_{generated_count:04d}.jpg"
        save_image(augmented, destination)
        generated_count += 1
        total_count += 1

    return {
        "original_count": original_count,
        "generated_count": generated_count,
        "final_count": total_count,
    }


def save_report(output_dir: Path, report: Dict[str, Dict[str, int]], args: argparse.Namespace) -> None:
    payload = {
        "input_dir": str(Path(args.input_dir).resolve()),
        "output_dir": str(output_dir.resolve()),
        "target_per_class": args.target_per_class,
        "image_size": args.image_size,
        "seed": args.seed,
        "classes": report,
    }
    (output_dir / "augmentation_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    if args.target_per_class < 1:
        raise ValueError("--target-per-class must be at least 1")
    if args.image_size < 32:
        raise ValueError("--image-size should be at least 32")

    reset_output_dir(output_dir, overwrite=args.overwrite)
    class_dirs = discover_class_dirs(input_dir)
    config = AugmentConfig(
        target_per_class=args.target_per_class,
        image_size=args.image_size,
        seed=args.seed,
    )

    report: Dict[str, Dict[str, int]] = {}
    print(f"Input directory: {input_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Target images per class: {args.target_per_class}")

    for class_dir in class_dirs:
        summary = augment_class(
            class_dir=class_dir,
            output_class_dir=output_dir / class_dir.name,
            config=config,
        )
        report[class_dir.name] = summary
        print(
            f"{class_dir.name}: "
            f"original={summary['original_count']} "
            f"generated={summary['generated_count']} "
            f"final={summary['final_count']}"
        )

    save_report(output_dir, report, args)
    print(f"Saved augmentation report to {output_dir / 'augmentation_report.json'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
