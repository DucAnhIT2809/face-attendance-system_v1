import io
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image

from app.config import get_settings
from app.db import execute, fetch_all, fetch_one
from app.deps import get_lecturer_context

router = APIRouter(prefix="/recognize", tags=["recognition"])

CONFIRM_HITS_REQUIRED = 4
MIN_SCORE_REQUIRED = 0.9
TRACK_IOU_THRESHOLD = 0.35
TRACK_TTL_FRAMES = 6
# Giữa hai lần nhận diện hợp lệ liên tiếp, không cộng quá N giây (tránh bù giờ khi camera/người dùng tạm ngắt lâu).
MAX_PRESENCE_STEP_SECONDS = 120
_RECOGNIZERS: dict[str, "InProcessRecognizer"] = {}
_RECOGNIZER_LOCK = threading.Lock()

# Runtime tracking state (in-memory)
# Dùng nội bộ cho confirm điểm danh + theo dõi thời gian hiện diện trong lớp.
# { session_id: { student_id: {hits, confirmed, last_score, last_seen, last_presence_at, presence_seconds, ...} } }
TRACKING_STATE: dict[str, dict[str, dict]] = {}
# { session_id: { track_id: {box, misses, identity, score, student, face_box} } }
LIVE_FACE_TRACKS: dict[str, dict[str, dict]] = {}
_NEXT_TRACK_ID = 1


def _next_track_id() -> str:
    global _NEXT_TRACK_ID
    track_id = f"face-{_NEXT_TRACK_ID}"
    _NEXT_TRACK_ID += 1
    return track_id


