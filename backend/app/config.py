from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql://postgres:1234@localhost:5432/face_attendance_db"
    jwt_secret: str = "change-me-in-production-use-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    modelcore_root: Path | None = None
    arcface_checkpoint: Path | None = None
    face_embedding_db: Path | None = None
    modelcore_python: str = "python3"

    # Bật tạm (FACE_ALLOW_BOOTSTRAP=1) để POST /api/auth/bootstrap-dev — tắt khi xong đồ án
    face_allow_bootstrap: bool = False

    # Uploads (ảnh khuôn mặt sinh viên)
    upload_root: Path = Path("uploads")

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
