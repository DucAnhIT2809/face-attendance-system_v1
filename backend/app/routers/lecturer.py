from datetime import datetime, timezone
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db import execute, execute_returning, fetch_all, fetch_one, rows_to_json_serializable
from app.deps import get_lecturer_context

router = APIRouter(prefix="/lecturer", tags=["lecturer"])


class UpdateSessionBody(BaseModel):
    session_date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    room: Optional[str] = None
    status: Optional[str] = None
    attendance_mode: Optional[str] = None


class ProcessRecheckRequestBody(BaseModel):
    decision: str
    response: Optional[str] = None


class CreateCourseClassBody(BaseModel):
    class_code: str = Field(min_length=1, max_length=100)
    class_name: Optional[str] = Field(None, max_length=255)
    subject_code: str = Field(min_length=1, max_length=50)
    subject_name: str = Field(min_length=1, max_length=255)
    credits: int = Field(default=3, ge=0, le=30)
    semester: str = Field(min_length=1, max_length=20)
    school_year: str = Field(min_length=1, max_length=20)
    room: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None


class CourseClassJoinDecisionBody(BaseModel):
    decision: str
    lecturer_note: Optional[str] = Field(None, max_length=500)


@router.get("/me")
def lecturer_me(ctx: Annotated[dict, Depends(get_lecturer_context)]):
    return {
        "user_id": str(ctx["id"]),
        "username": ctx["username"],
        "lecturer_id": str(ctx["lecturer_id"]),
        "lecturer_code": ctx["lecturer_code"],
        "full_name": ctx["full_name"],
        "email": ctx["email"],
        "phone": ctx["phone"],
        "department": ctx["department"],
    }


@router.get("/dashboard/summary")
def lecturer_dashboard(ctx: Annotated[dict, Depends(get_lecturer_context)]):
    lid = ctx["lecturer_id"]
    classes = fetch_all(
        "SELECT COUNT(*)::int AS n FROM course_classes WHERE lecturer_id = %s::uuid",
        (str(lid),),
    )
    students = fetch_all(
        """
        SELECT COUNT(DISTINCT ccs.student_id)::int AS n
        FROM course_class_students ccs
        JOIN course_classes cc ON cc.id = ccs.course_class_id
        WHERE cc.lecturer_id = %s::uuid AND ccs.status = 'ACTIVE'
        """,
        (str(lid),),
    )
    sessions = fetch_all(
        """
        SELECT COUNT(*)::int AS n
        FROM class_sessions cs
        JOIN course_classes cc ON cc.id = cs.course_class_id
        WHERE cc.lecturer_id = %s::uuid
        """,
        (str(lid),),
    )
    return {
        "course_class_count": classes[0]["n"] if classes else 0,
        "managed_student_count": students[0]["n"] if students else 0,
        "session_count": sessions[0]["n"] if sessions else 0,
    }


@router.get("/dashboard/absences")
def lecturer_dashboard_absences(ctx: Annotated[dict, Depends(get_lecturer_context)]):
    rows = fetch_all(
        """
        SELECT cc.class_code,
               s.subject_name,
               cs.session_date,
               st.student_code,
               st.full_name
        FROM class_sessions cs
        JOIN course_classes cc ON cc.id = cs.course_class_id
        JOIN subjects s ON s.id = cc.subject_id
        JOIN course_class_students ccs
          ON ccs.course_class_id = cc.id
         AND ccs.status = 'ACTIVE'
        JOIN students st ON st.id = ccs.student_id
        LEFT JOIN attendance_records ar
          ON ar.session_id = cs.id
         AND ar.student_id = st.id
         AND ar.status = 'PRESENT'::attendance_status
        WHERE cc.lecturer_id = %s::uuid
          AND cs.status IN ('FINISHED'::session_status, 'LOCKED'::session_status)
          AND cs.session_date < CURRENT_DATE
          AND ar.id IS NULL
        ORDER BY cs.session_date DESC, cc.class_code, st.student_code
        LIMIT 200
        """,
        (str(ctx["lecturer_id"]),),
    )
    return rows_to_json_serializable(rows)


