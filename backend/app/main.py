from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import auth, bootstrap_dev, health, lecturer, recognition, student

settings = get_settings()

app = FastAPI(
    title="Face Attendance API",
    version="0.1.0",
    description="Backend kết nối PostgreSQL (schema face_attendance_db) và tích hợp modelcore/Model_v2 (ArcFace + YOLOv8s-face).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(bootstrap_dev.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(lecturer.router, prefix="/api")
app.include_router(student.router, prefix="/api")
app.include_router(recognition.router, prefix="/api")


@app.get("/")
def root():
    return {"service": "face-attendance-api", "docs": "/docs"}
