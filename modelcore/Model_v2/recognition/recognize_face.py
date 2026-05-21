"""Shim — `python -m face_pipeline recognize ...`."""
from __future__ import annotations

from face_pipeline.recognition.recognize_face import main

if __name__ == "__main__":
    main()
