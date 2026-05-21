from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from face_pipeline.paths import (
    detect_weight_search_dirs,
    is_plausible_weight_pt,
    resolve_weight_file,
)


WINDOW_NAME = "YOLOv8n / YOLOv8s / YOLOv9 — so sánh"
DEFAULT_CAMERA_INDEX = 0
DEFAULT_CONFIDENCE = 0.5
DEFAULT_FACE_SIZE = 112
DEFAULT_OUTPUT_DIR = "Datadetect"
DEFAULT_DETECT_INTERVAL = 2.0
DEFAULT_EVAL_SECONDS = 12.0

# Thứ tự dict = thứ tự --run-all: v8 nano → v8 small → v9
WEIGHT_CANDIDATES: Dict[str, Sequence[str]] = {
    "yolov8n-face": ("yolov8n-face.pt", "yolo8n-face.pt", "yolo8n_face.pt"),
    "yolov8s-face": (
        "yolov8s-face.pt",
        "yolov8s-face-lindevs.pt",
        "yolo8s-face.pt",
        "yolo8s_face.pt",
    ),
    "yolov9-c": ("yolov9-c.pt", "yolov9c.pt", "yolov9-c-face.pt", "yolov9c-face.pt"),
}


@dataclass
class SessionMetrics:
    preset: str
    weight_path: str
    wall_seconds: float
    frames_read: int
    detect_runs: int
    inference_ms: List[float] = field(default_factory=list)
    face_counts_per_detect: List[int] = field(default_factory=list)
    loop_fps_samples: List[float] = field(default_factory=list)
    saved_crops: int = 0

    def summary(self) -> Dict[str, Any]:
        inf = self.inference_ms
        fc = self.face_counts_per_detect
        fps_s = self.loop_fps_samples
        return {
            "preset": self.preset,
            "weight_path": self.weight_path,
            "wall_seconds": round(self.wall_seconds, 2),
            "frames_read": self.frames_read,
            "detect_runs": self.detect_runs,
            "avg_inference_ms": round(statistics.mean(inf), 2) if inf else None,
            "median_inference_ms": round(statistics.median(inf), 2) if inf else None,
            "p95_inference_ms": round(_percentile(inf, 95), 2) if len(inf) >= 2 else (round(inf[0], 2) if inf else None),
            "avg_loop_fps": round(statistics.mean(fps_s), 2) if fps_s else None,
            "median_loop_fps": round(statistics.median(fps_s), 2) if fps_s else None,
            "avg_faces_when_detect": round(statistics.mean(fc), 2) if fc else 0.0,
            "max_faces_in_frame": max(fc) if fc else 0,
            "saved_crops": self.saved_crops,
        }


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return float(s[f])
    return float(s[f] + (s[c] - s[f]) * (k - f))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="So sánh webcam: YOLOv8n-face, YOLOv8s-face, YOLOv9-c (FPS, latency, số mặt)."
    )
    parser.add_argument(
        "--model",
        choices=sorted(WEIGHT_CANDIDATES.keys()),
        default="yolov8s-face",
        help="Preset: yolov8n-face | yolov8s-face | yolov9-c (file .pt trong Model_v2/detect_tracking hoặc Model_v2/).",
    )
    parser.add_argument(
        "--weight",
        type=str,
        default=None,
        help="Ghi đè đường dẫn .pt (tuyệt đối hoặc tên file).",
    )
    parser.add_argument(
        "--run-all",
        action="store_true",
        help="Chạy lần lượt yolov8n-face → yolov8s-face → yolov9-c, mỗi mô hình một phiên đánh giá.",
    )
    parser.add_argument(
        "--eval-seconds",
        type=float,
        default=DEFAULT_EVAL_SECONDS,
        help="Với --run-all: số giây webcam cho mỗi mô hình trước khi chuyển sang mô hình kế (vẫn có thể bấm q để thoát sớm).",
    )
    parser.add_argument("--camera-index", type=int, default=DEFAULT_CAMERA_INDEX)
    parser.add_argument("--conf", type=float, default=DEFAULT_CONFIDENCE)
    parser.add_argument("--detect-interval", type=float, default=DEFAULT_DETECT_INTERVAL)
    parser.add_argument("--face-size", type=int, default=DEFAULT_FACE_SIZE)
    parser.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument(
        "--report-json",
        type=str,
        default=None,
        help="Ghi file JSON báo cáo (đặc biệt hữu ích khi --run-all).",
    )
    return parser.parse_args()


