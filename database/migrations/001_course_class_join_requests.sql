-- Chạy trên DB đã có schema cũ (bổ sung bảng yêu cầu tham gia lớp).
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

DROP TRIGGER IF EXISTS trg_course_class_join_requests_updated_at ON course_class_join_requests;
CREATE TRIGGER trg_course_class_join_requests_updated_at
BEFORE UPDATE ON course_class_join_requests
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_join_requests_class_id ON course_class_join_requests(course_class_id);
CREATE INDEX IF NOT EXISTS idx_join_requests_student_id ON course_class_join_requests(student_id);
CREATE INDEX IF NOT EXISTS idx_join_requests_status ON course_class_join_requests(status);

CREATE UNIQUE INDEX IF NOT EXISTS uq_join_request_pending_per_class_student
    ON course_class_join_requests(course_class_id, student_id)
    WHERE status = 'PENDING'::request_status;
