import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { RequireRole } from "./components/RequireRole";
import { LoginPage } from "./pages/LoginPage";
import {
  LecturerAttendancePage,
  LecturerClassJoinRequestsPage,
  LecturerClassesPage,
  LecturerDashboardPage,
  LecturerLiveAttendancePage,
  LecturerReportsPage,
  LecturerReviewRequestsPage,
  LecturerSessionsPage,
  LecturerStudentsPage
} from "./pages/LecturerPages";
import {
  StudentDashboardPage,
  StudentFacePage,
  StudentHistoryPage,
  StudentJoinClassesPage,
  StudentInfoPage,
  StudentNotificationsPage,
  StudentReviewPage
} from "./pages/StudentPages";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<LoginPage />} />

      <Route
        path="/lecturer"
        element={
          <RequireRole role="LECTURER">
            <AppLayout role="LECTURER" />
          </RequireRole>
        }
      >
        <Route index element={<Navigate to="dashboard" replace />} />
        <Route path="dashboard" element={<LecturerDashboardPage />} />
        <Route path="classes" element={<LecturerClassesPage />} />
        <Route path="class-join-requests" element={<LecturerClassJoinRequestsPage />} />
        <Route path="students" element={<LecturerStudentsPage />} />
        <Route path="sessions" element={<LecturerSessionsPage />} />
        <Route path="live-attendance" element={<LecturerLiveAttendancePage />} />
        <Route path="attendance-results" element={<LecturerAttendancePage />} />
        <Route path="review-requests" element={<LecturerReviewRequestsPage />} />
        <Route path="reports" element={<LecturerReportsPage />} />
      </Route>

      <Route
        path="/student"
        element={
          <RequireRole role="STUDENT">
            <AppLayout role="STUDENT" />
          </RequireRole>
        }
      >
        <Route index element={<Navigate to="dashboard" replace />} />
        <Route path="dashboard" element={<StudentDashboardPage />} />
        <Route path="join-classes" element={<StudentJoinClassesPage />} />
        <Route path="profile" element={<StudentInfoPage />} />
        <Route path="face-images" element={<StudentFacePage />} />
        <Route path="attendance-history" element={<StudentHistoryPage />} />
        <Route path="review-request" element={<StudentReviewPage />} />
        <Route path="notifications" element={<StudentNotificationsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

export default App;
