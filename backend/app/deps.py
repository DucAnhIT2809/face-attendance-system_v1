from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db import fetch_one
from app.security import decode_token

security = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> dict:
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thiếu hoặc sai định dạng Authorization Bearer",
        )
    try:
        payload = decode_token(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ hoặc đã hết hạn",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token thiếu subject")

    row = fetch_one(
        """
        SELECT id, username, role::text AS role, status::text AS status
        FROM users
        WHERE id = %s::uuid
        """,
        (str(user_id),),
    )
    if not row or row.get("status") != "ACTIVE":
        raise HTTPException(status_code=401, detail="Tài khoản không tồn tại hoặc bị khóa")
    return row


async def get_lecturer_context(
    user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    if user.get("role") != "LECTURER":
        raise HTTPException(status_code=403, detail="Chỉ giảng viên được truy cập")
    lec = fetch_one(
        """
        SELECT id AS lecturer_id, lecturer_code, full_name, email, phone, department
        FROM lecturers
        WHERE user_id = %s::uuid
        """,
        (str(user["id"]),),
    )
    if not lec:
        raise HTTPException(
            status_code=400,
            detail="Tài khoản chưa liên kết bản ghi lecturers — hãy chạy seed hoặc thêm hồ sơ",
        )
    return {**user, **lec}


async def get_student_context(
    user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    if user.get("role") != "STUDENT":
        raise HTTPException(status_code=403, detail="Chỉ sinh viên được truy cập")
    st = fetch_one(
        """
        SELECT id AS student_id, student_code, full_name, administrative_class,
               email, phone, status::text AS student_status, face_folder
        FROM students
        WHERE user_id = %s::uuid
        """,
        (str(user["id"]),),
    )
    if not st:
        raise HTTPException(
            status_code=400,
            detail="Tài khoản chưa liên kết bản ghi students — hãy chạy seed hoặc thêm hồ sơ",
        )
    return {**user, **st}
