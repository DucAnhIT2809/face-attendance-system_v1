"""Shim — dùng package: `python -m face_pipeline track ...`."""
from __future__ import annotations

from face_pipeline.detect_tracking.yolo_track import main

if __name__ == "__main__":
    main()
