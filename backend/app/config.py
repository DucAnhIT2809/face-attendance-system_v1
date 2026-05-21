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
    # Thư mục con dưới MODELCORE_ROOT chứa package face_pipeline (mặc định Model_v2)
    modelcore_model_dir: str = "Model_v2"
    arcface_checkpoint: Path | None = None
    face_embedding_db: Path | None = None
    modelcore_python: str = "python3"
    class_embedding_root: Path = Path("modelcore/Model_v2/arcface_runs/classes")

    # Bật tạm (FACE_ALLOW_BOOTSTRAP=1) để POST /api/auth/bootstrap-dev — tắt khi xong đồ án
    face_allow_bootstrap: bool = False

    # Uploads (ảnh khuôn mặt sinh viên)
    upload_root: Path = Path("uploads")
    storage_backend: str = "local"
    storage_public_base_url: str | None = None
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_prefix: str = "face-attendance"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
