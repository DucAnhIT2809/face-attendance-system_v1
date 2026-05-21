import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../api/client";
import { DataTable, PageBlock, StatCards } from "../components/Common";

function getTodayDateString() {
  const now = new Date();
  const offsetDate = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return offsetDate.toISOString().slice(0, 10);
}

export function LecturerDashboardPage() {
  const [summary, setSummary] = useState(null);
  const [absenceRows, setAbsenceRows] = useState([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [summaryData, absenceData] = await Promise.all([
          apiFetch("/api/lecturer/dashboard/summary"),
          apiFetch("/api/lecturer/dashboard/absences")
        ]);
        if (!cancelled) {
          setSummary(summaryData);
          setAbsenceRows(
            (absenceData || []).map((r) => [
              r.class_code ?? "",
              r.subject_name ?? "",
              r.session_date ?? "",
              r.student_code ?? "",
              r.full_name ?? ""
            ])
          );
        }
      } catch (e) {
        if (!cancelled) setErr(e.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const cards = summary
    ? [
        { title: "Lớp học phần", value: String(summary.course_class_count) },
        { title: "Sinh viên (đang ghi danh)", value: String(summary.managed_student_count) },
        { title: "Buổi học / điểm danh", value: String(summary.session_count) }
      ]
    : [
        { title: "Lớp học phần", value: "…" },
        { title: "Sinh viên", value: "…" },
        { title: "Buổi học", value: "…" }
      ];

  return (
    <section className="panel-list">
      {err ? <p className="hint api-error">{err}</p> : null}
      <StatCards cards={cards} />
      <PageBlock title="Thống kê sinh viên nghỉ học theo lớp">
        <p className="hint">Danh sách sinh viên chưa có bản ghi điểm danh ở các buổi đã kết thúc trước hôm nay.</p>
        <DataTable
          headers={["Lớp", "Môn học", "Ngày", "Mã SV", "Họ tên"]}
          rows={absenceRows}
        />
      </PageBlock>
    </section>
  );
}

export function LecturerClassesPage() {
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    class_code: "",
    class_name: "",
    subject_code: "",
    subject_name: "",
    credits: 3,
    semester: "HK2",
    school_year: "2025-2026",
    room: "",
    description: ""
  });

  async function loadClasses(cancelled) {
    const data = await apiFetch("/api/lecturer/course-classes");
    if (cancelled) return;
    const table = (data || []).map((r) => [
      r.class_code ?? "",
      r.subject_name ?? "",
      r.class_name ?? "",
      String(r.student_count ?? 0),
      `${r.semester ?? ""} ${r.school_year ?? ""}`.trim()
    ]);
    setRows(table);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await loadClasses(cancelled);
      } catch (e) {
        if (!cancelled) setErr(e.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <PageBlock title="Lớp học phần">
      {err ? <p className="hint api-error">{err}</p> : null}
      {msg ? <p className="hint password-success">{msg}</p> : null}

      <h4 className="subpanel-title">Tạo lớp mới</h4>
      <p className="hint">
        Sau khi tạo, sinh viên có thể tìm lớp và gửi yêu cầu tham gia; bạn duyệt tại mục &quot;Yêu cầu tham gia lớp&quot;.
      </p>
      <div className="form-grid">
        <label>
          Mã lớp HP *
          <input
            value={form.class_code}
            onChange={(e) => setForm((f) => ({ ...f, class_code: e.target.value }))}
            placeholder="VD: 13094"
          />
        </label>
        <label>
          Tên lớp HP
          <input
            value={form.class_name}
            onChange={(e) => setForm((f) => ({ ...f, class_name: e.target.value }))}
            placeholder="Tùy chọn"
          />
        </label>
        <label>
          Mã học phần *
          <input
            value={form.subject_code}
            onChange={(e) => setForm((f) => ({ ...f, subject_code: e.target.value }))}
            placeholder="VD: INT1481"
          />
        </label>
        <label>
          Tên học phần *
          <input
            value={form.subject_name}
            onChange={(e) => setForm((f) => ({ ...f, subject_name: e.target.value }))}
            placeholder="Dùng khi tạo học phần mới"
          />
        </label>
        <label>
          Số tín chỉ
          <input
            type="number"
            min={0}
            max={30}
            value={form.credits}
            onChange={(e) => setForm((f) => ({ ...f, credits: Number(e.target.value) || 0 }))}
          />
        </label>
        <label>
          Học kỳ *
          <select
            value={form.semester}
            onChange={(e) => setForm((f) => ({ ...f, semester: e.target.value }))}
          >
            <option value="HK1">HK1</option>
            <option value="HK2">HK2</option>
            <option value="HK_HE">HK hè</option>
          </select>
        </label>
        <label>
          Năm học *
          <input
            value={form.school_year}
            onChange={(e) => setForm((f) => ({ ...f, school_year: e.target.value }))}
            placeholder="2025-2026"
          />
        </label>
        <label>
          Phòng
          <input
            value={form.room}
            onChange={(e) => setForm((f) => ({ ...f, room: e.target.value }))}
          />
        </label>
        <label className="full-width">
          Mô tả
          <input
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
          />
        </label>
      </div>
      <div className="actions">
        <button
          type="button"
          className="primary"
          disabled={creating}
          onClick={async () => {
            setErr("");
            setMsg("");
            if (!form.class_code.trim() || !form.subject_code.trim() || !form.subject_name.trim()) {
              setErr("Nhập đủ mã lớp, mã học phần và tên học phần.");
              return;
            }
            setCreating(true);
            try {
              await apiFetch("/api/lecturer/course-classes", {
                method: "POST",
                body: JSON.stringify({
                  class_code: form.class_code.trim(),
                  class_name: form.class_name.trim() || null,
                  subject_code: form.subject_code.trim(),
                  subject_name: form.subject_name.trim(),
                  credits: form.credits,
                  semester: form.semester,
                  school_year: form.school_year.trim(),
                  room: form.room.trim() || null,
                  description: form.description.trim() || null
                })
              });
              setMsg("Đã tạo lớp học phần.");
              await loadClasses(false);
            } catch (e) {
              setErr(e.message);
            } finally {
              setCreating(false);
            }
          }}
        >
          {creating ? "Đang tạo..." : "Tạo lớp"}
        </button>
      </div>

      <h4 className="subpanel-title">Danh sách lớp đang phụ trách</h4>
      <DataTable
        headers={["Mã lớp", "Môn học", "Tên lớp HP", "Sĩ số", "Học kỳ / năm"]}
        rows={rows}
      />
    </PageBlock>
  );
}

export function LecturerClassJoinRequestsPage() {
  const [items, setItems] = useState([]);
  const [err, setErr] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [busyId, setBusyId] = useState("");

  async function load() {
    const q = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : "";
    const data = await apiFetch(`/api/lecturer/course-class-join-requests${q}`);
    setItems(data || []);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const q = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : "";
        const data = await apiFetch(`/api/lecturer/course-class-join-requests${q}`);
        if (!cancelled) setItems(data || []);
      } catch (e) {
        if (!cancelled) setErr(e.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [statusFilter]);

  async function decide(id, decision) {
    const note =
      decision === "REJECTED"
        ? window.prompt("Ghi chú từ chối (tùy chọn, Enter để bỏ qua)") ?? ""
        : "";
    setBusyId(String(id));
    setErr("");
    try {
      await apiFetch(`/api/lecturer/course-class-join-requests/${id}/decision`, {
        method: "POST",
        body: JSON.stringify({
          decision,
          lecturer_note: note.trim() || null
        })
      });
      await load();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusyId("");
    }
  }

  return (
    <PageBlock title="Yêu cầu tham gia lớp">
      {err ? <p className="hint api-error">{err}</p> : null}
      <div className="actions">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          aria-label="Lọc trạng thái"
        >
          <option value="">Tất cả trạng thái</option>
          <option value="PENDING">Đang chờ</option>
          <option value="APPROVED">Đã chấp nhận</option>
          <option value="REJECTED">Đã từ chối</option>
          <option value="CANCELLED">Sinh viên đã hủy</option>
        </select>
        <button type="button" onClick={() => load()}>
          Làm mới
        </button>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Trạng thái</th>
              <th>Mã lớp / môn</th>
              <th>Sinh viên</th>
              <th>Lời nhắn SV</th>
              <th>Ghi chú GV</th>
              <th>Thời gian</th>
              <th>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.id}>
                <td>{r.status}</td>
                <td>
                  {r.class_code} — {r.subject_name}
                  <div className="hint">{r.subject_code}</div>
                </td>
                <td>
                  {r.student_code} — {r.full_name}
                  <div className="hint">{r.administrative_class ?? ""}</div>
                </td>
                <td>{r.message ?? "—"}</td>
                <td>{r.lecturer_note ?? "—"}</td>
                <td>
                  <span className="hint">{String(r.created_at ?? "").slice(0, 19)}</span>
                </td>
                <td>
                  {r.status === "PENDING" ? (
                    <div className="inline-actions">
                      <button
                        type="button"
                        className="primary"
                        disabled={busyId === String(r.id)}
                        onClick={() => decide(r.id, "APPROVED")}
                      >
                        Chấp nhận
                      </button>
                      <button
                        type="button"
                        disabled={busyId === String(r.id)}
                        onClick={() => decide(r.id, "REJECTED")}
                      >
                        Từ chối
                      </button>
                    </div>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!items.length ? <p className="hint">Chưa có yêu cầu.</p> : null}
    </PageBlock>
  );
}

export function LecturerStudentsPage() {
  const [classes, setClasses] = useState([]);
  const [classId, setClassId] = useState("");
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await apiFetch("/api/lecturer/course-classes");
        if (!cancelled) {
          setClasses(data || []);
          if (data?.length && !classId) setClassId(String(data[0].id));
        }
      } catch (e) {
        if (!cancelled) setErr(e.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!classId) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await apiFetch(
          `/api/lecturer/students?course_class_id=${encodeURIComponent(classId)}`
        );
        const table = (data || []).map((r) => [
          r.student_code ?? "",
          r.full_name ?? "",
          r.administrative_class ?? "",
          String(r.face_image_count ?? 0),
          r.student_status ?? ""
        ]);
        if (!cancelled) setRows(table);
      } catch (e) {
        if (!cancelled) setErr(e.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [classId]);

  return (
    <PageBlock title="Danh sách sinh viên trong lớp">
      {err ? <p className="hint api-error">{err}</p> : null}
      <div className="actions">
        <select
          value={classId}
          onChange={(e) => setClassId(e.target.value)}
          aria-label="Chọn lớp học phần"
        >
          {classes.map((c) => (
            <option key={c.id} value={c.id}>
              {c.class_code} — {c.subject_name}
            </option>
          ))}
        </select>
      </div>
      <DataTable
        headers={["Mã SV", "Họ tên", "Lớp hành chính", "Số ảnh khuôn mặt", "Trạng thái"]}
        rows={rows}
      />
    </PageBlock>
  );
}

export function LecturerSessionsPage() {
  const [sessions, setSessions] = useState([]);
  const [editingSessionId, setEditingSessionId] = useState("");
  const [editForm, setEditForm] = useState(null);
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);

  const statusOptions = ["NOT_STARTED", "RUNNING", "FINISHED", "LOCKED"];
  const modeOptions = ["FIXED_TIME_WINDOW", "CONTINUOUS", "HYBRID"];

  function formatClockTime(value) {
    if (!value) return "";
    const text = String(value);
    const match = text.match(/T(\d{2}:\d{2}:\d{2})/);
    if (match) return match[1];
    return text.slice(0, 8);
  }

  function formatSessionTime(session) {
    const liveStart = formatClockTime(session.started_at);
    const liveEnd = formatClockTime(session.finished_at);
    if (liveStart || liveEnd) return `${liveStart || "—"}–${liveEnd || "Đang chạy"}`;
    return `${session.start_time ?? ""}–${session.end_time ?? ""}`;
  }

  function startEdit(session) {
    setErr("");
    setEditingSessionId(session.id);
    setEditForm({
      session_date: String(session.session_date ?? "").slice(0, 10),
      start_time: String(session.start_time ?? "").slice(0, 5),
      end_time: String(session.end_time ?? "").slice(0, 5),
      room: session.room ?? "",
      status: session.status ?? "NOT_STARTED",
      attendance_mode: session.attendance_mode ?? "HYBRID"
    });
  }

  async function saveEdit() {
    if (!editingSessionId || !editForm) return;
    setSaving(true);
    setErr("");
    try {
      const updated = await apiFetch(`/api/lecturer/sessions/${encodeURIComponent(editingSessionId)}`, {
        method: "PATCH",
        body: JSON.stringify({
          ...editForm,
          room: editForm.room.trim() || null
        })
      });
      setSessions((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
      setEditingSessionId("");
      setEditForm(null);
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await apiFetch("/api/lecturer/sessions");
        if (!cancelled) setSessions(data || []);
      } catch (e) {
        if (!cancelled) setErr(e.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const rows = sessions.map((r) => [
    r.subject_name ?? r.class_name ?? "",
    r.class_code ?? "",
    String(r.session_date ?? ""),
    formatSessionTime(r),
    r.status ?? "",
    r.attendance_mode ?? "",
    <button type="button" onClick={() => startEdit(r)}>
      Sửa
    </button>
  ]);

  return (
    <PageBlock title="Quản lý buổi học">
      {err ? <p className="hint api-error">{err}</p> : null}
      {editForm ? (
        <div className="actions session-edit-form">
          <input
            type="date"
            value={editForm.session_date}
            onChange={(e) => setEditForm((prev) => ({ ...prev, session_date: e.target.value }))}
            aria-label="Ngày buổi học"
          />
          <input
            type="time"
            value={editForm.start_time}
            onChange={(e) => setEditForm((prev) => ({ ...prev, start_time: e.target.value }))}
            aria-label="Giờ bắt đầu"
          />
          <input
            type="time"
            value={editForm.end_time}
            onChange={(e) => setEditForm((prev) => ({ ...prev, end_time: e.target.value }))}
            aria-label="Giờ kết thúc"
          />
          <input
            value={editForm.room}
            onChange={(e) => setEditForm((prev) => ({ ...prev, room: e.target.value }))}
            placeholder="Phòng học"
            aria-label="Phòng học"
          />
          <select
            value={editForm.status}
            onChange={(e) => setEditForm((prev) => ({ ...prev, status: e.target.value }))}
            aria-label="Trạng thái"
          >
            {statusOptions.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
          <select
            value={editForm.attendance_mode}
            onChange={(e) => setEditForm((prev) => ({ ...prev, attendance_mode: e.target.value }))}
            aria-label="Chế độ điểm danh"
          >
            {modeOptions.map((mode) => (
              <option key={mode} value={mode}>
                {mode}
              </option>
            ))}
          </select>
          <button type="button" className="primary" disabled={saving} onClick={saveEdit}>
            {saving ? "Đang lưu..." : "Lưu cập nhật"}
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => {
              setEditingSessionId("");
              setEditForm(null);
            }}
          >
            Hủy
          </button>
        </div>
      ) : null}
      <p className="hint">Danh sách buổi học từ cơ sở dữ liệu (tối đa 100 bản ghi gần nhất).</p>
      <DataTable
        headers={["Tên môn học", "Lớp", "Ngày", "Giờ", "Trạng thái", "Chế độ", "Thao tác"]}
        rows={rows}
      />
    </PageBlock>
  );
}

export function LecturerLiveAttendancePage() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [sessions, setSessions] = useState([]);
  const [classes, setClasses] = useState([]);
  const [classCode, setClassCode] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [running, setRunning] = useState(false);
  const [latest, setLatest] = useState(null);
  const [board, setBoard] = useState({ present: [], not_present: [] });
  const [err, setErr] = useState("");
  const [stopping, setStopping] = useState(false);

  function clearLivePreview() {
    setLatest(null);
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.srcObject = null;
    }
  }

  async function startCamera() {
    if (!classCode) {
      setErr("Vui lòng chọn lớp học phần trước khi bắt đầu camera.");
      return;
    }
    setErr("");
    try {
      const todaySession = await apiFetch(
        `/api/lecturer/sessions/live-today?class_code=${encodeURIComponent(classCode)}`,
        { method: "POST" }
      );
      setSessionId(String(todaySession.id));
      setSessions((prev) => {
        const exists = prev.some((s) => s.id === todaySession.id);
        if (exists) return prev.map((s) => (s.id === todaySession.id ? todaySession : s));
        return [todaySession, ...prev];
      });
      setBoard({ present: [], not_present: [] });
      setLatest(null);
      setRunning(true);
    } catch (e) {
      setErr(e.message);
      setRunning(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [cls, ses] = await Promise.all([
          apiFetch("/api/lecturer/course-classes"),
          apiFetch("/api/lecturer/sessions")
        ]);
        const classList = cls || [];
        const sessionList = ses || [];
        const active = sessionList.filter((s) => s.status === "RUNNING" || s.status === "NOT_STARTED");
        const list = active.length ? active : sessionList;
        if (!cancelled) {
          setClasses(classList);
          if (classList.length && !classCode) setClassCode(String(classList[0].class_code));
          setSessions(list);
        }
      } catch (e) {
        if (!cancelled) setErr(e.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const today = getTodayDateString();
    const todaySession = sessions.find((s) => {
      const sameClass = classCode ? s.class_code === classCode : true;
      const sameDate = String(s.session_date || "").slice(0, 10) === today;
      return sameClass && sameDate;
    });

    setSessionId(todaySession ? String(todaySession.id) : "");
    clearLivePreview();
    setBoard({ present: [], not_present: [] });
  }, [sessions, classCode]);

  useEffect(() => {
    if (!running) return;
    let stream;
    navigator.mediaDevices
      .getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          facingMode: "user"
        },
        audio: false
      })
      .then((s) => {
        stream = s;
        if (videoRef.current) {
          videoRef.current.srcObject = s;
          videoRef.current.play().catch(() => {});
        }
      })
      .catch((e) => setErr(`Không mở được camera: ${e.message}`));
    return () => {
      if (stream) stream.getTracks().forEach((t) => t.stop());
      if (videoRef.current) videoRef.current.srcObject = null;
    };
  }, [running]);

  useEffect(() => {
    if (!running || !sessionId) {
      if (running && !sessionId) setErr("Không có buổi học hôm nay cho lớp đã chọn.");
      return;
    }
    let inFlight = false;
    const tick = setInterval(async () => {
      if (inFlight) return;
      try {
        const video = videoRef.current;
        const canvas = canvasRef.current;
        if (!video || !canvas || video.videoWidth === 0) return;
        inFlight = true;
        const maxWidth = 1280;
        const scale = Math.min(1, maxWidth / video.videoWidth);
        canvas.width = Math.round(video.videoWidth * scale);
        canvas.height = Math.round(video.videoHeight * scale);
        const ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.7));
        if (!blob) return;
        const fd = new FormData();
        fd.append("file", blob, "frame.jpg");
        const rec = await apiFetch(
          `/api/recognize/realtime-frame?session_id=${encodeURIComponent(sessionId)}&threshold=0.9`,
          { method: "POST", body: fd }
        );
        setLatest(rec);
      } catch (e) {
        setErr(e.message);
      } finally {
        inFlight = false;
      }
    }, 650);
    return () => clearInterval(tick);
  }, [running, sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    const poll = setInterval(async () => {
      try {
        const b = await apiFetch(`/api/recognize/live-board?session_id=${encodeURIComponent(sessionId)}`);
        setBoard(b);
      } catch (e) {
        setErr(e.message);
      }
    }, 1500);
    return () => clearInterval(poll);
  }, [sessionId]);

  const trackedFaces = running && Array.isArray(latest?.faces)
    ? latest.faces
    : running && latest?.face_box
    ? [latest]
    : [];

  function getFaceBoxStyle(faceBox) {
    if (!faceBox?.image_width || !faceBox?.image_height) return null;
    return {
      left: `${(faceBox.x / faceBox.image_width) * 100}%`,
      top: `${(faceBox.y / faceBox.image_height) * 100}%`,
      width: `${(faceBox.width / faceBox.image_width) * 100}%`,
      height: `${(faceBox.height / faceBox.image_height) * 100}%`
    };
  }

  function getTrackingName(face) {
    if (face?.candidate_student) {
      return `${face.candidate_student.student_code} - ${face.candidate_student.full_name}`;
    }
    if (face?.identity_label && face.identity_label !== "unknown") return face.identity_label;
    return "Đang tìm khuôn mặt";
  }

  function getTrackingStatus(face) {
    if (face?.confirmed) return "Đã điểm danh";
    if (face?.candidate_student) {
      return `Đang xác nhận ${face.pending_hits ?? 0}/${face.required_hits ?? 4}`;
    }
    return "Chưa xác định";
  }

  return (
    <PageBlock title="Điểm danh trực tiếp (camera-index realtime)">
      {err ? <p className="hint api-error">{err}</p> : null}
      <div className="actions">
        <select
          value={classCode}
          onChange={(e) => {
            setRunning(false);
            setClassCode(e.target.value);
          }}
          aria-label="Lọc lớp khi hiển thị buổi"
        >
          <option value="">Tất cả lớp</option>
          {classes.map((c) => (
            <option key={c.id} value={c.class_code}>
              {c.class_code} — {c.subject_name}
            </option>
          ))}
        </select>
        <button type="button" className="primary" disabled={!classCode || running} onClick={startCamera}>
          Bắt đầu camera
        </button>
        <button
          type="button"
          disabled={!sessionId || stopping}
          onClick={async () => {
            setRunning(false);
            clearLivePreview();
            if (!sessionId) return;
            setStopping(true);
            try {
              await apiFetch(`/api/lecturer/sessions/${encodeURIComponent(sessionId)}/stop-attendance`, {
                method: "POST"
              });
            } catch (e) {
              setErr(e.message);
            } finally {
              setStopping(false);
            }
          }}
        >
          {stopping ? "Đang chốt..." : "Dừng camera & chốt điểm danh"}
        </button>
      </div>
      <div className="live-grid">
        <div>
          <div className="video-wrap">
            <video ref={videoRef} className="live-video" muted playsInline />
            {trackedFaces.map((face, index) => {
              const faceBoxStyle = getFaceBoxStyle(face.face_box);
              if (!faceBoxStyle) return null;
              return (
                <div
                  key={face.track_id || index}
                  className={`face-track-box ${face.confirmed ? "confirmed" : ""}`}
                  style={faceBoxStyle}
                >
                  <span>{getTrackingName(face)}</span>
                  <small>
                    {getTrackingStatus(face)}
                    {face.cosine_score != null ? ` - ${Number(face.cosine_score).toFixed(3)}` : ""}
                  </small>
                </div>
              );
            })}
            <div className="live-overlay">
              {!running ? (
                <span>Camera đã tắt</span>
              ) : latest?.candidate_student ? (
                <>
                  <strong>
                    {latest.candidate_student.student_code} - {latest.candidate_student.full_name}
                  </strong>
                  <span>
                    score: {latest.cosine_score?.toFixed?.(3) ?? latest.cosine_score ?? "-"} |{" "}
                    {latest.confirmed
                      ? "DA DIEM DANH (khong dem hits nua)"
                      : `hits: ${latest.pending_hits ?? 0}/${latest.required_hits ?? 4}`}
                  </span>
                </>
              ) : (
                <span>Chưa nhận diện được sinh viên hợp lệ</span>
              )}
            </div>
          </div>
          <canvas ref={canvasRef} style={{ display: "none" }} />
          <p className="hint">
            Kết quả mới nhất:{" "}
            {!running
              ? "camera đã tắt"
              : latest?.confirmed && latest?.matched_student
              ? `${latest.matched_student.student_code} - ${latest.matched_student.full_name} (DA DIEM DANH)`
              : latest?.candidate_student
              ? `${latest.candidate_student.student_code} - ${latest.candidate_student.full_name} (dang tich luy ${latest.pending_hits ?? 0}/${latest.required_hits ?? 4})`
              : latest?.identity_label || "chưa nhận diện"}
          </p>
          <p className="hint">
            Hệ thống chỉ xác nhận điểm danh khi cùng một sinh viên được nhận diện liên tiếp đủ 4 lần với score &gt;=
            0.9.
          </p>
        </div>
        <div>
          <h4>Đã ghi nhận ({board.present_count || 0})</h4>
          <div className="table-wrap mini">
            <table>
              <tbody>
                {(board.present || []).map((p) => (
                  <tr key={p.student_code}>
                    <td>{p.student_code}</td>
                    <td>{p.full_name}</td>
                    <td>{p.similarity_score ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h4>Chưa ghi nhận ({board.not_present_count || 0})</h4>
          <div className="table-wrap mini">
            <table>
              <tbody>
                {(board.not_present || []).map((p) => (
                  <tr key={p.student_code}>
                    <td>{p.student_code}</td>
                    <td>{p.full_name}</td>
                    <td>{p.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </PageBlock>
  );
}

export function LecturerAttendancePage() {
  const [classes, setClasses] = useState([]);
  const [classCode, setClassCode] = useState("");
  const [sessionDate, setSessionDate] = useState(getTodayDateString());
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState("");

  function formatDuration(seconds) {
    const s = Math.max(0, Number(seconds) || 0);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = Math.floor(s % 60);
    const pad = (v) => String(v).padStart(2, "0");
    return `${pad(h)}:${pad(m)}:${pad(sec)}`;
  }

  function formatClockTime(value) {
    if (!value) return "—";
    const text = String(value);
    const match = text.match(/T(\d{2}:\d{2}:\d{2})/);
    if (match) return match[1];
    return text.slice(0, 8);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await apiFetch("/api/lecturer/course-classes");
        if (!cancelled) {
          setClasses(data || []);
          if (data?.length && !classCode) setClassCode(String(data[0].class_code));
        }
      } catch (e) {
        if (!cancelled) setErr(e.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const q = new URLSearchParams();
        if (classCode) q.set("class_code", classCode);
        if (sessionDate) q.set("session_date", sessionDate);
        const data = await apiFetch(`/api/lecturer/attendance-results?${q.toString()}`);
        const table = (data || []).map((r) => [
          r.class_code ?? "",
          r.session_date ?? "",
          r.student_code ?? "",
          r.full_name ?? "",
          formatClockTime(r.check_in_time), // thời điểm xác nhận điểm danh
          formatClockTime(r.last_seen_at), // thời điểm cuối cùng xuất hiện
          r.status ?? "",
          r.similarity_score != null ? String(r.similarity_score) : "—",
          formatDuration(r.total_seen_seconds)
        ]);
        if (!cancelled) setRows(table);
      } catch (e) {
        if (!cancelled) setErr(e.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [classCode, sessionDate]);

  return (
    <PageBlock title="Kết quả điểm danh (lọc theo lớp và ngày)">
      {err ? <p className="hint api-error">{err}</p> : null}
      <div className="actions">
        <select
          value={classCode}
          onChange={(e) => setClassCode(e.target.value)}
          aria-label="Chọn lớp học phần"
        >
          <option value="">Tất cả lớp</option>
          {classes.map((s) => (
            <option key={s.id} value={s.class_code}>
              {s.class_code} — {s.subject_name}
            </option>
          ))}
        </select>
        <input
          type="date"
          value={sessionDate}
          onChange={(e) => setSessionDate(e.target.value)}
          aria-label="Lọc theo ngày"
        />
        <button type="button" onClick={() => setSessionDate(getTodayDateString())}>
          Hôm nay
        </button>
      </div>
      <DataTable
        headers={[
          "Mã lớp",
          "Ngày",
          "Mã SV",
          "Họ tên",
          "Time xác nhận",
          "Time cuối cùng thấy",
          "Trạng thái",
          "Điểm tương đồng",
          "Thời gian hiện diện (hh:mm:ss)"
        ]}
        rows={rows}
      />
    </PageBlock>
  );
}

export function LecturerReviewRequestsPage() {
  const [requests, setRequests] = useState([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [processingId, setProcessingId] = useState("");
  const [responses, setResponses] = useState({});

  async function loadRequests(cancelledRef = { current: false }) {
    const data = await apiFetch("/api/lecturer/recheck-requests");
    if (!cancelledRef.current) setRequests(data || []);
  }

  useEffect(() => {
    const cancelledRef = { current: false };
    (async () => {
      try {
        await loadRequests(cancelledRef);
      } catch (e) {
        if (!cancelledRef.current) setErr(e.message);
      }
    })();
    return () => {
      cancelledRef.current = true;
    };
  }, []);

  async function processRequest(id, decision) {
    setErr("");
    setMsg("");
    setProcessingId(id);
    try {
      await apiFetch(`/api/lecturer/recheck-requests/${encodeURIComponent(id)}/process`, {
        method: "POST",
        body: JSON.stringify({
          decision,
          response: responses[id]?.trim() || undefined
        })
      });
      setMsg(decision === "APPROVED" ? "Đã chấp nhận yêu cầu." : "Đã từ chối yêu cầu.");
      await loadRequests();
    } catch (e) {
      setErr(e.message);
    } finally {
      setProcessingId("");
    }
  }

  const rows = requests.map((r) => [
    r.class_code ?? "",
    r.subject_name ?? "",
    r.session_date ?? "",
    r.student_code ?? "",
    r.full_name ?? "",
    r.attendance_status ?? "ABSENT",
    r.reason ?? "",
    r.status ?? "",
    r.status === "PENDING" ? (
      <input
        className="inline-input"
        placeholder="Phản hồi cho sinh viên"
        value={responses[r.id] || ""}
        onChange={(e) => setResponses((prev) => ({ ...prev, [r.id]: e.target.value }))}
      />
    ) : (
      r.lecturer_response || "—"
    ),
    r.status === "PENDING" ? (
      <div className="row-actions">
        <button
          type="button"
          className="primary"
          disabled={processingId === r.id}
          onClick={() => processRequest(r.id, "APPROVED")}
        >
          Chấp nhận
        </button>
        <button
          type="button"
          disabled={processingId === r.id}
          onClick={() => processRequest(r.id, "REJECTED")}
        >
          Từ chối
        </button>
      </div>
    ) : (
      "Đã xử lý"
    )
  ]);

  return (
    <PageBlock title="Yêu cầu kiểm tra lại từ sinh viên">
      {err ? <p className="hint api-error">{err}</p> : null}
      {msg ? <p className="hint password-success">{msg}</p> : null}
      <p className="hint">Chấp nhận yêu cầu sẽ cập nhật sinh viên thành PRESENT cho buổi học đó.</p>
      <DataTable
        headers={[
          "Lớp",
          "Môn học",
          "Ngày",
          "Mã SV",
          "Họ tên",
          "Điểm danh hiện tại",
          "Lý do",
          "Trạng thái",
          "Phản hồi",
          "Thao tác"
        ]}
        rows={rows}
      />
    </PageBlock>
  );
}

const reportHeaders = [
  "Mã lớp",
  "Môn học",
  "Ngày",
  "Ca học",
  "Mã SV",
  "Họ tên",
  "Lớp hành chính",
  "Trạng thái",
  "Nguồn",
  "Time xác nhận",
  "Time cuối cùng thấy",
  "Thời gian hiện diện",
  "Điểm tương đồng",
  "Ghi chú"
];

function reportClockTime(value) {
  if (!value) return "—";
  const text = String(value);
  const match = text.match(/T(\d{2}:\d{2}:\d{2})/);
  if (match) return match[1];
  return text.slice(0, 8);
}

function reportDuration(seconds) {
  const s = Math.max(0, Number(seconds) || 0);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  const pad = (v) => String(v).padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(sec)}`;
}

function reportRowsForExport(report) {
  const classInfo = report?.class_info || {};
  return (report?.rows || []).map((r) => [
    classInfo.class_code ?? "",
    classInfo.subject_name ?? "",
    r.session_date ?? "",
    `${String(r.start_time ?? "").slice(0, 5)}-${String(r.end_time ?? "").slice(0, 5)}`,
    r.student_code ?? "",
    r.full_name ?? "",
    r.administrative_class ?? "",
    r.attendance_status ?? "ABSENT",
    r.source ?? "—",
    reportClockTime(r.check_in_time),
    reportClockTime(r.last_seen_at),
    reportDuration(r.total_seen_seconds),
    r.similarity_score != null ? Number(r.similarity_score).toFixed(3) : "—",
    r.note ?? ""
  ]);
}

function downloadTextFile(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function escapeCsvCell(value) {
  const text = String(value ?? "");
  return `"${text.replace(/"/g, '""')}"`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function reportFileBase(report) {
  const classCode = report?.class_info?.class_code || "lop";
  const today = getTodayDateString();
  return `bao-cao-diem-danh-${classCode}-${today}`;
}

function exportReportCsv(report) {
  const rows = reportRowsForExport(report);
  const content = [reportHeaders, ...rows].map((row) => row.map(escapeCsvCell).join(",")).join("\n");
  downloadTextFile(`${reportFileBase(report)}.csv`, `\ufeff${content}`, "text/csv;charset=utf-8");
}

function buildReportHtml(report) {
  const classInfo = report?.class_info || {};
  const summary = report?.summary || {};
  const rows = reportRowsForExport(report);
  const byStatus = summary.by_status || {};
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Báo cáo điểm danh ${escapeHtml(classInfo.class_code || "")}</title>
  <style>
    body { font-family: Arial, sans-serif; color: #0f172a; }
    h1 { font-size: 20px; margin-bottom: 4px; }
    p { margin: 4px 0; }
    table { width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 12px; }
    th, td { border: 1px solid #cbd5e1; padding: 6px; text-align: left; }
    th { background: #e2e8f0; }
  </style>
</head>
<body>
  <h1>Báo cáo điểm danh</h1>
  <p><strong>Lớp:</strong> ${escapeHtml(classInfo.class_code)} - ${escapeHtml(classInfo.subject_name)}</p>
  <p><strong>Tên lớp:</strong> ${escapeHtml(classInfo.class_name || "")}</p>
  <p><strong>Số buổi:</strong> ${summary.session_count ?? 0} | <strong>Sĩ số:</strong> ${summary.student_count ?? 0} | <strong>Present:</strong> ${byStatus.PRESENT ?? 0} | <strong>Absent:</strong> ${byStatus.ABSENT ?? 0}</p>
  <table>
    <thead><tr>${reportHeaders.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr></thead>
    <tbody>
      ${rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}
    </tbody>
  </table>
</body>
</html>`;
}

function exportReportExcel(report) {
  downloadTextFile(
    `${reportFileBase(report)}.xls`,
    buildReportHtml(report),
    "application/vnd.ms-excel;charset=utf-8"
  );
}

function exportReportPdf(report) {
  const win = window.open("", "_blank");
  if (!win) return;
  win.document.write(buildReportHtml(report));
  win.document.close();
  win.focus();
  win.print();
}

export function LecturerReportsPage() {
  const [classes, setClasses] = useState([]);
  const [classCode, setClassCode] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [report, setReport] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await apiFetch("/api/lecturer/course-classes");
        if (!cancelled) setClasses(data || []);
      } catch (e) {
        if (!cancelled) setErr(e.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function loadReport() {
    if (!classCode) {
      setErr("Vui lòng chọn lớp học phần trước khi xuất báo cáo.");
      return;
    }
    setErr("");
    setLoading(true);
    try {
      const q = new URLSearchParams({ class_code: classCode });
      if (fromDate) q.set("from_date", fromDate);
      if (toDate) q.set("to_date", toDate);
      const data = await apiFetch(`/api/lecturer/reports/attendance?${q.toString()}`);
      setReport(data);
    } catch (e) {
      setErr(e.message);
      setReport(null);
    } finally {
      setLoading(false);
    }
  }

  const rows = reportRowsForExport(report).slice(0, 100);
  const summary = report?.summary || {};
  const byStatus = summary.by_status || {};
  const canExport = Boolean(report && report.rows?.length);

  return (
    <PageBlock title="Báo cáo điểm danh">
      {err ? <p className="hint api-error">{err}</p> : null}
      <p className="hint report-intro">
        Chọn lớp học phần trước, sau đó tải dữ liệu và xuất file theo định dạng cần dùng.
      </p>

      <div className="report-card">
        <div className="report-filters-grid">
          <div className="report-field report-field--class">
            <label htmlFor="report-class-select">Lớp học phần</label>
            <select
              id="report-class-select"
              value={classCode}
              onChange={(e) => {
                setClassCode(e.target.value);
                setReport(null);
              }}
              aria-label="Chọn lớp học phần để xuất báo cáo"
            >
              <option value="">Chọn lớp cần xuất</option>
              {classes.map((c) => (
                <option key={c.id} value={c.class_code}>
                  {c.class_code} — {c.subject_name}
                </option>
              ))}
            </select>
          </div>
          <div className="report-field">
            <label htmlFor="report-from-date">Ngày bắt đầu</label>
            <input
              id="report-from-date"
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              aria-label="Ngày bắt đầu"
            />
          </div>
          <div className="report-field">
            <label htmlFor="report-to-date">Ngày kết thúc</label>
            <input
              id="report-to-date"
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              aria-label="Ngày kết thúc"
            />
          </div>
          <div className="report-field report-field--actions">
            <span className="report-actions-spacer" aria-hidden="true" />
            <button
              id="report-load-btn"
              type="button"
              className="report-load-btn"
              disabled={loading}
              onClick={loadReport}
              aria-label="Tải dữ liệu báo cáo điểm danh"
            >
              {loading ? "Đang tải…" : "Tải báo cáo"}
            </button>
          </div>
        </div>

        <div className="report-export-bar">
          <span className="report-export-title">Xuất file</span>
          <div className="report-export-buttons">
            <button
              type="button"
              className="report-export-btn report-export-btn--excel"
              disabled={!canExport}
              onClick={() => exportReportExcel(report)}
            >
              Xuất Excel
            </button>
            <button
              type="button"
              className="report-export-btn report-export-btn--csv"
              disabled={!canExport}
              onClick={() => exportReportCsv(report)}
            >
              Xuất CSV
            </button>
            <button
              type="button"
              className="report-export-btn report-export-btn--pdf"
              disabled={!canExport}
              onClick={() => exportReportPdf(report)}
            >
              Xuất PDF
            </button>
          </div>
        </div>
      </div>

      {report ? (
        <div className="report-summary">
          <span>Số buổi: <strong>{summary.session_count ?? 0}</strong></span>
          <span>Sĩ số: <strong>{summary.student_count ?? 0}</strong></span>
          <span>Có mặt: <strong>{byStatus.PRESENT ?? 0}</strong></span>
          <span>Vắng: <strong>{byStatus.ABSENT ?? 0}</strong></span>
          <span>Tổng dòng: <strong>{summary.total_rows ?? 0}</strong></span>
        </div>
      ) : null}

      {report ? (
        <>
          <p className="hint report-preview-hint">Xem trước tối đa 100 dòng đầu tiên trước khi xuất file.</p>
          <DataTable headers={reportHeaders} rows={rows} />
        </>
      ) : null}
    </PageBlock>
  );
}