def _box_iou(a: dict[str, Any], b: dict[str, Any]) -> float:
    ax1, ay1 = float(a["x"]), float(a["y"])
    ax2, ay2 = ax1 + float(a["width"]), ay1 + float(a["height"])
    bx1, by1 = float(b["x"]), float(b["y"])
    bx2, by2 = bx1 + float(b["width"]), by1 + float(b["height"])

    inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = inter_w * inter_h
    if inter <= 0:
        return 0.0

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class InProcessRecognizer:
    def __init__(self, embedding_db_path: Path | None = None) -> None:
        settings = get_settings()
        if not settings.modelcore_root or not settings.arcface_checkpoint or not settings.face_embedding_db:
            raise HTTPException(
                status_code=503,
                detail="Chưa cấu hình MODELCORE_ROOT / ARCFACE_CHECKPOINT / FACE_EMBEDDING_DB trong .env (tuỳ chọn: MODELCORE_MODEL_DIR, mặc định Model_v2)",
            )

        model_dir = Path(settings.modelcore_root) / settings.modelcore_model_dir
        if not model_dir.is_dir():
            raise HTTPException(status_code=500, detail=f"Không tìm thấy thư mục model: {model_dir}")
        model_dir_str = str(model_dir.resolve())
        if model_dir_str not in sys.path:
            sys.path.insert(0, model_dir_str)

        try:
            import torch
            from face_pipeline.recognition.arcface_train import FaceDetector, build_transform, resolve_device, resolve_model_path
            from face_pipeline.recognition.recognize_face import load_backbone, load_embedding_db, predict_identity
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Không import được model trong backend: {exc}") from exc

        self.torch = torch
        self.predict_identity = predict_identity
        self.device = resolve_device("auto")
        selected_embedding_db = embedding_db_path or Path(settings.face_embedding_db).resolve()
        self.embedding_db_path = selected_embedding_db
        self.backbone, self.image_size = load_backbone(Path(settings.arcface_checkpoint).resolve(), self.device)
        self.person_embeddings = load_embedding_db(selected_embedding_db)
        self.transform = build_transform(image_size=self.image_size, train=False)
        self.face_detector = FaceDetector(resolve_model_path("yolov8s-face.pt"), conf=0.25)
        self.inference_lock = threading.Lock()

    def _recognize_crop(
        self,
        image: Image.Image,
        face_box_tuple: tuple[int, int, int, int],
        threshold: float,
    ) -> tuple[str, float]:
        face_image = image.crop(face_box_tuple)
        return self._recognize_face_image(face_image, threshold)

    def _recognize_face_image(self, face_image: Image.Image, threshold: float) -> tuple[str, float]:
        tensor = self.transform(face_image).unsqueeze(0).to(self.device)
        embedding = self.backbone(tensor)[0].detach().cpu()
        embedding = self.torch.nn.functional.normalize(embedding, p=2, dim=0)
        return self.predict_identity(embedding, self.person_embeddings, threshold)

    @staticmethod
    def _face_box_dict(
        face_box_tuple: tuple[int, int, int, int],
        source_width: int,
        source_height: int,
    ) -> dict[str, Any]:
        x1, y1, x2, y2 = face_box_tuple
        return {
            "x": x1,
            "y": y1,
            "width": max(0, x2 - x1),
            "height": max(0, y2 - y1),
            "image_width": source_width,
            "image_height": source_height,
        }

    def detect_faces(self, file_bytes: bytes) -> tuple[Image.Image, list[dict[str, Any]]]:
        image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        source_width, source_height = image.size
        with self.inference_lock:
            face_box_tuples = self.face_detector.detect_face_boxes(image)
        faces = [
            {
                "face_box_tuple": face_box_tuple,
                "face_box": self._face_box_dict(face_box_tuple, source_width, source_height),
            }
            for face_box_tuple in face_box_tuples
        ]
        return image, faces

    def recognize_face(
        self,
        image: Image.Image,
        detected_face: dict[str, Any],
        threshold: float,
    ) -> tuple[str, float]:
        with self.inference_lock, self.torch.no_grad():
            return self._recognize_crop(image, detected_face["face_box_tuple"], threshold)

    def recognize(
        self,
        file_bytes: bytes,
        threshold: float,
    ) -> tuple[str, str | None, float | None, dict[str, Any] | None, list[dict[str, Any]]]:
        started = time.perf_counter()
        image, detected_faces = self.detect_faces(file_bytes)
        source_width, source_height = image.size
        faces: list[dict[str, Any]] = []
        for detected_face in detected_faces:
            identity, score = self.recognize_face(image, detected_face, threshold)
            faces.append(
                {
                    "identity_label": identity,
                    "cosine_score": score,
                    "face_box": detected_face["face_box"],
                }
            )

        primary = faces[0] if faces else {}
        identity = primary.get("identity_label")
        score = primary.get("cosine_score")
        face_box = primary.get("face_box")
        first_box = None
        if face_box is not None:
            x1 = int(face_box["x"])
            y1 = int(face_box["y"])
            x2 = x1 + int(face_box["width"])
            y2 = y1 + int(face_box["height"])
            first_box = (x1, y1, x2, y2)
        elif detected_faces:
            first_box = detected_faces[0]["face_box_tuple"]
        if first_box is not None:
            x1, y1, x2, y2 = first_box
            face_box = {
                "x": x1,
                "y": y1,
                "width": max(0, x2 - x1),
                "height": max(0, y2 - y1),
                "image_width": source_width,
                "image_height": source_height,
            }

        elapsed_ms = (time.perf_counter() - started) * 1000
        raw_out = (
            f"Image size: {source_width}x{source_height}\n"
            f"Faces: {len(faces)}\n"
            f"Face box: {first_box if first_box is not None else 'none'}\n"
            f"Prediction: {identity}\n"
            f"Cosine score: {score if score is not None else 'none'}\n"
            f"In-process latency ms: {elapsed_ms:.1f}"
        )
        return raw_out, identity, score, face_box, faces


def _get_recognizer(embedding_db_path: Path | None = None) -> InProcessRecognizer:
    settings = get_settings()
    selected_path = (embedding_db_path or Path(settings.face_embedding_db)).resolve()
    cache_key = str(selected_path)
    if cache_key not in _RECOGNIZERS:
        with _RECOGNIZER_LOCK:
            if cache_key not in _RECOGNIZERS:
                _RECOGNIZERS[cache_key] = InProcessRecognizer(selected_path)
    return _RECOGNIZERS[cache_key]


