import { useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { apiFetch } from "../api/client";
import { clearStoredAuth, getStoredAuth } from "../authStorage";
import { lecturerMenu, studentMenu } from "../data/mockData";

export function AppLayout({ role }) {
  const location = useLocation();
  const navigate = useNavigate();
  const menus = role === "LECTURER" ? lecturerMenu : studentMenu;
  const auth = getStoredAuth();
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [passwordForm, setPasswordForm] = useState({
    current_password: "",
    new_password: "",
    confirm_password: ""
  });
  const [passwordMessage, setPasswordMessage] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);

  function logout() {
    clearStoredAuth();
    navigate("/login", { replace: true });
  }

  async function submitChangePassword(e) {
    e.preventDefault();
    setPasswordMessage("");
    setPasswordError("");
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      setPasswordError("Mật khẩu mới nhập lại không khớp");
      return;
    }
    setSavingPassword(true);
    try {
      const res = await apiFetch("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({
          current_password: passwordForm.current_password,
          new_password: passwordForm.new_password
        })
      });
      setPasswordMessage(res.message || "Đổi mật khẩu thành công");
      setPasswordForm({ current_password: "", new_password: "", confirm_password: "" });
    } catch (err) {
      setPasswordError(err.message);
    } finally {
      setSavingPassword(false);
    }
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>Face Attendance</h1>
        <p className="hint">Hệ thống điểm danh bằng nhận diện khuôn mặt</p>
        {auth.username ? (
          <p className="hint sidebar-user">
            Đăng nhập: <strong>{auth.username}</strong>
          </p>
        ) : null}

        <div className="role-switch">
          <button
            type="button"
            className={role === "LECTURER" ? "active" : ""}
            onClick={() => navigate("/lecturer/dashboard")}
          >
            Giảng viên
          </button>
          <button
            type="button"
            className={role === "STUDENT" ? "active" : ""}
            onClick={() => navigate("/student/dashboard")}
          >
            Sinh viên
          </button>
        </div>

        <nav>
          {menus.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                isActive ? "menu-item active" : "menu-item"
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <button type="button" className="logout" onClick={logout}>
          Đăng xuất
        </button>
      </aside>

      <main className="content">
        <section className="header">
          <div>
            <h2>
              {menus.find((x) => location.pathname.includes(x.to.split("/").pop()))
                ?.label || "Dashboard"}
            </h2>
            <p className="hint">
              {role === "LECTURER"
                ? "Quản lý lớp học, điểm danh, báo cáo và thống kê."
                : "Theo dõi thông tin cá nhân, ảnh khuôn mặt và lịch sử điểm danh."}
            </p>
          </div>
          <button
            type="button"
            className="primary"
            onClick={() => {
              setShowPasswordForm((open) => !open);
              setPasswordMessage("");
              setPasswordError("");
            }}
          >
            Đổi mật khẩu
          </button>
        </section>
        <Outlet />
      </main>
      {showPasswordForm ? (
        <div className="modal-backdrop" role="presentation">
          <form className="password-modal" onSubmit={submitChangePassword}>
            <div className="modal-header">
              <div>
                <h3>Đổi mật khẩu</h3>
                <p className="hint">Nhập mật khẩu hiện tại và mật khẩu mới.</p>
              </div>
              <button
                type="button"
                className="modal-close"
                disabled={savingPassword}
                onClick={() => {
                  setShowPasswordForm(false);
                  setPasswordForm({ current_password: "", new_password: "", confirm_password: "" });
                  setPasswordMessage("");
                  setPasswordError("");
                }}
                aria-label="Đóng popup đổi mật khẩu"
              >
                ×
              </button>
            </div>
            <input
              type="password"
              placeholder="Mật khẩu hiện tại"
              value={passwordForm.current_password}
              onChange={(e) =>
                setPasswordForm((prev) => ({ ...prev, current_password: e.target.value }))
              }
              autoComplete="current-password"
              required
            />
            <input
              type="password"
              placeholder="Mật khẩu mới"
              value={passwordForm.new_password}
              onChange={(e) => setPasswordForm((prev) => ({ ...prev, new_password: e.target.value }))}
              autoComplete="new-password"
              minLength={4}
              required
            />
            <input
              type="password"
              placeholder="Nhập lại mật khẩu mới"
              value={passwordForm.confirm_password}
              onChange={(e) =>
                setPasswordForm((prev) => ({ ...prev, confirm_password: e.target.value }))
              }
              autoComplete="new-password"
              minLength={4}
              required
            />
            {passwordMessage ? <p className="hint password-success">{passwordMessage}</p> : null}
            {passwordError ? <p className="hint api-error">{passwordError}</p> : null}
            <div className="modal-actions">
              <button type="submit" className="primary" disabled={savingPassword}>
                {savingPassword ? "Đang lưu..." : "Lưu mật khẩu"}
              </button>
              <button
                type="button"
                disabled={savingPassword}
                onClick={() => {
                  setShowPasswordForm(false);
                  setPasswordForm({ current_password: "", new_password: "", confirm_password: "" });
                  setPasswordMessage("");
                  setPasswordError("");
                }}
              >
                Hủy
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
