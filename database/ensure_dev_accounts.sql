-- Chạy trên database face_attendance_db (pgAdmin: Query Tool hoặc psql)
-- Mật khẩu: 1234 — hash bcrypt đúng với backend Python
-- Giải quyết: "Sai tên đăng nhập hoặc mật khẩu" khi chưa seed hoặc hash trong DB sai

INSERT INTO users (username, password_hash, role, status)
VALUES
  (
    'gv01',
    '$2b$10$24KJn3teNmKRg10IY.bfqeVEF5aR0BTzW.RRRlIc2i/yWIJndk6we',
    'LECTURER',
    'ACTIVE'
  ),
  (
    'sv01',
    '$2b$10$24KJn3teNmKRg10IY.bfqeVEF5aR0BTzW.RRRlIc2i/yWIJndk6we',
    'STUDENT',
    'ACTIVE'
  )
ON CONFLICT (username) DO UPDATE SET
  password_hash = EXCLUDED.password_hash,
  role = EXCLUDED.role,
  status = EXCLUDED.status;

INSERT INTO lecturers (user_id, lecturer_code, full_name, email, department)
SELECT u.id, 'GV001', 'Giảng viên mẫu', 'gv01@school.edu', 'CNTT'
FROM users u WHERE u.username = 'gv01'
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO students (user_id, student_code, full_name, administrative_class, email, status, face_folder)
SELECT u.id, '20230001', 'Nguyễn Văn A', 'D21CQCN01-B', 'sv01@school.edu', 'ACTIVE', NULL
FROM users u WHERE u.username = 'sv01'
ON CONFLICT (student_code) DO NOTHING;

UPDATE students st
SET user_id = u.id
FROM users u
WHERE u.username = 'sv01' AND st.student_code = '20230001' AND (st.user_id IS NULL OR st.user_id <> u.id);

-- Kiểm tra nhanh (bảng kết quả phải có 2 dòng gv01, sv01)
SELECT username, role::text, status::text, length(password_hash) AS hash_len
FROM users
WHERE username IN ('gv01', 'sv01');
