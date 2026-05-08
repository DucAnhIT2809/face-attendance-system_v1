from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import UUID
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.config import get_settings
from app.db import execute, execute_returning, fetch_all, rows_to_json_serializable
from app.deps import get_student_context

router = APIRouter(prefix="/student", tags=["student"])


class CreateRecheckRequestBody(BaseModel):
    session_id: UUID
    reason: str = Field(min_length=3, max_length=1000)


@router.get("/me")
def student_me(ctx: Annotated[dict, Depends(get_student_context)]):
    return {
        "user_id": str(ctx["id"]),
        "username": ctx["username"],
        "student_id": str(ctx["student_id"]),
        "student_code": ctx["student_code"],
        "full_name": ctx["full_name"],
        "administrative_class": ctx["administrative_class"],
        "email": ctx["email"],
        "phone": ctx["phone"],
        "student_status": ctx["student_status"],
        "face_folder": ctx["face_folder"],
    }


class UpdateStudentProfileBody(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=30)


@router.patch("/me")
def update_student_me(
    body: UpdateStudentProfileBody,
    ctx: Annotated[dict, Depends(get_student_context)],
):
    email = (body.email or "").strip() or None
    phone = (body.phone or "").strip() or None

    if email and "@" not in email:
        raise HTTPException(status_code=400, detail="Email không hợp lệ")
    if phone and not re.fullmatch(r"[0-9+()\\-\\s]{6,30}", phone):
        raise HTTPException(status_code=400, detail="Số điện thoại không hợp lệ")

    row = execute_returning(
        """
        UPDATE students
        SET email = %s,
            phone = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s::uuid
        RETURNING id, student_code, full_name, administrative_class, email, phone, status::text AS student_status
        """,
        (email, phone, str(ctx["student_id"])),
    )
    return rows_to_json_serializable([row])[0] if row else {}


@router.get("/face-images")
def student_face_images(ctx: Annotated[dict, Depends(get_student_context)]):
    rows = fetch_all(
        """
        SELECT id, image_path, image_type::text AS image_type, status::text AS status,
               is_used_for_training, uploaded_at, reviewed_at
        FROM student_face_images
        WHERE student_id = %s::uuid
        ORDER BY uploaded_at DESC
        """,
        (str(ctx["student_id"]),),
    )
    return rows_to_json_serializable(rows)


@router.post("/face-images")
async def upload_face_images(
    ctx: Annotated[dict, Depends(get_student_context)],
    files: list[UploadFile] = File(...),
):
    if not files:
        raise HTTPException(status_code=400, detail="Chưa chọn ảnh")

    settings = get_settings()
    upload_root = Path(settings.upload_root).resolve()
    student_code = ctx["student_code"]
    target_dir = (upload_root / "students" / str(student_code)).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    execute(
        "UPDATE students SET face_folder = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s::uuid",
        (str(target_dir), str(ctx["student_id"])),
    )

    created: list[dict] = []
    now = datetime.now(timezone.utc)
    allowed_ext = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

    for f in files[:10]:
        suffix = Path(f.filename or "").suffix.lower() or ".jpg"
        if suffix not in allowed_ext:
            raise HTTPException(status_code=400, detail=f"Định dạng không hỗ trợ: {suffix}")
        content = await f.read()
        if not content:
            continue
        if len(content) > 8 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File quá lớn (tối đa 8MB)")

        name = f"{now.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex}{suffix}"
        file_path = (target_dir / name).resolve()
        file_path.write_bytes(content)

        row = execute_returning(
            """
            INSERT INTO student_face_images (
                student_id, image_path, image_type, status,
                is_used_for_training, uploaded_by, uploaded_at, created_at, updated_at
            )
            VALUES (
                %s::uuid, %s, 'ORIGINAL'::face_image_type, 'PENDING'::face_image_status,
                FALSE, %s::uuid, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING id, image_path, image_type::text AS image_type, status::text AS status,
                      is_used_for_training, uploaded_at, reviewed_at
            """,
            (str(ctx["student_id"]), str(file_path), str(ctx["id"]), now),
        )
        if row:
            created.append(row)

    return rows_to_json_serializable(created)


@router.get("/attendance-history")
def student_attendance_history(
    ctx: Annotated[dict, Depends(get_student_context)],
    course_class_id: UUID | None = Query(None),
):
    if course_class_id:
        rows = fetch_all(
            """
            SELECT ar.id, ar.status::text AS status, ar.check_in_time, ar.check_out_time,
                   ar.similarity_score, ar.note,
                   cs.session_date, cs.start_time, cs.end_time,
                   cc.class_code, cc.class_name,
                   sub.subject_name
            FROM attendance_records ar
            JOIN class_sessions cs ON cs.id = ar.session_id
            JOIN course_classes cc ON cc.id = cs.course_class_id
            JOIN subjects sub ON sub.id = cc.subject_id
            WHERE ar.student_id = %s::uuid AND cc.id = %s::uuid
            ORDER BY cs.session_date DESC, cs.start_time DESC
            """,
            (str(ctx["student_id"]), str(course_class_id)),
        )
    else:
        rows = fetch_all(
            """
            SELECT ar.id, ar.status::text AS status, ar.check_in_time, ar.check_out_time,
                   ar.similarity_score, ar.note,
                   cs.session_date, cs.start_time, cs.end_time,
                   cc.class_code, cc.class_name,
                   sub.subject_name
            FROM attendance_records ar
            JOIN class_sessions cs ON cs.id = ar.session_id
            JOIN course_classes cc ON cc.id = cs.course_class_id
            JOIN subjects sub ON sub.id = cc.subject_id
            WHERE ar.student_id = %s::uuid
            ORDER BY cs.session_date DESC, cs.start_time DESC
            LIMIT 200
            """,
            (str(ctx["student_id"]),),
        )
    return rows_to_json_serializable(rows)


