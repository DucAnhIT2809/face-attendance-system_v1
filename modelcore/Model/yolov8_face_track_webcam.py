from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import torch
from PIL import Image

from arcface_train import ArcFaceBackbone, build_transform, resolve_device


DEFAULT_WEIGHT = "yolov8n-face.pt"
DEFAULT_CAMERA_INDEX = 2
DEFAULT_CONFIDENCE = 0.5
DEFAULT_IOU = 0.45
DEFAULT_FACE_SIZE = 112
DEFAULT_OUTPUT_DIR = "DatadetectTrack"
DEFAULT_TRACKER = "bytetrack.yaml"
DEFAULT_SAVE_INTERVAL = 2.0
DEFAULT_RECOGNIZE_INTERVAL = 0.8
DEFAULT_CONFIRM_FRAMES = 4
DEFAULT_TRACK_STALE_SECONDS = 3.0
WINDOW_NAME = "YOLOv8-Face Tracking - Camera"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Track faces from webcam using YOLOv8-face and the built-in Ultralytics tracker."
    )
    parser.add_argument("--weight", type=str, default=DEFAULT_WEIGHT, help="Path to YOLOv8-face weight file.")
    parser.add_argument("--camera-index", type=int, default=DEFAULT_CAMERA_INDEX, help="Webcam index.")
    parser.add_argument("--conf", type=float, default=DEFAULT_CONFIDENCE, help="Confidence threshold.")
    parser.add_argument("--iou", type=float, default=DEFAULT_IOU, help="IoU threshold.")
    parser.add_argument("--tracker", type=str, default=DEFAULT_TRACKER, help="Tracker config, e.g. bytetrack.yaml.")
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
        help="Directory used to save tracked face crops.",
    )
    parser.add_argument("--no-save", action="store_true", help="Show tracking only, do not save crops.")
    parser.add_argument(
        "--save-once-per-track",
        action="store_true",
        help="Save only one crop for each track_id.",
    )
    parser.add_argument(
        "--save-interval",
        type=float,
        default=DEFAULT_SAVE_INTERVAL,
        help="Minimum seconds between saved crops for the same track_id when not using --save-once-per-track.",
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        default="Model/arcface_runs/arcface_resnet18_augmented.pth",
        help="Path to ArcFace checkpoint (.pth).",
    )
    parser.add_argument(
        "--embedding-db",
        type=str,
        default="Model/arcface_runs/face_db.pt",
        help="Path to exported embedding DB (.pt).",
    )
    parser.add_argument(
        "--recognition-threshold",
        type=float,
        default=0.85,
        help="Cosine similarity threshold for known identity.",
    )
    parser.add_argument(
        "--recognize-interval",
        type=float,
        default=DEFAULT_RECOGNIZE_INTERVAL,
        help="Minimum seconds between re-recognition for the same track_id.",
    )
    parser.add_argument(
        "--confirm-frames",
        type=int,
        default=DEFAULT_CONFIRM_FRAMES,
        help="Require this many consistent recognized frames before confirming identity.",
    )
    parser.add_argument(
        "--track-stale-seconds",
        type=float,
        default=DEFAULT_TRACK_STALE_SECONDS,
        help="Forget inactive track states after N seconds.",
    )
    parser.add_argument("--device", type=str, default="auto", help="Device for ArcFace inference: auto/cpu/cuda/mps.")
    parser.add_argument("--pg-host", type=str, default="localhost")
    parser.add_argument("--pg-port", type=int, default=5432)
    parser.add_argument("--pg-db", type=str, default="face_attendance")
    parser.add_argument("--pg-user", type=str, default="postgres")
    parser.add_argument("--pg-password", type=str, default="postgres")
    parser.add_argument("--disable-attendance-db", action="store_true", help="Disable PostgreSQL attendance logging.")
    return parser.parse_args()


def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


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


def extract_tracks(result) -> List[Dict[str, Any]]:
    boxes = result.boxes
    if boxes is None or boxes.xyxy is None:
        return []

    xyxy = boxes.xyxy.tolist()
    ids = boxes.id.tolist() if boxes.id is not None else []
    confs = boxes.conf.tolist() if boxes.conf is not None else []

    tracks = []
    for index, coords in enumerate(xyxy):
        x1, y1, x2, y2 = map(int, coords[:4])
        track_id = int(ids[index]) if index < len(ids) and ids[index] is not None else None
        confidence = float(confs[index]) if index < len(confs) else None
        tracks.append(
            {
                "track_id": track_id,
                "confidence": confidence,
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
            }
        )
    return tracks


