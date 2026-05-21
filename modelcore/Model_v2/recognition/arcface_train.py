"""Shim — `cd modelcore/Model_v2 && python -m face_pipeline arcface-train ...`."""
from __future__ import annotations

from face_pipeline.recognition.arcface_train import main

if __name__ == "__main__":
    main()