def resolve_weight_for_preset(preset: str, weight_override: Optional[str]) -> Path:
    if weight_override:
        return resolve_weight_file(weight_override)

    for name in WEIGHT_CANDIDATES[preset]:
        for base in detect_weight_search_dirs():
            candidate = base / name
            if is_plausible_weight_pt(candidate):
                return candidate.resolve()

    tried = ", ".join(WEIGHT_CANDIDATES[preset])
    raise FileNotFoundError(
        f"Không tìm thấy weight cho preset '{preset}'. Đã thử tên: {tried} "
        f"trong các thư mục: {', '.join(str(b) for b in detect_weight_search_dirs())}"
    )


def resolve_model_path(weight_arg: str) -> Path:
    return resolve_weight_file(weight_arg)


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
    if boxes is None or boxes.xyxy is None:
        return []
    return [tuple(map(int, row[:4])) for row in boxes.xyxy.tolist()]


def draw_boxes(
    frame,
    boxes: List[Tuple[int, int, int, int]],
    preset: str,
    fps: float,
    elapsed_session: float,
    eval_limit: Optional[float],
) -> None:
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
    limit_txt = f" | còn {max(0.0, eval_limit - elapsed_session):.0f}s" if eval_limit is not None else ""
    cv2.putText(
        frame,
        f"{preset} | mặt={len(boxes)} | FPS={fps:.1f}{limit_txt} | q=thoát",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )


def save_faces(
    frame,
    boxes: List[Tuple[int, int, int, int]],
    output_dir: Path,
    preset: str,
    face_size: int,
) -> int:
    timestamp = int(time.time() * 1000)
    frame_h, frame_w = frame.shape[:2]
    saved = 0
    for index, (x1, y1, x2, y2) in enumerate(boxes):
        x1, y1, x2, y2 = clamp_box(x1, y1, x2, y2, frame_w, frame_h)
        if x2 <= x1 or y2 <= y1:
            continue
        face = frame[y1:y2, x1:x2]
        if face.size == 0:
            continue
        face = cv2.resize(face, (face_size, face_size))
        save_path = output_dir / f"{preset}_face_{timestamp}_{index}.jpg"
        cv2.imwrite(str(save_path), face)
        saved += 1
    return saved


