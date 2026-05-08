from contextlib import contextmanager
from typing import Any, Generator, Iterable, Optional
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor

from app.config import get_settings


@contextmanager
def get_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    settings = get_settings()
    conn = psycopg2.connect(settings.database_url)
    try:
        yield conn
    finally:
        conn.close()


def fetch_one(query: str, params: Optional[tuple] = None) -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
            return dict(row) if row else None


def fetch_all(query: str, params: Optional[tuple] = None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or ())
            return [dict(r) for r in cur.fetchall()]


def execute(query: str, params: Optional[tuple] = None) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
        conn.commit()


def execute_returning(query: str, params: Optional[tuple] = None) -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None


def rows_to_json_serializable(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        item: dict[str, Any] = {}
        for k, v in r.items():
            if isinstance(v, UUID):
                item[k] = str(v)
            elif hasattr(v, "isoformat"):
                item[k] = v.isoformat()
            else:
                item[k] = v
        out.append(item)
    return out
