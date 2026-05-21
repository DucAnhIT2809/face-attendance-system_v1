from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List, Tuple


DEFAULT_WEIGHT = "yolov8s-face.pt"
DEFAULT_CAMERA_INDEX = 0
DEFAULT_DETECT_INTERVAL = 2.0
DEFAULT_CONFIDENCE = 0.5
DEFAULT_FACE_SIZE = 112
DEFAULT_OUTPUT_DIR = "Datadetect"
WINDOW_NAME = "YOLOv8-Face - Camera"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect faces from webcam using a YOLOv8-face weight and save crops to Datadetect."
    )
    parser.add_argument("--weight", type=str, default=DEFAULT_WEIGHT, help="Path to YOLOv8-face weight file.")
    parser.add_argument("--camera-index", type=int, default=DEFAULT_CAMERA_INDEX, help="Webcam index.")
    parser.add_argument(
        "--detect-interval",
        type=float,
        default=DEFAULT_DETECT_INTERVAL,
        help="Run detection once every N seconds.",
    )
    parser.add_argument("--conf", type=float, default=DEFAULT_CONFIDENCE, help="Confidence threshold.")
    parser.add_argument(
        "--face-size",
        type=int,
        default=DEFAULT_FACE_SIZE,
        help="Resize saved face crops to a square of this size.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory used to save cropped faces.",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Show detections but do not save cropped faces.",
    )
    return parser.parse_args()


def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def resolve_model_path(weight_arg: str) -> Path:
    from face_pipeline.paths import resolve_weight_file

    return resolve_weight_file(weight_arg)


def get_next_face_id(output_dir: Path) -> int:
    max_face_id = -1
    for image_path in output_dir.glob("cam_face_*.jpg"):
        suffix = image_path.stem.removeprefix("cam_face_")
        if suffix.isdigit():
            max_face_id = max(max_face_id, int(suffix))
    return max_face_id + 1


def clamp_box(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    frame_width: int,
    frame_height: int,
) -> Tuple[int, int, int, int]:
    x1 = max(0, min(x1, frame_width - 1))
    y1 = max(0, min(y1, frame_height - 1))
    x2 = max(0, min(x2, frame_width))
    y2 = max(0, min(y2, frame_height))
    return x1, y1, x2, y2


def extract_boxes(result) -> List[Tuple[int, int, int, int]]:
    boxes = result.boxes
    if boxes is None:
        return []
    return [tuple(map(int, box[:4])) for box in boxes.xyxy.tolist()]


def draw_boxes(frame, boxes: List[Tuple[int, int, int, int]], detect_interval: float) -> None:
    for x1, y1, x2, y2 in boxes:
        frame_color = (0, 255, 0)
        cv2.rectangle(frame, (x1, y1), (x2, y2), frame_color, 2)
    cv2.putText(
        frame,
        f"Detect every {detect_interval:.1f}s | Press q to quit",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )


def save_faces(
    frame,
    boxes: List[Tuple[int, int, int, int]],
    output_dir: Path,
    face_size: int,
    start_face_id: int,
) -> int:
    frame_height, frame_width = frame.shape[:2]
    face_id = start_face_id

    for x1, y1, x2, y2 in boxes:
        x1, y1, x2, y2 = clamp_box(x1, y1, x2, y2, frame_width, frame_height)
        if x2 <= x1 or y2 <= y1:
            continue

        face = frame[y1:y2, x1:x2]
        if face.size == 0:
            continue

        face = cv2.resize(face, (face_size, face_size))
        save_path = output_dir / f"cam_face_{face_id}.jpg"
        cv2.imwrite(str(save_path), face)
        print(f"Saved: {save_path}")
        face_id += 1

    return face_id


def run_webcam(
    model_path: Path,
    camera_index: int,
    detect_interval: float,
    conf: float,
    output_dir: Path,
    face_size: int,
    save_enabled: bool,
) -> None:
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("Khong tim thay ultralytics. Hay cai `ultralytics`.") from exc
    model = YOLO(str(model_path))
    cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        raise RuntimeError(f"Cannot open webcam index {camera_index}")

    face_id = get_next_face_id(output_dir) if save_enabled else 0
    last_detect_ts = 0.0
    last_boxes: List[Tuple[int, int, int, int]] = []

    print(f"Weight: {model_path.resolve()}")
    print(f"Camera index: {camera_index}")
    print(f"Detect interval: {detect_interval}s")
    print(f"Confidence threshold: {conf}")
    print(f"Save face crops: {save_enabled}")
    if save_enabled:
        print(f"Output dir: {output_dir.resolve()}")
        print(f"Start face_id: {face_id}")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Khong doc duoc frame tu camera!")
                break

            now = time.time()
            if now - last_detect_ts >= detect_interval:
                result = model(frame, conf=conf, verbose=False)[0]
                last_boxes = extract_boxes(result)
                last_detect_ts = now

                if save_enabled and last_boxes:
                    face_id = save_faces(frame, last_boxes, output_dir, face_size, face_id)

            draw_boxes(frame, last_boxes, detect_interval)
            cv2.imshow(WINDOW_NAME, frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


def main() -> None:
    args = parse_args()

    try:
        global cv2
        import cv2
    except ImportError as exc:
        raise RuntimeError("Khong tim thay cv2. Hay cai `opencv-python`.") from exc

    model_path = resolve_model_path(args.weight)

    output_dir = Path(args.output_dir)
    save_enabled = not args.no_save
    if save_enabled:
        ensure_output_dir(output_dir)

    run_webcam(
        model_path=model_path,
        camera_index=args.camera_index,
        detect_interval=args.detect_interval,
        conf=args.conf,
        output_dir=output_dir,
        face_size=args.face_size,
        save_enabled=save_enabled,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
