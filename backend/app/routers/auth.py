from datetime import datetime, timezone

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import execute, fetch_one
from app.deps import get_current_user
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str


class ChangePasswordBody(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=4)


@router.post("/login", response_model=LoginResponse)
def login(body: LoginBody):
    row = fetch_one(
        """
        SELECT id, username, password_hash, role::text AS role, status::text AS status
        FROM users
        WHERE username = %s
        """,
        (body.username.strip(),),
    )
    if not row or row.get("status") != "ACTIVE":
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu")

    if not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu")

    execute(
        "UPDATE users SET last_login_at = %s WHERE id = %s",
        (datetime.now(timezone.utc), str(row["id"])),
    )

    token = create_access_token(
        {
            "sub": str(row["id"]),
            "username": row["username"],
            "role": row["role"],
        }
    )
    return LoginResponse(
        access_token=token,
        role=row["role"],
        user_id=str(row["id"]),
    )


@router.post("/change-password")
def change_password(
    body: ChangePasswordBody,
    user: Annotated[dict, Depends(get_current_user)],
):
    row = fetch_one(
        """
        SELECT id, password_hash
        FROM users
        WHERE id = %s::uuid
        """,
        (str(user["id"]),),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
    if not verify_password(body.current_password, row["password_hash"]):
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="Mật khẩu mới phải khác mật khẩu hiện tại")

    execute(
        """
        UPDATE users
        SET password_hash = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s::uuid
        """,
        (hash_password(body.new_password), str(user["id"])),
    )
    return {"ok": True, "message": "Đổi mật khẩu thành công"}
