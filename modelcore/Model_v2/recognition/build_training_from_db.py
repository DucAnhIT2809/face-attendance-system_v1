"""Shim — `python -m face_pipeline build-training ...`."""
from __future__ import annotations

from face_pipeline.data.build_training_from_db import main

if __name__ == "__main__":
    main()
