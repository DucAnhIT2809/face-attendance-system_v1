-- Chạy một lần nếu đã import seed cũ (dùng crypt) và đăng nhập API báo sai mật khẩu.
-- Cập nhật hash bcrypt tương thích Python cho mật khẩu: 1234

UPDATE users
SET password_hash = '$2b$10$24KJn3teNmKRg10IY.bfqeVEF5aR0BTzW.RRRlIc2i/yWIJndk6we'
WHERE username IN ('gv01', 'sv01');
