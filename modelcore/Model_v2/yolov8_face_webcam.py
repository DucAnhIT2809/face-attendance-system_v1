"""Shim: chạy `cd modelcore/Model_v2 && python -m face_pipeline detect ...`."""
from __future__ import annotations

from face_pipeline.detect_tracking.yolo_webcam import main

if __name__ == "__main__":
    main()
