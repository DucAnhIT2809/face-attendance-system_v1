from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings


@dataclass(frozen=True)
class StoredFile:
    uri: str
    key: str


def _join_url(base: str, key: str) -> str:
    return f"{base.rstrip('/')}/{key.lstrip('/')}"


def store_bytes(key: str, content: bytes, content_type: str | None = None) -> StoredFile:
    settings = get_settings()
    normalized_key = key.replace("\\", "/").lstrip("/")

    if settings.storage_backend.lower() == "s3":
        if not settings.s3_bucket:
            raise RuntimeError("S3_BUCKET is required when STORAGE_BACKEND=s3")
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("Install boto3 to use S3 storage") from exc

        s3_key = f"{settings.s3_prefix.strip('/')}/{normalized_key}" if settings.s3_prefix else normalized_key
        client = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
        )
        extra_args = {"ContentType": content_type} if content_type else {}
        client.put_object(Bucket=settings.s3_bucket, Key=s3_key, Body=content, **extra_args)
        uri = (
            _join_url(settings.storage_public_base_url, s3_key)
            if settings.storage_public_base_url
            else f"s3://{settings.s3_bucket}/{s3_key}"
        )
        return StoredFile(uri=uri, key=s3_key)

    upload_root = Path(settings.upload_root).resolve()
    target_path = (upload_root / normalized_key).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(content)
    return StoredFile(uri=str(target_path), key=normalized_key)
