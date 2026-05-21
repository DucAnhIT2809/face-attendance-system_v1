"""Đường dẫn gốc dự án và thư mục Model — dùng chung cho toàn pipeline."""

from __future__ import annotations

from pathlib import Path

# Thư mục package: .../Model_v2/face_pipeline/
_PACKAGE_DIR = Path(__file__).resolve().parent
# Thư mục Model_v2 (chứa arcface_runs, script shim, weights tùy chọn)
MODEL_DIR = _PACKAGE_DIR.parent
# Root modelcore (cha của Model_v2)
REPO_ROOT = MODEL_DIR.parent

# File .pt hợp lệ thường > vài MB; file vài byte thường là lỗi tải (HTML "Not Found", v.v.).
_MIN_PT_BYTES = 1024


def is_plausible_weight_pt(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix.lower() != ".pt":
        return True
    try:
        return path.stat().st_size >= _MIN_PT_BYTES
    except OSError:
        return False


def detect_weight_search_dirs() -> tuple[Path, ...]:
    """Thứ tự tìm file .pt cho YOLO face (webcam / ArcFace crop)."""
    return (
        MODEL_DIR / "detect_tracking",
        _PACKAGE_DIR / "detect_tracking",
        MODEL_DIR,
        REPO_ROOT,
    )


def resolve_weight_file(name_or_path: str) -> Path:
    """Trả về đường dẫn tuyệt đối tới weight; thử nhiều thư mục nếu chỉ là tên file."""
    candidate = Path(name_or_path)
    if is_plausible_weight_pt(candidate):
        return candidate.resolve()
    for base in detect_weight_search_dirs():
        cand = base / name_or_path
        if is_plausible_weight_pt(cand):
            return cand.resolve()
    raise FileNotFoundError(
        f"Weight file not found (hoặc file .pt quá nhỏ / hỏng): {name_or_path}. "
        f"Đã thử các thư mục: {', '.join(str(b) for b in detect_weight_search_dirs())}"
    )


def resolve_under_repo(*parts: str) -> Path:
    """Đường dẫn tuyệt đối dưới REPO_ROOT (TrainingSelected, TrainingAugmented, ...)."""
    return (REPO_ROOT / Path(*parts)).resolve()
