"""Shim: chạy `cd modelcore/Model_v2 && python -m face_pipeline augment ...`."""
from __future__ import annotations

from face_pipeline.recognition.augment_face_folders import main

if __name__ == "__main__":
    main()