def invalidate_recognizer_caches(paths: list[Path] | tuple[Path, ...]) -> None:
    """Xóa recognizer đã cache để lần nhận diện sau đọc lại face_db.pt từ đĩa."""
    resolved = {str(Path(p).resolve()) for p in paths if p is not None}
    if not resolved:
        return
    with _RECOGNIZER_LOCK:
        for key in resolved:
            _RECOGNIZERS.pop(key, None)


def _session_embedding_db_path(session_id: str, lecturer_id: str) -> tuple[Path | None, str | None]:
    row = fetch_one(
        """
        SELECT cc.class_code
        FROM class_sessions cs
        JOIN course_classes cc ON cc.id = cs.course_class_id
        WHERE cs.id = %s::uuid AND cc.lecturer_id = %s::uuid
        """,
        (session_id, lecturer_id),
    )
    if not row:
        raise HTTPException(status_code=403, detail="Bạn không có quyền điểm danh buổi học này")

    class_code = row["class_code"]
    settings = get_settings()
    class_db = (Path(settings.class_embedding_root) / class_code / "face_db.pt").resolve()
    return (class_db if class_db.exists() else None), class_code


def _resolve_student_by_identity(identity: str | None):
    if not identity or identity == "unknown":
        return None
    return fetch_one(
        """
        SELECT id, student_code, full_name, administrative_class
        FROM students
        WHERE student_code = %s
           OR lower(regexp_replace(full_name, '\\s+', '', 'g')) = lower(%s)
           OR lower(regexp_replace(full_name, '\\s+', '', 'g')) = lower(regexp_replace(%s, '[^A-Za-z0-9]', '', 'g'))
        LIMIT 1
        """,
        (identity, identity, identity),
    )


def _student_enrolled_in_session(student_id: str, session_id: str, lecturer_id: str):
    return fetch_one(
        """
        SELECT 1 AS ok
        FROM class_sessions cs
        JOIN course_classes cc ON cc.id = cs.course_class_id
        JOIN course_class_students ccs
          ON ccs.course_class_id = cc.id
         AND ccs.student_id = %s::uuid
         AND ccs.status = 'ACTIVE'
        WHERE cs.id = %s::uuid
          AND cc.lecturer_id = %s::uuid
        """,
        (student_id, session_id, lecturer_id),
    )


def _run_recognition(file_bytes: bytes, suffix: str, threshold: float, embedding_db_path: Path | None = None):
    try:
        recognizer = _get_recognizer(embedding_db_path)
        return recognizer.recognize(file_bytes, threshold)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"message": "Nhận diện trong backend thất bại", "error": str(exc)},
        )


