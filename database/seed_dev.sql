-- Dữ liệu mẫu (chạy sau schema.sql trên face_attendance_db)
-- Đăng nhập API: gv01 / 1234 (giảng viên), sv01 / 1234 (sinh viên)
-- Mật khẩu: bcrypt giống backend Python (thư viện bcrypt), không dùng crypt() của PG để tránh lệch verify.

INSERT INTO users (username, password_hash, role, status)
VALUES (
    'gv01',
    '$2b$10$24KJn3teNmKRg10IY.bfqeVEF5aR0BTzW.RRRlIc2i/yWIJndk6we',
    'LECTURER',
    'ACTIVE'
)
ON CONFLICT (username) DO NOTHING;

INSERT INTO users (username, password_hash, role, status)
VALUES (
    'sv01',
    '$2b$10$24KJn3teNmKRg10IY.bfqeVEF5aR0BTzW.RRRlIc2i/yWIJndk6we',
    'STUDENT',
    'ACTIVE'
)
ON CONFLICT (username) DO NOTHING;

INSERT INTO lecturers (user_id, lecturer_code, full_name, email, department)
SELECT u.id, 'GV001', 'Giảng viên mẫu', 'gv01@school.edu', 'CNTT'
FROM users u WHERE u.username = 'gv01'
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO students (user_id, student_code, full_name, administrative_class, email, status, face_folder)
SELECT u.id, '20230001', 'Nguyễn Văn A', 'D21CQCN01-B', 'sv01@school.edu', 'ACTIVE', NULL
FROM users u WHERE u.username = 'sv01'
ON CONFLICT (student_code) DO NOTHING;

-- Cập nhật liên kết user nếu student đã tồn tại từ trước nhưng chưa có user_id
UPDATE students st
SET user_id = u.id
FROM users u
WHERE u.username = 'sv01' AND st.student_code = '20230001' AND st.user_id IS NULL;

INSERT INTO subjects (subject_code, subject_name, credits)
VALUES ('INT1481', 'Lập trình Web', 3)
ON CONFLICT (subject_code) DO NOTHING;

INSERT INTO course_classes (class_code, class_name, subject_id, lecturer_id, semester, school_year, room)
SELECT '13094', 'Lập trình Web — 13094', s.id, l.id, 'HK2', '2025-2026', 'P.101'
FROM subjects s
CROSS JOIN lecturers l
WHERE s.subject_code = 'INT1481' AND l.lecturer_code = 'GV001'
ON CONFLICT (class_code, semester, school_year) DO NOTHING;

INSERT INTO course_class_students (course_class_id, student_id)
SELECT cc.id, st.id
FROM course_classes cc
JOIN students st ON st.student_code = '20230001'
WHERE cc.class_code = '13094' AND cc.semester = 'HK2' AND cc.school_year = '2025-2026'
ON CONFLICT (course_class_id, student_id) DO NOTHING;

INSERT INTO class_sessions (
    course_class_id, session_code, session_date, start_time, end_time, room,
    attendance_mode, status, created_by
)
SELECT cc.id, 'SES-20260506-01', DATE '2026-05-06', TIME '07:00', TIME '09:00', 'P.101',
       'HYBRID', 'FINISHED', u.id
FROM course_classes cc
JOIN lecturers lec ON lec.id = cc.lecturer_id
JOIN users u ON u.id = lec.user_id
WHERE cc.class_code = '13094' AND cc.semester = 'HK2' AND cc.school_year = '2025-2026'
ON CONFLICT (session_code) DO NOTHING;

INSERT INTO attendance_records (
    session_id, student_id, status, source, check_in_time, similarity_score, recognition_confidence
)
SELECT cs.id, st.id, 'PRESENT', 'FACE_RECOGNITION', TIMESTAMPTZ '2026-05-06 07:02:00+07', 0.94, 0.94
FROM class_sessions cs
JOIN students st ON st.student_code = '20230001'
WHERE cs.session_code = 'SES-20260506-01'
ON CONFLICT (session_id, student_id) DO NOTHING;