@router.get("/course-classes")
def list_course_classes(ctx: Annotated[dict, Depends(get_lecturer_context)]):
    rows = fetch_all(
        """
        SELECT cc.id, cc.class_code, cc.class_name, cc.semester::text AS semester,
               cc.school_year, cc.room,
               s.subject_code, s.subject_name,
               (SELECT COUNT(*) FROM course_class_students ccs
                WHERE ccs.course_class_id = cc.id AND ccs.status = 'ACTIVE')::int AS student_count
        FROM course_classes cc
        JOIN subjects s ON s.id = cc.subject_id
        WHERE cc.lecturer_id = %s::uuid
        ORDER BY cc.school_year DESC, cc.semester, cc.class_code
        """,
        (str(ctx["lecturer_id"]),),
    )
    return rows_to_json_serializable(rows)


@router.get("/students")
def list_students_for_class(
    ctx: Annotated[dict, Depends(get_lecturer_context)],
    course_class_id: UUID = Query(..., description="UUID lớp học phần"),
):
    rows = fetch_all(
        """
        SELECT st.id, st.student_code, st.full_name, st.administrative_class,
               st.email, st.phone, st.status::text AS student_status,
               ccs.status::text AS membership_status,
               (SELECT COUNT(*) FROM student_face_images sfi
                WHERE sfi.student_id = st.id)::int AS face_image_count
        FROM course_class_students ccs
        JOIN students st ON st.id = ccs.student_id
        JOIN course_classes cc ON cc.id = ccs.course_class_id
        WHERE cc.id = %s::uuid
          AND cc.lecturer_id = %s::uuid
          AND ccs.status = 'ACTIVE'
        ORDER BY st.student_code
        """,
        (str(course_class_id), str(ctx["lecturer_id"])),
    )
    return rows_to_json_serializable(rows)


@router.get("/sessions")
def list_sessions(
    ctx: Annotated[dict, Depends(get_lecturer_context)],
    course_class_id: Optional[UUID] = None,
):
    if course_class_id:
        rows = fetch_all(
            """
            SELECT cs.id, cs.session_code, cs.session_date, cs.start_time, cs.end_time,
                   cs.started_at, cs.finished_at,
                   cs.room, cs.status::text AS status, cs.attendance_mode::text AS attendance_mode,
                   cc.class_code, cc.class_name, s.subject_name
            FROM class_sessions cs
            JOIN course_classes cc ON cc.id = cs.course_class_id
            JOIN subjects s ON s.id = cc.subject_id
            WHERE cc.lecturer_id = %s::uuid AND cs.course_class_id = %s::uuid
            ORDER BY cs.session_date DESC, cs.start_time DESC
            """,
            (str(ctx["lecturer_id"]), str(course_class_id)),
        )
    else:
        rows = fetch_all(
            """
            SELECT cs.id, cs.session_code, cs.session_date, cs.start_time, cs.end_time,
                   cs.started_at, cs.finished_at,
                   cs.room, cs.status::text AS status, cs.attendance_mode::text AS attendance_mode,
                   cc.class_code, cc.class_name, s.subject_name
            FROM class_sessions cs
            JOIN course_classes cc ON cc.id = cs.course_class_id
            JOIN subjects s ON s.id = cc.subject_id
            WHERE cc.lecturer_id = %s::uuid
            ORDER BY cs.session_date DESC, cs.start_time DESC
            LIMIT 100
            """,
            (str(ctx["lecturer_id"]),),
        )
    return rows_to_json_serializable(rows)


@router.patch("/sessions/{session_id}")
def update_session(
    session_id: UUID,
    body: UpdateSessionBody,
    ctx: Annotated[dict, Depends(get_lecturer_context)],
):
    owned = fetch_one(
        """
        SELECT cs.id
        FROM class_sessions cs
        JOIN course_classes cc ON cc.id = cs.course_class_id
        WHERE cs.id = %s::uuid AND cc.lecturer_id = %s::uuid
        """,
        (str(session_id), str(ctx["lecturer_id"])),
    )
    if not owned:
        raise HTTPException(status_code=404, detail="Không tìm thấy buổi học hoặc không có quyền")

    row = execute_returning(
        """
        UPDATE class_sessions
        SET session_date = COALESCE(%s::date, session_date),
            start_time = COALESCE(%s::time, start_time),
            end_time = COALESCE(%s::time, end_time),
            room = %s,
            status = COALESCE(%s::session_status, status),
            attendance_mode = COALESCE(%s::attendance_mode, attendance_mode),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s::uuid
        RETURNING id, session_code, session_date, start_time, end_time,
                  started_at, finished_at,
                  room, status::text AS status, attendance_mode::text AS attendance_mode
        """,
        (
            body.session_date,
            body.start_time,
            body.end_time,
            body.room,
            body.status,
            body.attendance_mode,
            str(session_id),
        ),
    )
    if not row:
        raise HTTPException(status_code=500, detail="Không cập nhật được buổi học")

    meta = fetch_one(
        """
        SELECT cc.class_code, cc.class_name, s.subject_name
        FROM class_sessions cs
        JOIN course_classes cc ON cc.id = cs.course_class_id
        JOIN subjects s ON s.id = cc.subject_id
        WHERE cs.id = %s::uuid
        """,
        (str(session_id),),
    )
    row.update(meta or {})
    return rows_to_json_serializable([row])[0]


