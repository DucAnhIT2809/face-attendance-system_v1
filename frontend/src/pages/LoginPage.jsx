import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { loginRequest } from "../api/client";
import { getStoredAuth, setStoredAuth } from "../authStorage";

export function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("gv01");
  const [password, setPassword] = useState("1234");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const auth = getStoredAuth();
    if (auth.token && auth.role === "LECTURER") navigate("/lecturer/dashboard", { replace: true });
    else if (auth.token && auth.role === "STUDENT") navigate("/student/dashboard", { replace: true });
  }, [navigate]);

  async function handleLogin(expectedRole) {
    setError("");
    setLoading(true);
    try {
      const data = await loginRequest(username.trim(), password);
      if (data.role !== expectedRole) {
        setError(
          expectedRole === "LECTURER"
            ? "Tài khoản này không phải giảng viên. Dùng nút Sinh viên hoặc tài khoản sv01."
            : "Tài khoản này không phải sinh viên. Dùng nút Giảng viên hoặc tài khoản gv01."
        );
        return;
      }
      setStoredAuth({
        token: data.access_token,
        role: data.role,
        username: username.trim()
      });
      navigate(expectedRole === "LECTURER" ? "/lecturer/dashboard" : "/student/dashboard", {
        replace: true
      });
    } catch (e) {
      setError(e.message || "Đăng nhập thất bại");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h2>Đăng nhập hệ thống</h2>
        {error ? <p className="login-error">{error}</p> : null}
        <input
          placeholder="Tên đăng nhập"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
        />
        <input
          placeholder="Mật khẩu"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
        <div className="role-switch">
          <button
            type="button"
            className="active"
            disabled={loading}
            onClick={() => handleLogin("LECTURER")}
          >
            {loading ? "Đang xử lý…" : "Đăng nhập — Giảng viên"}
          </button>
          <button type="button" disabled={loading} onClick={() => handleLogin("STUDENT")}>
            {loading ? "Đang xử lý…" : "Đăng nhập — Sinh viên"}
          </button>
        </div>
      </div>
    </div>
  );
}