def _record_face_hit(session_id: str, student: dict, score: float | None, threshold: float):
    sid = str(student["id"])
    session_state = TRACKING_STATE.setdefault(session_id, {})
    state = session_state.setdefault(
        sid,
        {
            "hits": 0,
            "confirmed": False,
            "last_score": None,
            "last_seen": None,
            "last_presence_at": None,
            "presence_seconds": 0,
            "student_code": student["student_code"],
            "full_name": student["full_name"],
        },
    )

    now = datetime.now(timezone.utc)
    valid_hit = score is not None and score >= max(threshold, MIN_SCORE_REQUIRED)

    # Chỉ tích lũy thời gian hiện diện khi nhận diện đạt ngưỡng (tránh cộng giờ khi score thấp / cache track cũ).
    last_pres_raw = state.get("last_presence_at")
    if last_pres_raw and valid_hit:
        try:
            prev = datetime.fromisoformat(last_pres_raw)
            if prev.tzinfo is None:
                prev = prev.replace(tzinfo=timezone.utc)
            delta = max(0, int((now - prev).total_seconds()))
            delta = min(delta, MAX_PRESENCE_STEP_SECONDS)
            state["presence_seconds"] = int(state.get("presence_seconds", 0)) + delta
        except ValueError:
            pass
    if valid_hit:
        state["last_presence_at"] = now.isoformat()
    elif not state.get("confirmed"):
        # Chưa điểm danh: mất chuỗi khớp → không nối mốc thời gian (tránh cộng bù sau khoảng lặng dài).
        state["last_presence_at"] = None

    if state.get("confirmed"):
        state["hits"] = CONFIRM_HITS_REQUIRED
    else:
        state["hits"] = int(state.get("hits", 0)) + 1 if valid_hit else 0

    state["last_score"] = score
    state["last_seen"] = now.isoformat()
    pending_hits = int(state["hits"])
    confirmed_now = False
    updated = None

    if not state.get("confirmed") and pending_hits >= CONFIRM_HITS_REQUIRED:
        state["confirmed"] = True
        confirmed_now = True
        execute(
            """
            INSERT INTO attendance_records (
                session_id, student_id, status, source, check_in_time,
                first_seen_at, last_seen_at, similarity_score, recognition_confidence, total_seen_seconds
            )
            VALUES (
                %s::uuid, %s::uuid, 'PRESENT'::attendance_status, 'FACE_RECOGNITION'::attendance_source,
                %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (session_id, student_id) DO UPDATE SET
                status = 'PRESENT'::attendance_status,
                source = 'FACE_RECOGNITION'::attendance_source,
                check_in_time = COALESCE(attendance_records.check_in_time, EXCLUDED.check_in_time),
                first_seen_at = COALESCE(attendance_records.first_seen_at, EXCLUDED.first_seen_at),
                last_seen_at = EXCLUDED.last_seen_at,
                similarity_score = EXCLUDED.similarity_score,
                recognition_confidence = EXCLUDED.recognition_confidence,
                total_seen_seconds = GREATEST(attendance_records.total_seen_seconds, EXCLUDED.total_seen_seconds),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                session_id,
                sid,
                now,
                now,
                now,
                score,
                score,
                int(state.get("presence_seconds", 0)),
            ),
        )
        updated = {
            "student_id": sid,
            "student_code": student["student_code"],
            "full_name": student["full_name"],
        }
    elif state.get("confirmed"):
        execute(
            """
            UPDATE attendance_records
            SET last_seen_at = %s,
                similarity_score = %s,
                recognition_confidence = %s,
                total_seen_seconds = GREATEST(total_seen_seconds, %s),
                updated_at = CURRENT_TIMESTAMP
            WHERE session_id = %s::uuid AND student_id = %s::uuid
            """,
            (
                now,
                score,
                score,
                int(state.get("presence_seconds", 0)),
                session_id,
                sid,
            ),
        )

    return pending_hits, confirmed_now, updated


@router.post("/identity")
async def recognize_identity(
    ctx: Annotated[dict, Depends(get_lecturer_context)],
    file: UploadFile = File(...),
    threshold: float = 0.4,
):
    """
    Nhận diện ảnh upload bằng model đã cache trong tiến trình backend.
    Cần cấu hình MODELCORE_ROOT / MODELCORE_MODEL_DIR (tuỳ chọn) / ARCFACE_CHECKPOINT / FACE_EMBEDDING_DB trong .env
    """
    suffix = Path(file.filename or "upload.jpg").suffix or ".jpg"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="File rỗng")

    out, identity, score, face_box, faces = _run_recognition(data, suffix, threshold)

    student = _resolve_student_by_identity(identity)
    if student:
        student = {k: (str(v) if k == "id" else v) for k, v in student.items()}

    return {
        "raw_stdout_tail": out[-1500:],
        "identity_label": identity,
        "cosine_score": score,
        "face_box": face_box,
        "faces": faces,
        "threshold": threshold,
        "matched_student": student,
        "requested_by_lecturer_id": str(ctx["lecturer_id"]),
    }


@router.post("/realtime-frame")
async def recognize_realtime_frame(
    ctx: Annotated[dict, Depends(get_lecturer_context)],
    file: UploadFile = File(...),
    session_id: str = "",
    threshold: float = 0.9,
):
    """
    Nhận 1 frame từ frontend, nhận diện và cập nhật attendance_records ngay lập tức.
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="Thiếu session_id")
    suffix = Path(file.filename or "frame.jpg").suffix or ".jpg"
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="File rỗng")

    started = time.perf_counter()
    embedding_db_path, class_code = _session_embedding_db_path(session_id, str(ctx["lecturer_id"]))
    recognizer = _get_recognizer(embedding_db_path)
    image, detected_faces = recognizer.detect_faces(data)
    tracks = LIVE_FACE_TRACKS.setdefault(session_id, {})
    for track in tracks.values():
        track["misses"] = int(track.get("misses", 0)) + 1

    faces: list[dict[str, Any]] = []
    seen_student_ids: set[str] = set()
    updated = None

    for detected_face in detected_faces:
        face_box = detected_face["face_box"]
        matched_track_id = None
        matched_iou = 0.0
        for track_id, track in tracks.items():
            iou = _box_iou(face_box, track["face_box"])
            if iou > matched_iou:
                matched_iou = iou
                matched_track_id = track_id

        if matched_track_id and matched_iou >= TRACK_IOU_THRESHOLD:
            track = tracks[matched_track_id]
            track["misses"] = 0
            track["face_box"] = face_box
            identity = track.get("identity_label")
            score = track.get("cosine_score")
            student = track.get("student")
            recognized_now = False
            if not student and (not identity or identity == "unknown"):
                identity, score = recognizer.recognize_face(image, detected_face, threshold)
                student = _resolve_student_by_identity(identity)
                if student and not _student_enrolled_in_session(str(student["id"]), session_id, str(ctx["lecturer_id"])):
                    student = None
                track["identity_label"] = identity
                track["cosine_score"] = score
                track["student"] = student
                recognized_now = True
        else:
            matched_track_id = _next_track_id()
            identity, score = recognizer.recognize_face(image, detected_face, threshold)
            student = _resolve_student_by_identity(identity)
            if student and not _student_enrolled_in_session(str(student["id"]), session_id, str(ctx["lecturer_id"])):
                student = None
            track = {
                "misses": 0,
                "face_box": face_box,
                "identity_label": identity,
                "cosine_score": score,
                "student": student,
            }
            tracks[matched_track_id] = track
            recognized_now = True

        pending_hits = 0
        confirmed = False
        candidate_student = None
        matched_student = None
        if student:
            sid = str(student["id"])
            seen_student_ids.add(sid)
            pending_hits, confirmed, matched_student = _record_face_hit(session_id, student, score, threshold)
            updated = matched_student or updated
            candidate_student = {
                "student_id": sid,
                "student_code": student["student_code"],
                "full_name": student["full_name"],
            }
            confirmed = bool(TRACKING_STATE.get(session_id, {}).get(sid, {}).get("confirmed"))

        faces.append(
            {
                "track_id": matched_track_id,
                "identity_label": identity,
                "cosine_score": score,
                "face_box": face_box,
                "confirmed": confirmed,
                "pending_hits": pending_hits,
                "required_hits": CONFIRM_HITS_REQUIRED,
                "candidate_student": candidate_student,
                "matched_student": matched_student,
                "recognized_now": recognized_now,
            }
        )

    for track_id in [tid for tid, track in tracks.items() if int(track.get("misses", 0)) > TRACK_TTL_FRAMES]:
        del tracks[track_id]

    session_state = TRACKING_STATE.get(session_id, {})
    for sid, item in session_state.items():
        if sid not in seen_student_ids and not item.get("confirmed"):
            item["hits"] = 0

    primary = faces[0] if faces else {}
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "identity_label": primary.get("identity_label"),
        "cosine_score": primary.get("cosine_score"),
        "face_box": primary.get("face_box"),
        "faces": faces,
        "confirmed": bool(primary.get("confirmed")),
        "pending_hits": int(primary.get("pending_hits", 0)),
        "required_hits": CONFIRM_HITS_REQUIRED,
        "min_score_required": max(threshold, MIN_SCORE_REQUIRED),
        "matched_student": primary.get("matched_student") or updated,
        "candidate_student": primary.get("candidate_student"),
        "raw_stdout_tail": f"Detected faces: {len(detected_faces)}\nLive latency ms: {elapsed_ms:.1f}",
        "session_id": session_id,
        "class_code": class_code,
        "embedding_db": str(recognizer.embedding_db_path),
        "requested_by_lecturer_id": str(ctx["lecturer_id"]),
    }