@router.post("/sessions/live-today")
def start_live_attendance_today(
    ctx: Annotated[dict, Depends(get_lecturer_context)],
    class_code: str = Query(..., description="Mã lớp học phần"),
):
    today = datetime.now().date()
    course_class = fetch_one(
        """
        SELECT cc.id, cc.class_code, cc.class_name, cc.room, s.subject_name
        FROM course_classes cc
        JOIN subjects s ON s.id = cc.subject_id
        WHERE cc.lecturer_id = %s::uuid AND cc.class_code = %s
        """,
        (str(ctx["lecturer_id"]), class_code),
    )
    if not course_class:
        raise HTTPException(status_code=404, detail="Không tìm thấy lớp học phần hoặc không có quyền")

    existing = fetch_one(
        """
        SELECT cs.id, cs.session_code, cs.session_date, cs.start_time, cs.end_time,
               cs.started_at, cs.finished_at,
               cs.room, cs.status::text AS status, cs.attendance_mode::text AS attendance_mode,
               cc.class_code, cc.class_name, s.subject_name
        FROM class_sessions cs
        JOIN course_classes cc ON cc.id = cs.course_class_id
        JOIN subjects s ON s.id = cc.subject_id
        WHERE cs.course_class_id = %s::uuid AND cs.session_date = %s::date
        ORDER BY cs.created_at DESC
        LIMIT 1
        """,
        (str(course_class["id"]), today),
    )

    if existing:
        if existing["status"] == "LOCKED":
            raise HTTPException(status_code=400, detail="Buổi điểm danh hôm nay đã khóa")
        row = execute_returning(
            """
            UPDATE class_sessions
            SET status = 'RUNNING'::session_status,
                started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s::uuid
            RETURNING id, session_code, session_date, start_time, end_time,
                      started_at, finished_at,
                      room, status::text AS status, attendance_mode::text AS attendance_mode
            """,
            (str(existing["id"]),),
        )
    else:
        session_code = f"LIVE-{today:%Y%m%d}-{course_class['class_code']}"
        row = execute_returning(
            """
            INSERT INTO class_sessions (
                course_class_id, session_code, session_date, start_time, end_time, room,
                attendance_mode, status, created_by, started_at
            )
            VALUES (
                %s::uuid, %s, %s::date, TIME '00:00', TIME '23:59', %s,
                'CONTINUOUS'::attendance_mode, 'RUNNING'::session_status,
                %s::uuid, CURRENT_TIMESTAMP
            )
            RETURNING id, session_code, session_date, start_time, end_time,
                      started_at, finished_at,
                      room, status::text AS status, attendance_mode::text AS attendance_mode
            """,
            (
                str(course_class["id"]),
                session_code,
                today,
                course_class.get("room"),
                str(ctx["id"]),
            ),
        )

    if not row:
        raise HTTPException(status_code=500, detail="Không tạo được buổi điểm danh hôm nay")

    row["class_code"] = course_class["class_code"]
    row["class_name"] = course_class["class_name"]
    row["subject_name"] = course_class["subject_name"]
    return rows_to_json_serializable([row])[0]