def run_one_session(
    *,
    preset: str,
    weight_path: Path,
    camera_index: int,
    conf: float,
    detect_interval: float,
    face_size: int,
    output_dir: Path,
    save_enabled: bool,
    eval_seconds: Optional[float],
) -> SessionMetrics:
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("Không tìm thấy ultralytics. Cài: ultralytics") from exc
    model = YOLO(str(weight_path))
    if save_enabled:
        output_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Không mở được camera index {camera_index}")

    metrics = SessionMetrics(
        preset=preset,
        weight_path=str(weight_path),
        wall_seconds=0.0,
        frames_read=0,
        detect_runs=0,
    )

    last_detect_ts = 0.0
    last_boxes: List[Tuple[int, int, int, int]] = []
    session_start = time.time()

    print(f"\n--- Phiên: {preset} ---")
    print(f"Weight: {weight_path}")
    print(f"conf={conf}, detect_interval={detect_interval}s")
    if eval_seconds is not None:
        print(f"Giới hạn phiên: {eval_seconds:.1f}s (hoặc bấm q)")

    try:
        while True:
            loop_start = time.time()
            now = time.time()
            elapsed_session = now - session_start
            if eval_seconds is not None and elapsed_session >= eval_seconds:
                break

            ret, frame = cap.read()
            if not ret:
                print("Không đọc được frame từ camera.")
                break

            metrics.frames_read += 1

            if now - last_detect_ts >= detect_interval:
                t0 = time.perf_counter()
                result = model(frame, conf=conf, verbose=False)[0]
                metrics.inference_ms.append((time.perf_counter() - t0) * 1000.0)
                last_boxes = extract_boxes(result)
                metrics.detect_runs += 1
                metrics.face_counts_per_detect.append(len(last_boxes))
                if save_enabled and last_boxes:
                    metrics.saved_crops += save_faces(
                        frame, last_boxes, output_dir, preset, face_size
                    )
                last_detect_ts = now

            loop_elapsed = max(time.time() - loop_start, 1e-6)
            metrics.loop_fps_samples.append(1.0 / loop_elapsed)

            draw_boxes(
                frame,
                last_boxes,
                preset,
                metrics.loop_fps_samples[-1],
                elapsed_session,
                eval_seconds,
            )
            cv2.imshow(WINDOW_NAME, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()

    metrics.wall_seconds = time.time() - session_start
    return metrics


def print_session_evaluation(m: SessionMetrics) -> None:
    s = m.summary()
    print("\n=== Đánh giá phiên ===")
    for k, v in s.items():
        print(f"  {k}: {v}")


def print_comparison_table(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    print("\n========== So sánh nhanh các mô hình ==========")
    cols = [
        ("preset", "preset"),
        ("detect_runs", "detect_runs"),
        ("avg_inf_ms", "avg_inference_ms"),
        ("p95_inf_ms", "p95_inference_ms"),
        ("med_FPS", "median_loop_fps"),
        ("avg_mặt", "avg_faces_when_detect"),
        ("max_mặt", "max_faces_in_frame"),
    ]
    header = " | ".join(h for h, _ in cols)
    print(header)
    print("-" * len(header))
    for r in rows:
        print(" | ".join(str(r.get(key, "")) for _, key in cols))
    print("\n--- Chi tiết JSON từng mô hình ---")
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))


def main() -> None:
    args = parse_args()

    try:
        global cv2
        import cv2
    except ImportError as exc:
        raise RuntimeError("Không tìm thấy cv2. Cài: opencv-python") from exc

    output_dir = Path(args.output_dir).resolve()
    save_enabled = not args.no_save

    order: List[str] = list(WEIGHT_CANDIDATES.keys())
    if args.run_all:
        sessions: List[SessionMetrics] = []
        for preset in order:
            weight_path = resolve_weight_for_preset(preset, None)
            m = run_one_session(
                preset=preset,
                weight_path=weight_path,
                camera_index=args.camera_index,
                conf=args.conf,
                detect_interval=args.detect_interval,
                face_size=args.face_size,
                output_dir=output_dir,
                save_enabled=save_enabled,
                eval_seconds=max(1.0, float(args.eval_seconds)),
            )
            sessions.append(m)
            print_session_evaluation(m)

        summaries = [s.summary() for s in sessions]
        print_comparison_table(summaries)

        if args.report_json:
            out = Path(args.report_json).resolve()
            out.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\nĐã ghi báo cáo JSON: {out}")
        return

    weight_path = resolve_weight_for_preset(args.model, args.weight)
    m = run_one_session(
        preset=args.model,
        weight_path=weight_path,
        camera_index=args.camera_index,
        conf=args.conf,
        detect_interval=args.detect_interval,
        face_size=args.face_size,
        output_dir=output_dir,
        save_enabled=save_enabled,
        eval_seconds=None,
    )
    print_session_evaluation(m)
    if args.report_json:
        out = Path(args.report_json).resolve()
        out.write_text(json.dumps(m.summary(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Đã ghi báo cáo JSON: {out}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
