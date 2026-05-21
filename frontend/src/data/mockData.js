export const lecturerMenu = [
  { label: "Dashboard", to: "/lecturer/dashboard" },
  { label: "Lớp học phần", to: "/lecturer/classes" },
  { label: "Yêu cầu tham gia lớp", to: "/lecturer/class-join-requests" },
  { label: "Sinh viên", to: "/lecturer/students" },
  { label: "Buổi học", to: "/lecturer/sessions" },
  { label: "Điểm danh trực tiếp", to: "/lecturer/live-attendance" },
  { label: "Kết quả điểm danh", to: "/lecturer/attendance-results" },
  { label: "Yêu cầu kiểm tra lại", to: "/lecturer/review-requests" },
  { label: "Báo cáo", to: "/lecturer/reports" }
];

export const studentMenu = [
  { label: "Dashboard", to: "/student/dashboard" },
  { label: "Tham gia lớp", to: "/student/join-classes" },
  { label: "Thông tin cá nhân", to: "/student/profile" },
  { label: "Ảnh khuôn mặt", to: "/student/face-images" },
  { label: "Lịch sử điểm danh", to: "/student/attendance-history" },
  { label: "Yêu cầu kiểm tra lại", to: "/student/review-request" },
  { label: "Thông báo", to: "/student/notifications" }
];

export const lecturerStats = [
  { title: "Lớp đang phụ trách", value: "8 lớp" },
  { title: "Buổi đã điểm danh", value: "57 buổi" },
  { title: "Sinh viên quản lý", value: "312 SV" },
  { title: "Tỷ lệ chuyên cần TB", value: "91.4%" }
];

export const studentStats = [
  { title: "Lớp học phần đang học", value: "5 lớp" },
  { title: "Tỷ lệ chuyên cần", value: "94.2%" },
  { title: "Ảnh khuôn mặt hợp lệ", value: "7/8 ảnh" },
  { title: "Yêu cầu đang xử lý", value: "1 yêu cầu" }
];

export const classesRows = [
  ["INT1481", "Lập trình Web", "D21CQCN01", "52", "93%"],
  ["INT1419", "Cơ sở dữ liệu", "D21CQCN02", "48", "89%"],
  ["INT1467", "Thị giác máy tính", "D21CQCN01", "45", "88%"]
];

export const studentsRows = [
  ["B21DCCN001", "Nguyễn Văn A", "Đủ ảnh", "96%", "Bình thường"],
  ["B21DCCN023", "Trần Thị B", "Thiếu ảnh", "87%", "Cần nhắc"],
  ["B21DCCN081", "Lê Văn C", "Đang duyệt", "72%", "Chuyên cần thấp"]
];

export const attendanceRows = [
  ["B21DCCN001", "07:02", "Có mặt", "0.96"],
  ["B21DCCN023", "07:15", "Đi muộn", "0.91"],
  ["B21DCCN081", "--", "Vắng", "--"]
];

export const personalRows = [
  ["Lập trình Web", "03/05/2026", "Có mặt", "07:01"],
  ["Cơ sở dữ liệu", "01/05/2026", "Đi muộn", "07:12"],
  ["Trí tuệ nhân tạo", "28/04/2026", "Có mặt", "06:58"]
];