@router.post("/sessions/{session_id}/stop-attendance")
def stop_attendance_session(
    session_id: UUID,
    ctx: Annotated[dict, Depends(get_lecturer_context)],
):
    """
    Giảng viên tắt điểm danh:
    - Đóng buổi học (status = FINISHED)
    - Chốt check_out_time = last_seen_at (nếu có), fallback finished_at
    """
    owned = fetch_one(
        """
        SELECT cs.id
        FROM class_sessions cs
        JOIN course_classes cc ON cc.id = cs.course_class_id
        WHERE cs.id = %s::uuid AND cc.lecturer_id = %s::uuid
        """,
        (str(session_id), str(ctx["lecturer_id"])),
    )
    if not owned:
        raise HTTPException(status_code=404, detail="Không tìm thấy buổi học hoặc không có quyền")

    finished_at = datetime.now(timezone.utc)
    execute(
        """
        UPDATE class_sessions
        SET status = 'FINISHED'::session_status,
            finished_at = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s::uuid
        """,
        (finished_at, str(session_id)),
    )

    execute(
        """
        UPDATE attendance_records
        SET check_out_time = COALESCE(last_seen_at, %s),
            updated_at = CURRENT_TIMESTAMP
        WHERE session_id = %s::uuid
          AND status = 'PRESENT'::attendance_status
        """,
        (finished_at, str(session_id)),
    )

    return {
        "ok": True,
        "session_id": str(session_id),
        "finished_at": finished_at.isoformat(),
        "message": "Đã tắt điểm danh và chốt thời gian cuối cùng xuất hiện.",
    }


@router.get("/attendance-records")
def list_attendance_for_session(
    ctx: Annotated[dict, Depends(get_lecturer_context)],
    session_id: UUID = Query(...),
):
    rows = fetch_all(
        """
        SELECT ar.id, ar.student_id, st.student_code, st.full_name,
               ar.status::text AS status, ar.source::text AS source,
               ar.check_in_time, ar.check_out_time, ar.similarity_score, ar.recognition_confidence
        FROM attendance_records ar
        JOIN students st ON st.id = ar.student_id
        JOIN class_sessions cs ON cs.id = ar.session_id
        JOIN course_classes cc ON cc.id = cs.course_class_id
        WHERE ar.session_id = %s::uuid AND cc.lecturer_id = %s::uuid
        ORDER BY st.student_code
        """,
        (str(session_id), str(ctx["lecturer_id"])),
    )
    return rows_to_json_serializable(rows)


@router.get("/attendance-results")
def attendance_results_filtered(
    ctx: Annotated[dict, Depends(get_lecturer_context)],
    class_code: Optional[str] = Query(None, description="Lọc theo mã lớp học phần"),
    session_date: Optional[str] = Query(None, description="Lọc theo ngày YYYY-MM-DD"),
):
    query = """
        SELECT ar.id, st.student_code, st.full_name,
               cc.class_code, cc.class_name,
               cs.session_date,
               ar.status::text AS status, ar.source::text AS source,
               ar.check_in_time, ar.last_seen_at, ar.check_out_time,
               ar.total_seen_seconds, ar.similarity_score, ar.recognition_confidence
        FROM attendance_records ar
        JOIN students st ON st.id = ar.student_id
        JOIN class_sessions cs ON cs.id = ar.session_id
        JOIN course_classes cc ON cc.id = cs.course_class_id
        WHERE cc.lecturer_id = %s::uuid
    """
    params: list = [str(ctx["lecturer_id"])]
    if class_code:
        query += " AND cc.class_code = %s"
        params.append(class_code)
    if session_date:
        query += " AND cs.session_date = %s::date"
        params.append(session_date)
    query += " ORDER BY cs.session_date DESC, cc.class_code, st.student_code"
    rows = fetch_all(query, tuple(params))
    return rows_to_json_serializable(rows)


