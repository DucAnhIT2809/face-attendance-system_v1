"""Shim: chạy `cd modelcore/Model_v2 && python -m face_pipeline student-db ...`."""
from __future__ import annotations

from face_pipeline.data.student_db_pg import main

if __name__ == "__main__":
    main()