@router.get("/live-board")
def live_board(
    ctx: Annotated[dict, Depends(get_lecturer_context)],
    session_id: str = "",
):
    """
    Trả về danh sách đã ghi nhận/chưa ghi nhận của một buổi để frontend hiển thị realtime.
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="Thiếu session_id")

    rows = fetch_all(
        """
        SELECT st.student_code, st.full_name,
               COALESCE(ar.status::text, 'UNKNOWN') AS status,
               ar.check_in_time, ar.last_seen_at, ar.similarity_score
        FROM class_sessions cs
        JOIN course_classes cc ON cc.id = cs.course_class_id
        JOIN course_class_students ccs ON ccs.course_class_id = cc.id AND ccs.status = 'ACTIVE'
        JOIN students st ON st.id = ccs.student_id
        LEFT JOIN attendance_records ar ON ar.session_id = cs.id AND ar.student_id = st.id
        WHERE cs.id = %s::uuid AND cc.lecturer_id = %s::uuid
        ORDER BY st.student_code
        """,
        (session_id, str(ctx["lecturer_id"])),
    )

    present = []
    absent = []
    for r in rows:
        item = {
            "student_code": r["student_code"],
            "full_name": r["full_name"],
            "status": r["status"],
            "check_in_time": r["check_in_time"].isoformat() if r["check_in_time"] else None,
            "last_seen_at": r["last_seen_at"].isoformat() if r["last_seen_at"] else None,
            "similarity_score": float(r["similarity_score"]) if r["similarity_score"] is not None else None,
        }
        if r["status"] == "PRESENT":
            present.append(item)
        else:
            absent.append(item)

    return {
        "session_id": session_id,
        "present_count": len(present),
        "not_present_count": len(absent),
        "present": present,
        "not_present": absent,
    }


@router.get("/live-tracking")
def live_tracking(
    ctx: Annotated[dict, Depends(get_lecturer_context)],
    session_id: str = "",
):
    """
    Trả trạng thái tích lũy nhận diện realtime (đủ 4 lần >= 0.9 mới xác nhận điểm danh).
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="Thiếu session_id")

    # Verify lecturer owns the session
    owned = fetch_one(
        """
        SELECT 1 AS ok
        FROM class_sessions cs
        JOIN course_classes cc ON cc.id = cs.course_class_id
        WHERE cs.id = %s::uuid AND cc.lecturer_id = %s::uuid
        """,
        (session_id, str(ctx["lecturer_id"])),
    )
    if not owned:
        raise HTTPException(status_code=403, detail="Bạn không có quyền xem tracking của buổi này")

    state = TRACKING_STATE.get(session_id, {})
    items = []
    for sid, item in state.items():
        items.append(
            {
                "student_id": sid,
                "student_code": item.get("student_code"),
                "full_name": item.get("full_name"),
                "hits": int(item.get("hits", 0)),
                "required_hits": CONFIRM_HITS_REQUIRED,
                "last_score": item.get("last_score"),
                "last_seen": item.get("last_seen"),
                "presence_seconds": int(item.get("presence_seconds", 0)),
                "ready": int(item.get("hits", 0)) >= CONFIRM_HITS_REQUIRED,
            }
        )
    items.sort(key=lambda x: (-x["hits"], x.get("student_code") or ""))
    return {"session_id": session_id, "tracking": items}
