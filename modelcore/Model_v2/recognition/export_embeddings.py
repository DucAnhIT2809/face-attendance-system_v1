"""Shim — `python -m face_pipeline export-embeddings ...`."""
from __future__ import annotations

from face_pipeline.recognition.export_embeddings import main

if __name__ == "__main__":
    main()
