import { clearStoredAuth, getStoredAuth } from "../authStorage";

export function getApiBase() {
  // Dev: gọi /api qua Vite proxy → tránh CORS và dễ chạy local
  if (import.meta.env.DEV) return "";
  const base = import.meta.env.VITE_API_URL || "http://localhost:8001";
  return String(base).replace(/\/$/, "");
}

function parseErrorDetail(text) {
  try {
    const j = JSON.parse(text);
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail)) return j.detail.map((x) => x.msg || x).join("; ");
    if (j.detail != null) return JSON.stringify(j.detail);
    return text;
  } catch {
    return text || "Lỗi không xác định";
  }
}

export async function apiFetch(path, options = {}) {
  const { skipAuthRedirect, ...fetchOpts } = options;
  const token = getStoredAuth().token;
  const headers = { ...(fetchOpts.headers || {}) };
  if (fetchOpts.body && !(fetchOpts.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const base = getApiBase();
  const url = base ? `${base}${path}` : path;
  let res;
  try {
    res = await fetch(url, { ...fetchOpts, headers });
  } catch (e) {
    const msg =
      e instanceof TypeError
        ? "Không kết nối được backend. Chạy API (cổng 8001): từ thư mục gốc project gõ npm run backend — rồi mở lại trang."
        : String(e?.message || e);
    throw new Error(msg);
  }

  if (res.status === 401) {
    if (path === "/api/auth/login" || skipAuthRedirect) {
      const text = await res.text();
      throw new Error(parseErrorDetail(text) || "Đăng nhập thất bại");
    }
    clearStoredAuth();
    window.location.assign("/login");
    throw new Error("Phiên đăng nhập hết hạn hoặc không hợp lệ.");
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseErrorDetail(text) || `HTTP ${res.status}`);
  }

  const ct = res.headers.get("content-type");
  if (ct && ct.includes("application/json")) return res.json();
  return res.text();
}

export async function loginRequest(username, password) {
  return apiFetch("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
    skipAuthRedirect: true
  });
}
