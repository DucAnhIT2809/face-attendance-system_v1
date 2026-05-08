from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.db import execute, fetch_one
from app.security import hash_password

router = APIRouter(prefix="/auth", tags=["bootstrap"])


@router.post("/bootstrap-dev")
def bootstrap_dev_accounts():
    """
    Tạo / cập nhật gv01, sv01 (mật khẩu 1234) và bản ghi lecturer + student mẫu.
    Chỉ hoạt động khi FACE_ALLOW_BOOTSTRAP=1 trong backend/.env — nhớ tắt sau khi setup.
    """
    if not get_settings().face_allow_bootstrap:
        raise HTTPException(status_code=404, detail="Not found")

    pw_hash = hash_password("1234")

    for username, role in (("gv01", "LECTURER"), ("sv01", "STUDENT")):
        execute(
            """
            INSERT INTO users (username, password_hash, role, status)
            VALUES (%s, %s, %s::user_role, 'ACTIVE'::account_status)
            ON CONFLICT (username) DO UPDATE SET
                password_hash = EXCLUDED.password_hash,
                role = EXCLUDED.role,
                status = 'ACTIVE'::account_status
            """,
            (username, pw_hash, role),
        )

    execute(
        """
        INSERT INTO lecturers (user_id, lecturer_code, full_name, email, department)
        SELECT u.id, 'GV001', 'Giảng viên mẫu', 'gv01@school.edu', 'CNTT'
        FROM users u WHERE u.username = 'gv01'
        ON CONFLICT (user_id) DO NOTHING
        """
    )

    execute(
        """
        INSERT INTO students (user_id, student_code, full_name, administrative_class, email, status, face_folder)
        SELECT u.id, '20230001', 'Nguyễn Văn A', 'D21CQCN01-B', 'sv01@school.edu', 'ACTIVE'::student_status, NULL
        FROM users u WHERE u.username = 'sv01'
        ON CONFLICT (student_code) DO NOTHING
        """
    )

    execute(
        """
        UPDATE students st
        SET user_id = u.id
        FROM users u
        WHERE u.username = 'sv01' AND st.student_code = '20230001'
          AND (st.user_id IS DISTINCT FROM u.id)
        """
    )

    gv = fetch_one(
        "SELECT username FROM users WHERE username = %s",
        ("gv01",),
    )
    return {
        "ok": True,
        "gv01_ready": gv is not None,
        "hint": "Đăng nhập gv01 / 1234 (Giảng viên). Tắt FACE_ALLOW_BOOTSTRAP trong .env khi không cần.",
    }
