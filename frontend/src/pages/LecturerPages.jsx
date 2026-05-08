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
        { title: "Buổi học / điểm danh", value: String(summary.session_count) },
        { title: "Ghi chú", value: "Dữ liệu từ PostgreSQL" }
      ]
    : [
        { title: "Lớp học phần", value: "…" },
        { title: "Sinh viên", value: "…" },
        { title: "Buổi học", value: "…" },
        { title: "Trạng thái", value: err ? "Lỗi" : "Đang tải" }
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

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await apiFetch("/api/lecturer/course-classes");
        const table = (data || []).map((r) => [
          r.class_code ?? "",
          r.subject_name ?? "",
          r.class_name ?? "",
          String(r.student_count ?? 0),
          `${r.semester ?? ""} ${r.school_year ?? ""}`.trim()
        ]);
        if (!cancelled) setRows(table);
      } catch (e) {
        if (!cancelled) setErr(e.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <PageBlock title="Danh sách lớp học phần">
      {err ? <p className="hint api-error">{err}</p> : null}
      <DataTable
        headers={["Mã lớp", "Môn học", "Tên lớp HP", "Sĩ số", "Học kỳ / năm"]}
        rows={rows}
      />
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
          `/api/recognize/realtime-frame?session_id=${encodeURIComponent(sessionId)}&threshold=0.85`,
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
            0.85.
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

export function LecturerReportsPage() {
  return (
    <PageBlock title="Báo cáo điểm danh">
      <div className="actions">
        <button type="button" className="primary">
          Xuất Excel
        </button>
        <button type="button">Xuất CSV</button>
        <button type="button">Xuất PDF</button>
      </div>
    </PageBlock>
  );
}

