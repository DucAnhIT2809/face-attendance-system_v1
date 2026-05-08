from fastapi import APIRouter

from app.db import fetch_one

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/db")
def health_db():
    row = fetch_one("SELECT 1 AS ok;")
    return {"status": "ok" if row and row.get("ok") == 1 else "error", "db": row}
