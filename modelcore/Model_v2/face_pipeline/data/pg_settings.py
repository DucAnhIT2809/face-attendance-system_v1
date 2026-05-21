"""Tham số kết nối PostgreSQL mặc định (dùng chung cho track / student-db / build-training)."""

from __future__ import annotations

import os
from typing import Any

DEFAULT_PG_HOST = "localhost"
DEFAULT_PG_PORT = 5432
DEFAULT_PG_DBNAME = "face_attendance_db"
DEFAULT_PG_USER = "postgres"


def default_pg_password() -> str:
    return os.environ.get("FACE_ATTENDANCE_PG_PASSWORD", "1234")


def connect_pg(
    *,
    host: str = DEFAULT_PG_HOST,
    port: int = DEFAULT_PG_PORT,
    dbname: str = DEFAULT_PG_DBNAME,
    user: str = DEFAULT_PG_USER,
    password: str | None = None,
    connect_timeout: int = 10,
):
    """Kết nối PostgreSQL (timeout mặc định 10s)."""
    import psycopg2

    return psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=default_pg_password() if password is None else password,
        connect_timeout=connect_timeout,
    )


def connect_pg_from_args(ns: Any) -> Any:
    """Từ namespace argparse (--db-host, --db-port, ...)."""
    return connect_pg(
        host=getattr(ns, "db_host", DEFAULT_PG_HOST),
        port=int(getattr(ns, "db_port", DEFAULT_PG_PORT)),
        dbname=getattr(ns, "db_name", DEFAULT_PG_DBNAME),
        user=getattr(ns, "db_user", DEFAULT_PG_USER),
        password=getattr(ns, "db_password", None),
    )
