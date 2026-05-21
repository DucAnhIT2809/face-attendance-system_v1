"""Cập nhật embedding một sinh viên vào face_db.pt sau khi upload ảnh (không train lại toàn bộ)."""

from __future__ import annotations

import io
import sys
import threading
from pathlib import Path
from typing import Any

import torch
from PIL import Image

from app.config import get_settings
from app.db import execute, fetch_all

_EMB_LOCK = threading.Lock()


def _ensure_model_on_syspath() -> Path:
    settings = get_settings()
    if not settings.modelcore_root:
        raise RuntimeError("Chưa cấu hình MODELCORE_ROOT")
    model_dir = Path(settings.modelcore_root) / settings.modelcore_model_dir
    if not model_dir.is_dir():
        raise RuntimeError(f"Không tìm thấy thư mục model: {model_dir}")
    s = str(model_dir.resolve())
    if s not in sys.path:
        sys.path.insert(0, s)
    return model_dir


def _class_codes_for_student(student_id: str) -> list[str]:
    rows = fetch_all(
        """
        SELECT DISTINCT cc.class_code
        FROM course_class_students ccs
        JOIN course_classes cc ON cc.id = ccs.course_class_id
        WHERE ccs.student_id = %s::uuid AND ccs.status = 'ACTIVE'
        ORDER BY cc.class_code
        """,
        (student_id,),
    )
    return [str(r["class_code"]) for r in rows if r.get("class_code")]


def _embedding_db_targets(student_id: str) -> list[Path]:
    settings = get_settings()
    out: list[Path] = []
    seen: set[str] = set()

    def add(p: Path | None) -> None:
        if not p:
            return
        r = p.resolve()
        k = str(r)
        if k in seen:
            return
        seen.add(k)
        out.append(r)

    if settings.face_embedding_db:
        add(Path(settings.face_embedding_db))

    root = Path(settings.class_embedding_root)
    for code in _class_codes_for_student(student_id):
        p = (root / code / "face_db.pt").resolve()
        if p.is_file():
            add(p)
    return out


@torch.no_grad()
def _encode_rgb_pil(
    backbone: Any,
    image: Image.Image,
    image_size: int,
    device: torch.device,
    face_detector: Any | None,
    transform: Any,
) -> torch.Tensor:
    if face_detector is not None:
        image = face_detector.crop_largest_face(image)
    tensor = transform(image).unsqueeze(0).to(device)
    emb = backbone(tensor)[0].detach().cpu()
    return torch.nn.functional.normalize(emb.float(), p=2, dim=0)


def _mean_embedding_from_contents(image_contents: list[bytes]) -> torch.Tensor:
    if not image_contents:
        raise ValueError("Không có dữ liệu ảnh")

    _ensure_model_on_syspath()
    from face_pipeline.recognition.arcface_train import FaceDetector, build_transform, resolve_device, resolve_model_path
    from face_pipeline.recognition.recognize_face import load_backbone

    settings = get_settings()
    ckpt = Path(settings.arcface_checkpoint).resolve()
    if not ckpt.is_file():
        raise FileNotFoundError(f"Không tìm thấy checkpoint ArcFace: {ckpt}")

    device = resolve_device("auto")
    backbone, image_size = load_backbone(ckpt, device)
    transform = build_transform(image_size=image_size, train=False)
    det_path = resolve_model_path("yolov8s-face.pt")
    face_detector = FaceDetector(det_path, conf=0.25)

    vectors: list[torch.Tensor] = []
    for raw in image_contents:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        vectors.append(_encode_rgb_pil(backbone, img, image_size, device, face_detector, transform))

    stacked = torch.stack(vectors, dim=0)
    mean = torch.nn.functional.normalize(stacked.mean(dim=0), p=2, dim=0)
    return mean


def _merge_vector_into_db_file(
    db_path: Path,
    identity: str,
    new_vec: torch.Tensor,
    checkpoint_path: Path,
    n_new_images: int,
) -> None:
    new_vec = torch.nn.functional.normalize(new_vec.detach().cpu().float(), p=2, dim=0)

    if db_path.is_file():
        data: dict[str, Any] = torch.load(db_path, map_location="cpu")
    else:
        ck = torch.load(checkpoint_path, map_location="cpu")
        data = {
            "checkpoint_path": str(checkpoint_path),
            "image_size": int(ck["image_size"]),
            "embedding_size": int(new_vec.numel()),
            "person_embeddings": {},
            "samples_per_person": {},
        }

    pe = data.get("person_embeddings")
    if not isinstance(pe, dict):
        pe = {}
    else:
        pe = {str(k): v.detach().cpu().float() for k, v in pe.items()}

    old = pe.get(identity)
    if old is not None:
        old_n = torch.nn.functional.normalize(old, p=2, dim=0)
        merged = torch.nn.functional.normalize(0.5 * old_n + 0.5 * new_vec, p=2, dim=0)
        pe[identity] = merged
    else:
        pe[identity] = new_vec

    data["person_embeddings"] = pe
    data["embedding_size"] = int(new_vec.numel())
    if "image_size" not in data:
        ck = torch.load(checkpoint_path, map_location="cpu")
        data["image_size"] = int(ck["image_size"])
    if "checkpoint_path" not in data:
        data["checkpoint_path"] = str(checkpoint_path)

    sp = data.get("samples_per_person")
    if not isinstance(sp, dict):
        sp = {}
    sp[identity] = int(sp.get(identity, 0)) + max(1, int(n_new_images))
    data["samples_per_person"] = sp

    db_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(data, db_path)


def merge_embeddings_after_face_upload(
    *,
    student_id: str,
    student_code: str,
    image_contents: list[bytes],
    created_image_ids: list[str],
) -> dict[str, Any]:
    """
    Trích xuất embedding từ các ảnh vừa upload, gộp vào face_db.pt (global + từng lớp nếu đã có file),
    xóa cache recognizer, đánh dấu ảnh VALID + dùng cho training.
    """
    if not image_contents or not created_image_ids:
        return {"ok": False, "skipped": True, "reason": "no_images"}

    settings = get_settings()
    if not settings.modelcore_root or not settings.arcface_checkpoint or not settings.face_embedding_db:
        return {
            "ok": False,
            "skipped": True,
            "reason": "missing_model_env",
            "detail": "Cần MODELCORE_ROOT, ARCFACE_CHECKPOINT, FACE_EMBEDDING_DB trong .env",
        }

    targets = _embedding_db_targets(student_id)
    if not targets:
        return {"ok": False, "skipped": True, "reason": "no_embedding_db_paths"}

    ckpt = Path(settings.arcface_checkpoint).resolve()

    try:
        with _EMB_LOCK:
            new_vec = _mean_embedding_from_contents(image_contents)
            updated = []
            n_img = len(image_contents)
            for db_path in targets:
                _merge_vector_into_db_file(db_path, student_code, new_vec, ckpt, n_img)
                updated.append(str(db_path))

        for img_id in created_image_ids:
            execute(
                """
                UPDATE student_face_images
                SET status = 'VALID'::face_image_status,
                    is_used_for_training = TRUE,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s::uuid
                """,
                (img_id,),
            )

        from app.routers.recognition import invalidate_recognizer_caches

        invalidate_recognizer_caches(targets)

        return {"ok": True, "updated_dbs": updated, "identity": student_code}
    except Exception as exc:
        return {"ok": False, "skipped": False, "error": str(exc)}