def draw_tracks(frame, tracks: List[Dict[str, Any]]) -> None:
    for track in tracks:
        x1 = int(track["x1"])
        y1 = int(track["y1"])
        x2 = int(track["x2"])
        y2 = int(track["y2"])
        track_id = track["track_id"]
        confidence = track["confidence"]
        person_name = track.get("name")
        person_score = track.get("score")
        person_id = track.get("person_id")
        status = track.get("status")

        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"id={track_id}" if track_id is not None else "id=?"
        if confidence is not None:
            label += f" conf={confidence:.2f}"
        if person_name is not None and person_score is not None:
            label += f" | {person_name} ({float(person_score):.2f})"
        if person_id is not None:
            label += f" PID={person_id}"
        if status is not None:
            label += f" [{status}]"
        cv2.putText(
            frame,
            label,
            (x1, max(20, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )


class ArcFaceRecognizer:
    def __init__(self, checkpoint_path: Path, db_path: Path, threshold: float, device: torch.device) -> None:
        self.threshold = threshold
        self.device = device
        self.backbone, self.image_size = self._load_backbone(checkpoint_path)
        self.person_embeddings = self._load_embedding_db(db_path)
        self.transform = build_transform(image_size=self.image_size, train=False)

    def _load_backbone(self, checkpoint_path: Path) -> tuple[ArcFaceBackbone, int]:
        checkpoint = torch.load(checkpoint_path, map_location=self.device)
        embedding_size = int(checkpoint["embedding_size"])
        image_size = int(checkpoint["image_size"])
        backbone = ArcFaceBackbone(embedding_size=embedding_size, pretrained_backbone=False).to(self.device)
        backbone.load_state_dict(checkpoint["backbone_state_dict"], strict=True)
        backbone.eval()
        return backbone, image_size

    def _load_embedding_db(self, db_path: Path) -> Dict[str, torch.Tensor]:
        db = torch.load(db_path, map_location="cpu")
        person_embeddings = db.get("person_embeddings")
        if not isinstance(person_embeddings, dict) or not person_embeddings:
            raise ValueError(f"Invalid embedding DB: {db_path}")

        normalized: Dict[str, torch.Tensor] = {}
        for person_name, embedding in person_embeddings.items():
            tensor = embedding.detach().cpu().float()
            normalized[person_name] = torch.nn.functional.normalize(tensor, p=2, dim=0)
        return normalized

    @torch.no_grad()
    def recognize_face_bgr(self, face_bgr) -> Tuple[str, float]:
        face_rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(face_rgb)
        tensor = self.transform(pil_image).unsqueeze(0).to(self.device)
        query = self.backbone(tensor)[0].detach().cpu()
        query = torch.nn.functional.normalize(query, p=2, dim=0)

        best_name = "unknown"
        best_score = -1.0
        for person_name, ref_embedding in self.person_embeddings.items():
            score = torch.dot(query, ref_embedding).item()
            if score > best_score:
                best_score = score
                best_name = person_name
        if best_score < self.threshold:
            return "unknown", best_score
        return best_name, best_score


class AttendanceDB:
    def __init__(self, host: str, port: int, database: str, user: str, password: str) -> None:
        try:
            import psycopg2
        except ImportError as exc:
            raise RuntimeError("Khong tim thay psycopg2. Hay cai `pip install psycopg2-binary`.") from exc

        self.conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=database,
            user=user,
            password=password,
        )
        self.conn.autocommit = True
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS attendance_records (
                    id SERIAL PRIMARY KEY,
                    attendance_date DATE NOT NULL,
                    person_name TEXT NOT NULL,
                    person_id INTEGER NOT NULL,
                    first_seen_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    last_score REAL,
                    UNIQUE (attendance_date, person_name)
                );
                """
            )

    def mark_present(self, person_name: str, person_id: int, score: float) -> bool:
        today = date.today()
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO attendance_records (attendance_date, person_name, person_id, last_score)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (attendance_date, person_name) DO NOTHING
                RETURNING id;
                """,
                (today, person_name, person_id, score),
            )
            inserted = cursor.fetchone()
            return inserted is not None

    def close(self) -> None:
        self.conn.close()