@router.get("/recheck-eligible-sessions")
def student_recheck_eligible_sessions(
    ctx: Annotated[dict, Depends(get_student_context)],
):
    rows = fetch_all(
        """
        SELECT cs.id AS session_id,
               cs.session_date,
               cs.start_time,
               cs.end_time,
               cc.class_code,
               cc.class_name,
               sub.subject_name,
               ar.id AS attendance_record_id,
               COALESCE(ar.status::text, 'ABSENT') AS attendance_status,
               req.id AS existing_request_id,
               req.status::text AS request_status
        FROM class_sessions cs
        JOIN course_classes cc ON cc.id = cs.course_class_id
        JOIN subjects sub ON sub.id = cc.subject_id
        JOIN course_class_students ccs
          ON ccs.course_class_id = cc.id
         AND ccs.student_id = %s::uuid
         AND ccs.status = 'ACTIVE'
        LEFT JOIN attendance_records ar
          ON ar.session_id = cs.id
         AND ar.student_id = %s::uuid
        LEFT JOIN attendance_recheck_requests req
          ON req.session_id = cs.id
         AND req.student_id = %s::uuid
         AND req.status = 'PENDING'::request_status
        WHERE cs.status IN ('FINISHED'::session_status, 'LOCKED'::session_status)
        ORDER BY cs.session_date DESC, cs.start_time DESC
        LIMIT 100
        """,
        (str(ctx["student_id"]), str(ctx["student_id"]), str(ctx["student_id"])),
    )
    return rows_to_json_serializable(rows)


@router.get("/recheck-requests")
def student_recheck_requests(
    ctx: Annotated[dict, Depends(get_student_context)],
):
    rows = fetch_all(
        """
        SELECT req.id, req.reason, req.status::text AS status,
               req.lecturer_response, req.created_at, req.processed_at,
               cs.session_date, cc.class_code, sub.subject_name
        FROM attendance_recheck_requests req
        JOIN class_sessions cs ON cs.id = req.session_id
        JOIN course_classes cc ON cc.id = cs.course_class_id
        JOIN subjects sub ON sub.id = cc.subject_id
        WHERE req.student_id = %s::uuid
        ORDER BY req.created_at DESC
        LIMIT 100
        """,
        (str(ctx["student_id"]),),
    )
    return rows_to_json_serializable(rows)


@router.post("/recheck-requests")
def create_student_recheck_request(
    body: CreateRecheckRequestBody,
    ctx: Annotated[dict, Depends(get_student_context)],
):
    owned_session = fetch_all(
        """
        SELECT cs.id, ar.id AS attendance_record_id
        FROM class_sessions cs
        JOIN course_classes cc ON cc.id = cs.course_class_id
        JOIN course_class_students ccs
          ON ccs.course_class_id = cc.id
         AND ccs.student_id = %s::uuid
         AND ccs.status = 'ACTIVE'
        LEFT JOIN attendance_records ar
          ON ar.session_id = cs.id
         AND ar.student_id = %s::uuid
        WHERE cs.id = %s::uuid
          AND cs.status IN ('FINISHED'::session_status, 'LOCKED'::session_status)
        LIMIT 1
        """,
        (str(ctx["student_id"]), str(ctx["student_id"]), str(body.session_id)),
    )
    if not owned_session:
        raise HTTPException(status_code=404, detail="Không tìm thấy buổi học hợp lệ để yêu cầu kiểm tra lại")

    existing = fetch_all(
        """
        SELECT id
        FROM attendance_recheck_requests
        WHERE session_id = %s::uuid
          AND student_id = %s::uuid
          AND status = 'PENDING'::request_status
        LIMIT 1
        """,
        (str(body.session_id), str(ctx["student_id"])),
    )
    if existing:
        raise HTTPException(status_code=400, detail="Bạn đã gửi yêu cầu đang chờ xử lý cho buổi này")

    row = execute_returning(
        """
        INSERT INTO attendance_recheck_requests (
            attendance_record_id, session_id, student_id, reason
        )
        VALUES (%s::uuid, %s::uuid, %s::uuid, %s)
        RETURNING id, attendance_record_id, session_id, student_id,
                  reason, status::text AS status, created_at
        """,
        (
            str(owned_session[0]["attendance_record_id"]) if owned_session[0]["attendance_record_id"] else None,
            str(body.session_id),
            str(ctx["student_id"]),
            body.reason.strip(),
        ),
    )
    return rows_to_json_serializable([row])[0]
