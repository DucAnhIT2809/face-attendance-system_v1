from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import UUID
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.db import execute, execute_returning, fetch_all, fetch_one, rows_to_json_serializable
from app.deps import get_student_context
from app.storage import store_bytes

router = APIRouter(prefix="/student", tags=["student"])


class CreateRecheckRequestBody(BaseModel):
    session_id: UUID
    reason: str = Field(min_length=3, max_length=1000)


class CreateCourseClassJoinRequestBody(BaseModel):
    course_class_id: UUID
    message: str | None = Field(default=None, max_length=500)


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

    student_code = ctx["student_code"]
    storage_prefix = f"students/{student_code}"

    execute(
        "UPDATE students SET face_folder = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s::uuid",
        (storage_prefix, str(ctx["student_id"])),
    )

    created: list[dict] = []
    upload_blobs: list[bytes] = []
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
        stored = store_bytes(
            key=f"{storage_prefix}/{name}",
            content=content,
            content_type=f.content_type,
        )

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
            (str(ctx["student_id"]), stored.uri, str(ctx["id"]), now),
        )
        if row:
            created.append(row)
            upload_blobs.append(content)

    created_json = rows_to_json_serializable(created)
    emb_meta: dict = {"ok": False, "skipped": True, "reason": "no_stored_images"}
    if upload_blobs and created:
        from app.embedding_incremental import merge_embeddings_after_face_upload

        emb_meta = merge_embeddings_after_face_upload(
            student_id=str(ctx["student_id"]),
            student_code=student_code,
            image_contents=upload_blobs,
            created_image_ids=[str(r["id"]) for r in created],
        )

    return {"created": created_json, "embedding_update": emb_meta}


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


@router.get("/course-classes/search")
def student_search_course_classes(
    ctx: Annotated[dict, Depends(get_student_context)],
    q: str = Query("", min_length=1, max_length=200),
    limit: int = Query(40, ge=1, le=100),
):
    pattern = f"%{q.strip()}%"
    sid = str(ctx["student_id"])
    rows = fetch_all(
        """
        SELECT cc.id, cc.class_code, cc.class_name, cc.semester::text AS semester,
               cc.school_year, cc.room,
               s.subject_code, s.subject_name,
               lec.full_name AS lecturer_name, lec.lecturer_code,
               (SELECT COUNT(*) FROM course_class_students ccs
                WHERE ccs.course_class_id = cc.id AND ccs.status = 'ACTIVE')::int AS student_count
        FROM course_classes cc
        JOIN subjects s ON s.id = cc.subject_id
        JOIN lecturers lec ON lec.id = cc.lecturer_id
        WHERE (
            cc.class_code ILIKE %s OR cc.class_name ILIKE %s
            OR s.subject_code ILIKE %s OR s.subject_name ILIKE %s
            OR lec.full_name ILIKE %s OR lec.lecturer_code ILIKE %s
            OR cc.school_year ILIKE %s OR cc.semester::text ILIKE %s
        )
        AND NOT EXISTS (
            SELECT 1 FROM course_class_students ccs
            WHERE ccs.course_class_id = cc.id
              AND ccs.student_id = %s::uuid
              AND ccs.status = 'ACTIVE'
        )
        AND NOT EXISTS (
            SELECT 1 FROM course_class_join_requests r2
            WHERE r2.course_class_id = cc.id
              AND r2.student_id = %s::uuid
              AND r2.status = 'PENDING'::request_status
        )
        ORDER BY cc.school_year DESC, cc.class_code
        LIMIT %s
        """,
        (
            pattern,
            pattern,
            pattern,
            pattern,
            pattern,
            pattern,
            pattern,
            pattern,
            sid,
            sid,
            limit,
        ),
    )
    return rows_to_json_serializable(rows)


@router.get("/course-class-join-requests")
def student_list_course_class_join_requests(
    ctx: Annotated[dict, Depends(get_student_context)],
):
    rows = fetch_all(
        """
        SELECT r.id, r.status::text AS status, r.message, r.lecturer_note,
               r.created_at, r.processed_at,
               cc.id AS course_class_id, cc.class_code, cc.class_name,
               s.subject_code, s.subject_name
        FROM course_class_join_requests r
        JOIN course_classes cc ON cc.id = r.course_class_id
        JOIN subjects s ON s.id = cc.subject_id
        WHERE r.student_id = %s::uuid
        ORDER BY r.created_at DESC
        LIMIT 100
        """,
        (str(ctx["student_id"]),),
    )
    return rows_to_json_serializable(rows)


@router.post("/course-class-join-requests")
def student_create_course_class_join_request(
    body: CreateCourseClassJoinRequestBody,
    ctx: Annotated[dict, Depends(get_student_context)],
):
    cc = fetch_one(
        "SELECT id FROM course_classes WHERE id = %s::uuid",
        (str(body.course_class_id),),
    )
    if not cc:
        raise HTTPException(status_code=404, detail="Không tìm thấy lớp học phần")

    active = fetch_one(
        """
        SELECT 1 AS ok FROM course_class_students
        WHERE course_class_id = %s::uuid AND student_id = %s::uuid AND status = 'ACTIVE'
        """,
        (str(body.course_class_id), str(ctx["student_id"])),
    )
    if active:
        raise HTTPException(status_code=400, detail="Bạn đã là thành viên lớp này")

    pending = fetch_one(
        """
        SELECT id FROM course_class_join_requests
        WHERE course_class_id = %s::uuid AND student_id = %s::uuid
          AND status = 'PENDING'::request_status
        LIMIT 1
        """,
        (str(body.course_class_id), str(ctx["student_id"])),
    )
    if pending:
        raise HTTPException(status_code=400, detail="Bạn đã có yêu cầu đang chờ duyệt cho lớp này")

    msg = (body.message or "").strip() or None
    row = execute_returning(
        """
        INSERT INTO course_class_join_requests (course_class_id, student_id, status, message)
        VALUES (%s::uuid, %s::uuid, 'PENDING'::request_status, %s)
        RETURNING id, status::text AS status, message, created_at
        """,
        (str(body.course_class_id), str(ctx["student_id"]), msg),
    )
    return rows_to_json_serializable([row])[0]


@router.delete("/course-class-join-requests/{request_id}")
def student_cancel_course_class_join_request(
    request_id: UUID,
    ctx: Annotated[dict, Depends(get_student_context)],
):
    row = execute_returning(
        """
        UPDATE course_class_join_requests
        SET status = 'CANCELLED'::request_status,
            updated_at = CURRENT_TIMESTAMP,
            processed_at = CURRENT_TIMESTAMP
        WHERE id = %s::uuid AND student_id = %s::uuid AND status = 'PENDING'::request_status
        RETURNING id, status::text AS status
        """,
        (str(request_id), str(ctx["student_id"])),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu đang chờ để hủy")
    return rows_to_json_serializable([row])[0]