@dataclass
class TrackState:
    candidate_name: str = "unknown"
    candidate_streak: int = 0
    latest_score: float = -1.0
    confirmed_name: str = "unknown"
    confirmed_score: float = -1.0
    confirmed_person_id: Optional[int] = None
    last_seen_ts: float = 0.0


def should_save_track(
    track_id: Optional[int],
    now: float,
    last_saved_at: Dict[int, float],
    save_once_per_track: bool,
    save_interval: float,
) -> bool:
    if track_id is None:
        return False

    if save_once_per_track:
        return track_id not in last_saved_at

    previous = last_saved_at.get(track_id)
    if previous is None:
        return True
    return (now - previous) >= save_interval


def save_tracks(
    frame,
    tracks: List[Dict[str, Any]],
    output_dir: Path,
    face_size: int,
    last_saved_at: Dict[int, float],
    save_once_per_track: bool,
    save_interval: float,
) -> None:
    frame_height, frame_width = frame.shape[:2]
    now = time.time()

    for track in tracks:
        track_id = track["track_id"]
        if not should_save_track(track_id, now, last_saved_at, save_once_per_track, save_interval):
            continue

        x1, y1, x2, y2 = clamp_box(
            int(track["x1"]),
            int(track["y1"]),
            int(track["x2"]),
            int(track["y2"]),
            frame_width,
            frame_height,
        )
        if x2 <= x1 or y2 <= y1:
            continue

        face = frame[y1:y2, x1:x2]
        if face.size == 0:
            continue

        face = cv2.resize(face, (face_size, face_size))
        save_path = output_dir / f"track_{track_id}_{int(now * 1000)}.jpg"
        cv2.imwrite(str(save_path), face)
        last_saved_at[int(track_id)] = now
        print(f"Saved: {save_path}")


