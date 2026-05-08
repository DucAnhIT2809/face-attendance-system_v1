import { Navigate, useLocation } from "react-router-dom";
import { getStoredAuth } from "../authStorage";

export function RequireRole({ role, children }) {
  const location = useLocation();
  const auth = getStoredAuth();

  if (!auth.token) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (auth.role !== role) {
    if (auth.role === "LECTURER") {
      return <Navigate to="/lecturer/dashboard" replace />;
    }
    if (auth.role === "STUDENT") {
      return <Navigate to="/student/dashboard" replace />;
    }
    return <Navigate to="/login" replace />;
  }

  return children;
}