@router.get("/reports/attendance")
def attendance_report(
    ctx: Annotated[dict, Depends(get_lecturer_context)],
    class_code: str = Query(..., description="Mã lớp học phần cần xuất báo cáo"),
    from_date: Optional[str] = Query(None, description="Từ ngày YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="Đến ngày YYYY-MM-DD"),
):
    class_info = fetch_one(
        """
        SELECT cc.id, cc.class_code, cc.class_name, cc.semester::text AS semester,
               cc.school_year, sub.subject_code, sub.subject_name,
               (SELECT COUNT(*) FROM course_class_students ccs
                WHERE ccs.course_class_id = cc.id AND ccs.status = 'ACTIVE')::int AS student_count
        FROM course_classes cc
        JOIN subjects sub ON sub.id = cc.subject_id
        WHERE cc.lecturer_id = %s::uuid AND cc.class_code = %s
        """,
        (str(ctx["lecturer_id"]), class_code),
    )
    if not class_info:
        raise HTTPException(status_code=404, detail="Không tìm thấy lớp học phần hoặc không có quyền")

    filters = ["cs.course_class_id = %s::uuid"]
    params: list = [str(class_info["id"])]
    if from_date:
        filters.append("cs.session_date >= %s::date")
        params.append(from_date)
    if to_date:
        filters.append("cs.session_date <= %s::date")
        params.append(to_date)
    session_where = " AND ".join(filters)

    rows = fetch_all(
        f"""
        WITH selected_sessions AS (
            SELECT cs.id, cs.session_code, cs.session_date, cs.start_time, cs.end_time,
                   cs.status::text AS session_status
            FROM class_sessions cs
            WHERE {session_where}
        ),
        active_students AS (
            SELECT st.id, st.student_code, st.full_name, st.administrative_class
            FROM course_class_students ccs
            JOIN students st ON st.id = ccs.student_id
            WHERE ccs.course_class_id = %s::uuid
              AND ccs.status = 'ACTIVE'
              AND st.status = 'ACTIVE'
        )
        SELECT ss.session_code, ss.session_date, ss.start_time, ss.end_time, ss.session_status,
               ast.student_code, ast.full_name, ast.administrative_class,
               COALESCE(ar.status::text, 'ABSENT') AS attendance_status,
               ar.source::text AS source,
               ar.check_in_time, ar.last_seen_at, ar.check_out_time,
               ar.total_seen_seconds, ar.similarity_score, ar.recognition_confidence,
               ar.note
        FROM selected_sessions ss
        CROSS JOIN active_students ast
        LEFT JOIN attendance_records ar
          ON ar.session_id = ss.id
         AND ar.student_id = ast.id
        ORDER BY ss.session_date DESC, ss.start_time DESC, ast.student_code
        """,
        tuple(params + [str(class_info["id"])]),
    )

    summary_rows = fetch_all(
        f"""
        WITH selected_sessions AS (
            SELECT cs.id
            FROM class_sessions cs
            WHERE {session_where}
        ),
        active_students AS (
            SELECT st.id
            FROM course_class_students ccs
            JOIN students st ON st.id = ccs.student_id
            WHERE ccs.course_class_id = %s::uuid
              AND ccs.status = 'ACTIVE'
              AND st.status = 'ACTIVE'
        ),
        matrix AS (
            SELECT COALESCE(ar.status::text, 'ABSENT') AS attendance_status
            FROM selected_sessions ss
            CROSS JOIN active_students ast
            LEFT JOIN attendance_records ar
              ON ar.session_id = ss.id
             AND ar.student_id = ast.id
        )
        SELECT attendance_status, COUNT(*)::int AS count
        FROM matrix
        GROUP BY attendance_status
        """,
        tuple(params + [str(class_info["id"])]),
    )

    session_count = fetch_one(
        f"SELECT COUNT(*)::int AS count FROM class_sessions cs WHERE {session_where}",
        tuple(params),
    )
    summary = {
        "session_count": session_count["count"] if session_count else 0,
        "student_count": class_info["student_count"],
        "total_rows": len(rows),
        "by_status": {r["attendance_status"]: r["count"] for r in summary_rows},
    }

    return {
        "class_info": rows_to_json_serializable([class_info])[0],
        "summary": summary,
        "rows": rows_to_json_serializable(rows),
    }


@router.get("/recheck-requests")
def lecturer_recheck_requests(
    ctx: Annotated[dict, Depends(get_lecturer_context)],
):
    rows = fetch_all(
        """
        SELECT req.id, req.reason, req.status::text AS status,
               req.lecturer_response, req.created_at, req.processed_at,
               st.student_code, st.full_name,
               cs.session_date, cc.class_code, sub.subject_name,
               ar.status::text AS attendance_status
        FROM attendance_recheck_requests req
        JOIN students st ON st.id = req.student_id
        JOIN class_sessions cs ON cs.id = req.session_id
        JOIN course_classes cc ON cc.id = cs.course_class_id
        JOIN subjects sub ON sub.id = cc.subject_id
        LEFT JOIN attendance_records ar ON ar.id = req.attendance_record_id
        WHERE cc.lecturer_id = %s::uuid
        ORDER BY
            CASE req.status
                WHEN 'PENDING' THEN 0
                WHEN 'APPROVED' THEN 1
                WHEN 'REJECTED' THEN 2
                ELSE 3
            END,
            req.created_at DESC
        LIMIT 200
        """,
        (str(ctx["lecturer_id"]),),
    )
    return rows_to_json_serializable(rows)


@router.post("/recheck-requests/{request_id}/process")
def process_lecturer_recheck_request(
    request_id: UUID,
    body: ProcessRecheckRequestBody,
    ctx: Annotated[dict, Depends(get_lecturer_context)],
):
    decision = body.decision.upper().strip()
    if decision not in {"APPROVED", "REJECTED"}:
        raise HTTPException(status_code=400, detail="decision phải là APPROVED hoặc REJECTED")

    req = fetch_one(
        """
        SELECT req.id, req.session_id, req.student_id, req.status::text AS status,
               cc.lecturer_id
        FROM attendance_recheck_requests req
        JOIN class_sessions cs ON cs.id = req.session_id
        JOIN course_classes cc ON cc.id = cs.course_class_id
        WHERE req.id = %s::uuid AND cc.lecturer_id = %s::uuid
        """,
        (str(request_id), str(ctx["lecturer_id"])),
    )
    if not req:
        raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu hoặc không có quyền")
    if req["status"] != "PENDING":
        raise HTTPException(status_code=400, detail="Yêu cầu này đã được xử lý")

    attendance_record_id = None
    if decision == "APPROVED":
        record = execute_returning(
            """
            INSERT INTO attendance_records (
                session_id, student_id, status, source, check_in_time,
                note, is_manually_modified
            )
            VALUES (
                %s::uuid, %s::uuid, 'PRESENT'::attendance_status,
                'REQUEST_APPROVED'::attendance_source, CURRENT_TIMESTAMP,
                %s, TRUE
            )
            ON CONFLICT (session_id, student_id) DO UPDATE SET
                status = 'PRESENT'::attendance_status,
                source = 'REQUEST_APPROVED'::attendance_source,
                check_in_time = COALESCE(attendance_records.check_in_time, CURRENT_TIMESTAMP),
                note = EXCLUDED.note,
                is_manually_modified = TRUE,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (
                str(req["session_id"]),
                str(req["student_id"]),
                body.response or "Giảng viên đã chấp nhận yêu cầu kiểm tra lại.",
            ),
        )
        attendance_record_id = str(record["id"]) if record else None

    row = execute_returning(
        """
        UPDATE attendance_recheck_requests
        SET status = %s::request_status,
            lecturer_response = %s,
            attendance_record_id = COALESCE(%s::uuid, attendance_record_id),
            processed_by = %s::uuid,
            processed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s::uuid
        RETURNING id, status::text AS status, lecturer_response, processed_at
        """,
        (
            decision,
            body.response or ("Đã chấp nhận yêu cầu." if decision == "APPROVED" else "Đã từ chối yêu cầu."),
            attendance_record_id,
            str(ctx["id"]),
            str(request_id),
        ),
    )
    return rows_to_json_serializable([row])[0]


_SEMESTERS = {"HK1", "HK2", "HK_HE"}


@router.post("/course-classes")
def create_course_class(
    body: CreateCourseClassBody,
    ctx: Annotated[dict, Depends(get_lecturer_context)],
):
    sem = body.semester.strip().upper()
    if sem not in _SEMESTERS:
        raise HTTPException(
            status_code=400,
            detail=f"Học kỳ không hợp lệ: chọn một trong {', '.join(sorted(_SEMESTERS))}",
        )

    dup = fetch_one(
        """
        SELECT id FROM course_classes
        WHERE class_code = %s AND semester = %s::semester_type AND school_year = %s
        """,
        (body.class_code.strip(), sem, body.school_year.strip()),
    )
    if dup:
        raise HTTPException(status_code=409, detail="Đã tồn tại lớp học phần với cùng mã lớp, học kỳ và năm học")

    code = body.subject_code.strip()
    sub = fetch_one(
        "SELECT id FROM subjects WHERE UPPER(TRIM(subject_code)) = UPPER(TRIM(%s))",
        (code,),
    )
    if not sub:
        sub = execute_returning(
            """
            INSERT INTO subjects (subject_code, subject_name, credits)
            VALUES (TRIM(%s), %s, %s)
            RETURNING id
            """,
            (code, body.subject_name.strip(), body.credits),
        )
    if not sub:
        raise HTTPException(status_code=500, detail="Không tạo được học phần")

    cn = (body.class_name or "").strip() or None
    row = execute_returning(
        """
        INSERT INTO course_classes (
            class_code, class_name, subject_id, lecturer_id, semester, school_year, room, description
        )
        VALUES (
            TRIM(%s), %s, %s::uuid, %s::uuid, %s::semester_type, TRIM(%s), %s, %s
        )
        RETURNING id, class_code, class_name, semester::text AS semester, school_year, room, description
        """,
        (
            body.class_code,
            cn,
            str(sub["id"]),
            str(ctx["lecturer_id"]),
            sem,
            body.school_year.strip(),
            (body.room or "").strip() or None,
            (body.description or "").strip() or None,
        ),
    )
    if not row:
        raise HTTPException(status_code=500, detail="Không tạo được lớp học phần")

    meta = fetch_one(
        """
        SELECT s.subject_code, s.subject_name
        FROM course_classes cc
        JOIN subjects s ON s.id = cc.subject_id
        WHERE cc.id = %s::uuid
        """,
        (str(row["id"]),),
    )
    row.update(meta or {})
    return rows_to_json_serializable([row])[0]


@router.get("/course-class-join-requests")
def list_course_class_join_requests(
    ctx: Annotated[dict, Depends(get_lecturer_context)],
    status_filter: Optional[str] = Query(None, alias="status", description="PENDING, APPROVED, REJECTED, CANCELLED"),
):
    params: list = [str(ctx["lecturer_id"])]
    extra = ""
    if status_filter:
        extra = " AND r.status::text = %s"
        params.append(status_filter.strip().upper())

    rows = fetch_all(
        f"""
        SELECT r.id, r.status::text AS status, r.message, r.lecturer_note,
               r.created_at, r.processed_at,
               cc.id AS course_class_id, cc.class_code, cc.class_name,
               s.subject_code, s.subject_name,
               st.id AS student_id, st.student_code, st.full_name, st.administrative_class
        FROM course_class_join_requests r
        JOIN course_classes cc ON cc.id = r.course_class_id
        JOIN subjects s ON s.id = cc.subject_id
        JOIN students st ON st.id = r.student_id
        WHERE cc.lecturer_id = %s::uuid
        {extra}
        ORDER BY
            CASE r.status::text
                WHEN 'PENDING' THEN 0
                WHEN 'APPROVED' THEN 1
                WHEN 'REJECTED' THEN 2
                ELSE 3
            END,
            r.created_at DESC
        LIMIT 300
        """,
        tuple(params),
    )
    return rows_to_json_serializable(rows)


@router.post("/course-class-join-requests/{request_id}/decision")
def decide_course_class_join_request(
    request_id: UUID,
    body: CourseClassJoinDecisionBody,
    ctx: Annotated[dict, Depends(get_lecturer_context)],
):
    decision = body.decision.strip().upper()
    if decision not in {"APPROVED", "REJECTED"}:
        raise HTTPException(status_code=400, detail="decision phải là APPROVED hoặc REJECTED")

    req = fetch_one(
        """
        SELECT r.id, r.course_class_id, r.student_id, r.status::text AS status
        FROM course_class_join_requests r
        JOIN course_classes cc ON cc.id = r.course_class_id
        WHERE r.id = %s::uuid AND cc.lecturer_id = %s::uuid
        """,
        (str(request_id), str(ctx["lecturer_id"])),
    )
    if not req:
        raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu hoặc không có quyền")
    if req["status"] != "PENDING":
        raise HTTPException(status_code=400, detail="Yêu cầu này đã được xử lý")

    note = (body.lecturer_note or "").strip() or None

    if decision == "APPROVED":
        execute(
            """
            INSERT INTO course_class_students (course_class_id, student_id, status, joined_at, removed_at)
            VALUES (%s::uuid, %s::uuid, 'ACTIVE'::class_member_status, CURRENT_TIMESTAMP, NULL)
            ON CONFLICT (course_class_id, student_id) DO UPDATE SET
                status = 'ACTIVE'::class_member_status,
                joined_at = CURRENT_TIMESTAMP,
                removed_at = NULL
            """,
            (str(req["course_class_id"]), str(req["student_id"])),
        )

    row = execute_returning(
        """
        UPDATE course_class_join_requests
        SET status = %s::request_status,
            lecturer_note = %s,
            processed_by = %s::uuid,
            processed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s::uuid
        RETURNING id, status::text AS status, lecturer_note, processed_at
        """,
        (decision, note, str(ctx["id"]), str(request_id)),
    )
    return rows_to_json_serializable([row])[0] if row else {}