def run_tracking(
    model_path: Path,
    camera_index: int,
    conf: float,
    iou: float,
    tracker: str,
    output_dir: Path,
    face_size: int,
    save_enabled: bool,
    save_once_per_track: bool,
    save_interval: float,
    recognizer: ArcFaceRecognizer,
    recognize_interval: float,
    confirm_frames: int,
    track_stale_seconds: float,
    attendance_db: AttendanceDB | None,
) -> None:
    model = YOLO(str(model_path))
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open webcam index {camera_index}")

    last_saved_at: Dict[int, float] = {}
    last_recognized_at: Dict[int, float] = {}
    track_states: Dict[int, TrackState] = {}
    person_to_fixed_id: Dict[str, int] = {
        person_name: index + 1 for index, person_name in enumerate(sorted(recognizer.person_embeddings.keys()))
    }
    marked_today: set[str] = set()

    print(f"Weight: {model_path}")
    print(f"Camera index: {camera_index}")
    print(f"Confidence threshold: {conf}")
    print(f"IoU threshold: {iou}")
    print(f"Tracker: {tracker}")
    print(f"Confirm frames: {confirm_frames}")
    print(f"Save face crops: {save_enabled}")
    print(f"Attendance DB enabled: {attendance_db is not None}")
    if save_enabled:
        print(f"Output dir: {output_dir.resolve()}")
        if save_once_per_track:
            print("Save mode: one crop per track_id")
        else:
            print(f"Save mode: one crop per track every {save_interval}s")
    print("Press 'q' to quit.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Khong doc duoc frame tu camera!")
                break

            result = model.track(
                frame,
                persist=True,
                conf=conf,
                iou=iou,
                tracker=tracker,
                verbose=False,
            )[0]
            tracks = extract_tracks(result)

            frame_height, frame_width = frame.shape[:2]
            now = time.time()
            active_track_ids = set()
            for track in tracks:
                track_id = track["track_id"]
                if track_id is None:
                    continue
                active_track_ids.add(track_id)
                state = track_states.setdefault(track_id, TrackState())
                state.last_seen_ts = now

                previous_ts = last_recognized_at.get(track_id)
                if previous_ts is not None and (now - previous_ts) < recognize_interval:
                    continue

                x1, y1, x2, y2 = clamp_box(
                    int(track["x1"]),
                    int(track["y1"]),
                    int(track["x2"]),
                    int(track["y2"]),
                    frame_width,
                    frame_height,
                )
                if x2 <= x1 or y2 <= y1:
                    continue

                face = frame[y1:y2, x1:x2]
                if face.size == 0:
                    continue

                person_name, score = recognizer.recognize_face_bgr(face)
                state.latest_score = score
                if person_name == state.candidate_name:
                    state.candidate_streak += 1
                else:
                    state.candidate_name = person_name
                    state.candidate_streak = 1

                if (
                    person_name != "unknown"
                    and state.candidate_streak >= max(confirm_frames, 1)
                ):
                    state.confirmed_name = person_name
                    state.confirmed_score = score
                    state.confirmed_person_id = person_to_fixed_id[person_name]
                    if attendance_db is not None and person_name not in marked_today:
                        inserted = attendance_db.mark_present(
                            person_name=person_name,
                            person_id=state.confirmed_person_id,
                            score=score,
                        )
                        if inserted:
                            print(
                                f"[ATTENDANCE] {person_name} (id={state.confirmed_person_id}) "
                                f"duoc diem danh ngay {date.today().isoformat()}"
                            )
                        marked_today.add(person_name)

                last_recognized_at[track_id] = now

            stale_ids: List[int] = []
            for track_id, state in track_states.items():
                if track_id not in active_track_ids and (now - state.last_seen_ts) > track_stale_seconds:
                    stale_ids.append(track_id)
            for stale_id in stale_ids:
                track_states.pop(stale_id, None)
                last_recognized_at.pop(stale_id, None)

            for track in tracks:
                track_id = track["track_id"]
                if track_id is None:
                    continue
                state = track_states.get(track_id)
                if state is None:
                    continue
                if state.confirmed_name != "unknown" and state.confirmed_person_id is not None:
                    track["name"] = state.confirmed_name
                    track["score"] = state.confirmed_score
                    track["person_id"] = state.confirmed_person_id
                    track["status"] = "confirmed"
                elif state.candidate_name != "unknown":
                    track["name"] = state.candidate_name
                    track["score"] = state.latest_score
                    track["status"] = f"verifying {state.candidate_streak}/{max(confirm_frames, 1)}"

            draw_tracks(frame, tracks)
            cv2.putText(
                frame,
                f"Tracks: {len(tracks)} | Press q to quit",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

            if save_enabled and tracks:
                save_tracks(
                    frame=frame,
                    tracks=tracks,
                    output_dir=output_dir,
                    face_size=face_size,
                    last_saved_at=last_saved_at,
                    save_once_per_track=save_once_per_track,
                    save_interval=save_interval,
                )

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

    try:
        global YOLO
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("Khong tim thay ultralytics. Hay cai `ultralytics`.") from exc

    model_path = resolve_model_path(args.weight)
    checkpoint_path = Path(args.checkpoint).resolve()
    db_path = Path(args.embedding_db).resolve()
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"ArcFace checkpoint not found: {checkpoint_path}")
    if not db_path.exists():
        raise FileNotFoundError(f"Embedding DB not found: {db_path}")

    arcface_device = resolve_device(args.device)
    recognizer = ArcFaceRecognizer(
        checkpoint_path=checkpoint_path,
        db_path=db_path,
        threshold=args.recognition_threshold,
        device=arcface_device,
    )
    attendance_db = None
    if not args.disable_attendance_db:
        attendance_db = AttendanceDB(
            host=args.pg_host,
            port=args.pg_port,
            database=args.pg_db,
            user=args.pg_user,
            password=args.pg_password,
        )

    output_dir = Path(args.output_dir)
    save_enabled = not args.no_save
    if save_enabled:
        ensure_output_dir(output_dir)

    try:
        run_tracking(
            model_path=model_path,
            camera_index=args.camera_index,
            conf=args.conf,
            iou=args.iou,
            tracker=args.tracker,
            output_dir=output_dir,
            face_size=args.face_size,
            save_enabled=save_enabled,
            save_once_per_track=args.save_once_per_track,
            save_interval=args.save_interval,
            recognizer=recognizer,
            recognize_interval=args.recognize_interval,
            confirm_frames=args.confirm_frames,
            track_stale_seconds=args.track_stale_seconds,
            attendance_db=attendance_db,
        )
    finally:
        if attendance_db is not None:
            attendance_db.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
