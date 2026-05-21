-- =========================================================
-- DATABASE: Face Attendance System
-- PostgreSQL Schema (Production-friendly baseline)
-- =========================================================

-- Optional (run separately):
-- CREATE DATABASE face_attendance_db;
-- \c face_attendance_db

-- =========================================================
-- 1. EXTENSIONS
-- =========================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =========================================================
-- 2. ENUM TYPES
-- =========================================================
DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('LECTURER', 'STUDENT');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE account_status AS ENUM ('ACTIVE', 'INACTIVE', 'LOCKED');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE student_status AS ENUM ('ACTIVE', 'INACTIVE', 'REMOVED');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE face_image_type AS ENUM ('ORIGINAL', 'CROPPED', 'AUGMENTED');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE face_image_status AS ENUM ('PENDING', 'VALID', 'INVALID');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE semester_type AS ENUM ('HK1', 'HK2', 'HK_HE');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE class_member_status AS ENUM ('ACTIVE', 'REMOVED');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE attendance_mode AS ENUM ('FIXED_TIME_WINDOW', 'CONTINUOUS', 'HYBRID');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE session_status AS ENUM ('NOT_STARTED', 'RUNNING', 'FINISHED', 'LOCKED');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE attendance_status AS ENUM ('PRESENT', 'ABSENT', 'LATE', 'EXCUSED', 'INCOMPLETE', 'UNKNOWN');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE attendance_source AS ENUM ('FACE_RECOGNITION', 'MANUAL', 'REQUEST_APPROVED');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE request_status AS ENUM ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE notification_type AS ENUM (
        'FACE_IMAGE_APPROVED',
        'FACE_IMAGE_REJECTED',
        'ATTENDANCE_UPDATED',
        'RECHECK_REQUEST',
        'SYSTEM'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

-- =========================================================
-- 3. COMMON FUNCTIONS
-- =========================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =========================================================
-- 4. USERS / ACCOUNTS
-- =========================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role user_role NOT NULL,
    status account_status NOT NULL DEFAULT 'ACTIVE',
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =========================================================
-- 5. LECTURERS
-- =========================================================
CREATE TABLE IF NOT EXISTS lecturers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lecturer_code VARCHAR(50) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(30),
    department VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trg_lecturers_updated_at
BEFORE UPDATE ON lecturers
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =========================================================
-- 6. STUDENTS
-- =========================================================
CREATE TABLE IF NOT EXISTS students (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE REFERENCES users(id) ON DELETE SET NULL,
    student_code VARCHAR(50) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    administrative_class VARCHAR(100),
    email VARCHAR(255),
    phone VARCHAR(30),
    status student_status NOT NULL DEFAULT 'ACTIVE',
    face_folder TEXT,
    need_retrain BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trg_students_updated_at
BEFORE UPDATE ON students
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =========================================================
-- 7. SUBJECTS
-- =========================================================
CREATE TABLE IF NOT EXISTS subjects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_code VARCHAR(50) UNIQUE NOT NULL,
    subject_name VARCHAR(255) NOT NULL,
    credits INTEGER NOT NULL DEFAULT 0 CHECK (credits >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trg_subjects_updated_at
BEFORE UPDATE ON subjects
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =========================================================
-- 8. COURSE CLASSES
-- =========================================================
CREATE TABLE IF NOT EXISTS course_classes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    class_code VARCHAR(100) NOT NULL,
    class_name VARCHAR(255),
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE RESTRICT,
    lecturer_id UUID NOT NULL REFERENCES lecturers(id) ON DELETE RESTRICT,
    semester semester_type NOT NULL,
    school_year VARCHAR(20) NOT NULL,
    room VARCHAR(100),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(class_code, semester, school_year)
);

CREATE TRIGGER trg_course_classes_updated_at
BEFORE UPDATE ON course_classes
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =========================================================
-- 9. COURSE CLASS MEMBERS
-- =========================================================
CREATE TABLE IF NOT EXISTS course_class_students (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_class_id UUID NOT NULL REFERENCES course_classes(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    status class_member_status NOT NULL DEFAULT 'ACTIVE',
    joined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    removed_at TIMESTAMPTZ,
    UNIQUE(course_class_id, student_id)
);

-- =========================================================
-- 9b. COURSE CLASS JOIN REQUESTS (sinh viên xin tham gia — GV duyệt)
-- =========================================================
CREATE TABLE IF NOT EXISTS course_class_join_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_class_id UUID NOT NULL REFERENCES course_classes(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    status request_status NOT NULL DEFAULT 'PENDING',
    message TEXT,
    lecturer_note TEXT,
    processed_at TIMESTAMPTZ,
    processed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trg_course_class_join_requests_updated_at
BEFORE UPDATE ON course_class_join_requests
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =========================================================
-- 10. STUDENT FACE IMAGES
-- =========================================================
CREATE TABLE IF NOT EXISTS student_face_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    image_path TEXT NOT NULL,
    image_type face_image_type NOT NULL DEFAULT 'ORIGINAL',
    status face_image_status NOT NULL DEFAULT 'PENDING',
    is_used_for_training BOOLEAN NOT NULL DEFAULT FALSE,
    uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    review_note TEXT,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trg_student_face_images_updated_at
BEFORE UPDATE ON student_face_images
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =========================================================
-- 11. FACE EMBEDDINGS
-- =========================================================
CREATE TABLE IF NOT EXISTS face_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    embedding_json JSONB,
    embedding_path TEXT,
    model_name VARCHAR(100) NOT NULL DEFAULT 'ArcFace',
    model_version VARCHAR(100),
    image_source_id UUID REFERENCES student_face_images(id) ON DELETE SET NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (embedding_json IS NOT NULL OR embedding_path IS NOT NULL)
);

-- =========================================================
-- 12. TRAINING RUNS
-- =========================================================
CREATE TABLE IF NOT EXISTS training_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name VARCHAR(100) NOT NULL DEFAULT 'ArcFace',
    model_version VARCHAR(100),
    training_dir TEXT,
    augmented_dir TEXT,
    checkpoint_path TEXT,
    num_students INTEGER NOT NULL DEFAULT 0 CHECK (num_students >= 0),
    num_images INTEGER NOT NULL DEFAULT 0 CHECK (num_images >= 0),
    epochs INTEGER CHECK (epochs IS NULL OR epochs > 0),
    batch_size INTEGER CHECK (batch_size IS NULL OR batch_size > 0),
    learning_rate NUMERIC(12, 8),
    train_loss NUMERIC(12, 6),
    train_accuracy NUMERIC(12, 6),
    val_loss NUMERIC(12, 6),
    val_accuracy NUMERIC(12, 6),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================
-- 13. CLASS SESSIONS
-- =========================================================
CREATE TABLE IF NOT EXISTS class_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_class_id UUID NOT NULL REFERENCES course_classes(id) ON DELETE CASCADE,
    session_code VARCHAR(100) UNIQUE,
    session_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    room VARCHAR(100),
    attendance_mode attendance_mode NOT NULL DEFAULT 'HYBRID',
    status session_status NOT NULL DEFAULT 'NOT_STARTED',
    fixed_window_minutes INTEGER NOT NULL DEFAULT 10 CHECK (fixed_window_minutes >= 0),
    late_after_minutes INTEGER NOT NULL DEFAULT 10 CHECK (late_after_minutes >= 0),
    minimum_presence_minutes INTEGER NOT NULL DEFAULT 0 CHECK (minimum_presence_minutes >= 0),
    required_presence_ratio NUMERIC(5, 2) NOT NULL DEFAULT 80.00 CHECK (required_presence_ratio >= 0 AND required_presence_ratio <= 100),
    note TEXT,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    locked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (end_time > start_time)
);

CREATE TRIGGER trg_class_sessions_updated_at
BEFORE UPDATE ON class_sessions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =========================================================
-- 14. ATTENDANCE RECORDS
-- =========================================================
CREATE TABLE IF NOT EXISTS attendance_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES class_sessions(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    status attendance_status NOT NULL DEFAULT 'UNKNOWN',
    source attendance_source NOT NULL DEFAULT 'FACE_RECOGNITION',
    first_seen_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    check_in_time TIMESTAMPTZ,
    check_out_time TIMESTAMPTZ,
    total_seen_seconds INTEGER NOT NULL DEFAULT 0 CHECK (total_seen_seconds >= 0),
    presence_ratio NUMERIC(5, 2) NOT NULL DEFAULT 0.00 CHECK (presence_ratio >= 0 AND presence_ratio <= 100),
    recognition_confidence NUMERIC(6, 4),
    similarity_score NUMERIC(6, 4),
    is_late BOOLEAN NOT NULL DEFAULT FALSE,
    is_manually_modified BOOLEAN NOT NULL DEFAULT FALSE,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, student_id),
    CHECK (check_out_time IS NULL OR check_in_time IS NULL OR check_out_time >= check_in_time)
);

CREATE TRIGGER trg_attendance_records_updated_at
BEFORE UPDATE ON attendance_records
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =========================================================
-- 15. ATTENDANCE DETECTION EVENTS
-- =========================================================
CREATE TABLE IF NOT EXISTS attendance_detection_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES class_sessions(id) ON DELETE CASCADE,
    student_id UUID REFERENCES students(id) ON DELETE SET NULL,
    attendance_record_id UUID REFERENCES attendance_records(id) ON DELETE CASCADE,
    track_id VARCHAR(100),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    bbox_x1 INTEGER,
    bbox_y1 INTEGER,
    bbox_x2 INTEGER,
    bbox_y2 INTEGER,
    detection_confidence NUMERIC(6, 4),
    recognition_confidence NUMERIC(6, 4),
    similarity_score NUMERIC(6, 4),
    frame_path TEXT,
    crop_path TEXT,
    is_accepted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================
-- 16. ATTENDANCE EVIDENCE IMAGES
-- =========================================================
CREATE TABLE IF NOT EXISTS attendance_evidence_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attendance_record_id UUID NOT NULL REFERENCES attendance_records(id) ON DELETE CASCADE,
    detection_event_id UUID REFERENCES attendance_detection_events(id) ON DELETE SET NULL,
    image_path TEXT NOT NULL,
    crop_path TEXT,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confidence NUMERIC(6, 4),
    similarity_score NUMERIC(6, 4),
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================
-- 17. ATTENDANCE MANUAL EDIT LOGS
-- =========================================================
CREATE TABLE IF NOT EXISTS attendance_edit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attendance_record_id UUID NOT NULL REFERENCES attendance_records(id) ON DELETE CASCADE,
    edited_by UUID REFERENCES users(id) ON DELETE SET NULL,
    old_status attendance_status,
    new_status attendance_status,
    old_check_in_time TIMESTAMPTZ,
    new_check_in_time TIMESTAMPTZ,
    old_check_out_time TIMESTAMPTZ,
    new_check_out_time TIMESTAMPTZ,
    reason TEXT,
    note TEXT,
    edited_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================
-- 18. ATTENDANCE RECHECK REQUESTS
-- =========================================================
CREATE TABLE IF NOT EXISTS attendance_recheck_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attendance_record_id UUID REFERENCES attendance_records(id) ON DELETE SET NULL,
    session_id UUID NOT NULL REFERENCES class_sessions(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    evidence_path TEXT,
    status request_status NOT NULL DEFAULT 'PENDING',
    lecturer_response TEXT,
    processed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trg_attendance_recheck_requests_updated_at
BEFORE UPDATE ON attendance_recheck_requests
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =========================================================
-- 19. NOTIFICATIONS
-- =========================================================
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type notification_type NOT NULL DEFAULT 'SYSTEM',
    title VARCHAR(255) NOT NULL,
    content TEXT,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    read_at TIMESTAMPTZ,
    related_entity_type VARCHAR(100),
    related_entity_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================
-- 20. SYSTEM ACTIVITY LOGS
-- =========================================================
CREATE TABLE IF NOT EXISTS system_activity_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(255) NOT NULL,
    entity_type VARCHAR(100),
    entity_id UUID,
    ip_address VARCHAR(100),
    user_agent TEXT,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================
-- 21. INDEXES
-- =========================================================
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);

CREATE INDEX IF NOT EXISTS idx_students_student_code ON students(student_code);
CREATE INDEX IF NOT EXISTS idx_students_full_name ON students(full_name);
CREATE INDEX IF NOT EXISTS idx_students_status ON students(status);

CREATE INDEX IF NOT EXISTS idx_lecturers_lecturer_code ON lecturers(lecturer_code);

CREATE INDEX IF NOT EXISTS idx_course_classes_lecturer_id ON course_classes(lecturer_id);
CREATE INDEX IF NOT EXISTS idx_course_classes_subject_id ON course_classes(subject_id);
CREATE INDEX IF NOT EXISTS idx_course_classes_school_year ON course_classes(school_year);

CREATE INDEX IF NOT EXISTS idx_course_class_students_class_id ON course_class_students(course_class_id);
CREATE INDEX IF NOT EXISTS idx_course_class_students_student_id ON course_class_students(student_id);

CREATE INDEX IF NOT EXISTS idx_join_requests_class_id ON course_class_join_requests(course_class_id);
CREATE INDEX IF NOT EXISTS idx_join_requests_student_id ON course_class_join_requests(student_id);
CREATE INDEX IF NOT EXISTS idx_join_requests_status ON course_class_join_requests(status);

CREATE INDEX IF NOT EXISTS idx_face_images_student_id ON student_face_images(student_id);
CREATE INDEX IF NOT EXISTS idx_face_images_status ON student_face_images(status);
CREATE INDEX IF NOT EXISTS idx_face_images_training ON student_face_images(is_used_for_training);

CREATE INDEX IF NOT EXISTS idx_face_embeddings_student_id ON face_embeddings(student_id);
CREATE INDEX IF NOT EXISTS idx_face_embeddings_active ON face_embeddings(is_active);

CREATE INDEX IF NOT EXISTS idx_class_sessions_class_id ON class_sessions(course_class_id);
CREATE INDEX IF NOT EXISTS idx_class_sessions_date ON class_sessions(session_date);
CREATE INDEX IF NOT EXISTS idx_class_sessions_status ON class_sessions(status);

CREATE INDEX IF NOT EXISTS idx_attendance_records_session_id ON attendance_records(session_id);
CREATE INDEX IF NOT EXISTS idx_attendance_records_student_id ON attendance_records(student_id);
CREATE INDEX IF NOT EXISTS idx_attendance_records_status ON attendance_records(status);
CREATE INDEX IF NOT EXISTS idx_attendance_records_session_status ON attendance_records(session_id, status);

CREATE INDEX IF NOT EXISTS idx_detection_events_session_id ON attendance_detection_events(session_id);
CREATE INDEX IF NOT EXISTS idx_detection_events_student_id ON attendance_detection_events(student_id);
CREATE INDEX IF NOT EXISTS idx_detection_events_track_id ON attendance_detection_events(track_id);
CREATE INDEX IF NOT EXISTS idx_detection_events_detected_at ON attendance_detection_events(detected_at);

CREATE INDEX IF NOT EXISTS idx_evidence_attendance_record_id ON attendance_evidence_images(attendance_record_id);

CREATE INDEX IF NOT EXISTS idx_recheck_student_id ON attendance_recheck_requests(student_id);
CREATE INDEX IF NOT EXISTS idx_recheck_session_id ON attendance_recheck_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_recheck_status ON attendance_recheck_requests(status);
CREATE INDEX IF NOT EXISTS idx_recheck_session_status ON attendance_recheck_requests(session_id, status);

CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_user_read_created ON notifications(user_id, is_read, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_activity_logs_user_id ON system_activity_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_logs_created_at ON system_activity_logs(created_at);

-- =========================================================
-- 22. PARTIAL UNIQUE INDEXES (business constraints)
-- =========================================================
CREATE UNIQUE INDEX IF NOT EXISTS uq_face_embedding_active_per_model
    ON face_embeddings(student_id, model_name, COALESCE(model_version, ''))
    WHERE is_active = TRUE;

CREATE UNIQUE INDEX IF NOT EXISTS uq_recheck_pending_per_attendance
    ON attendance_recheck_requests(attendance_record_id)
    WHERE status = 'PENDING' AND attendance_record_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_join_request_pending_per_class_student
    ON course_class_join_requests(course_class_id, student_id)
    WHERE status = 'PENDING'::request_status;

