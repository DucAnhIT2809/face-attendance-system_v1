"""Shim — dùng package: `python -m face_pipeline detect ...` (chạy trong thư mục Model)."""
from __future__ import annotations

from face_pipeline.detect_tracking.yolo_webcam import main

if __name__ == "__main__":
    main()
