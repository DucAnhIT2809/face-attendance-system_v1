import { useEffect, useState } from "react";
import { apiFetch } from "../api/client";
import { DataTable, PageBlock, StatCards } from "../components/Common";

export function StudentDashboardPage() {
  const [me, setMe] = useState(null);
  const [faces, setFaces] = useState([]);
  const [history, setHistory] = useState([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [m, f, h] = await Promise.all([
          apiFetch("/api/student/me"),
          apiFetch("/api/student/face-images"),
          apiFetch("/api/student/attendance-history")
        ]);
        if (!cancelled) {
          setMe(m);
          setFaces(f || []);
          setHistory(h || []);
        }
      } catch (e) {
        if (!cancelled) setErr(e.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const validFaces = faces.filter((x) => x.status === "VALID").length;
  const cards = me
    ? [
        { title: "Mã sinh viên", value: me.student_code ?? "—" },
        { title: "Họ tên", value: me.full_name ?? "—" },
        { title: "Ảnh đã upload", value: String(faces.length) },
        { title: "Ảnh hợp lệ", value: String(validFaces) }
      ]
    : [
        { title: "Mã sinh viên", value: "…" },
        { title: "Họ tên", value: "…" },
        { title: "Ảnh", value: "…" },
        { title: "Trạng thái", value: err ? "Lỗi" : "Đang tải" }
      ];

  return (
    <section className="panel-list">
      {err ? <p className="hint api-error">{err}</p> : null}
      <StatCards cards={cards} />
      <PageBlock title="Tóm tắt">
        <p className="hint">
          Số buổi đã có trong lịch sử: <strong>{history.length}</strong>
        </p>
      </PageBlock>
    </section>
  );
}

export function StudentInfoPage() {
  const [me, setMe] = useState(null);
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const m = await apiFetch("/api/student/me");
        if (!cancelled) {
          setMe(m);
          setEmail(m?.email || "");
          setPhone(m?.phone || "");
        }
      } catch (e) {
        if (!cancelled) setErr(e.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (err) return <PageBlock title="Thông tin cá nhân"><p className="hint api-error">{err}</p></PageBlock>;
  if (!me) return <PageBlock title="Thông tin cá nhân"><p className="hint">Đang tải…</p></PageBlock>;

  return (
    <PageBlock title="Thông tin cá nhân">
      <div className="info-grid">
        <p>
          <span>Mã SV:</span> {me.student_code}
        </p>
        <p>
          <span>Họ tên:</span> {me.full_name}
        </p>
        <p>
          <span>Lớp hành chính:</span> {me.administrative_class ?? "—"}
        </p>
        <p>
          <span>Email:</span>{" "}
          <input
            className="inline-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email@domain.com"
          />
        </p>
        <p>
          <span>SĐT:</span>{" "}
          <input
            className="inline-input"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="Số điện thoại"
          />
        </p>
        <p>
          <span>Trạng thái:</span> {me.student_status ?? "—"}
        </p>
      </div>
      <div className="actions">
        <button
          type="button"
          className="primary"
          disabled={saving}
          onClick={async () => {
            setMsg("");
            setErr("");
            setSaving(true);
            try {
              const updated = await apiFetch("/api/student/me", {
                method: "PATCH",
                body: JSON.stringify({ email, phone })
              });
              setMe((prev) => ({ ...prev, ...updated }));
              setMsg("Đã cập nhật thông tin.");
            } catch (e) {
              setErr(e.message);
            } finally {
              setSaving(false);
            }
          }}
        >
          {saving ? "Đang lưu..." : "Lưu thay đổi"}
        </button>
        {msg ? <span className="hint">{msg}</span> : null}
      </div>
    </PageBlock>
  );
}

export function StudentFacePage() {
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState("");
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);

  async function refresh() {
    const data = await apiFetch("/api/student/face-images");
    const table = (data || []).map((r) => [
      String(r.image_path ?? "").split("/").slice(-1)[0],
      r.status ?? "",
      r.image_type ?? "",
      r.is_used_for_training ? "Có" : "Không",
      String(r.uploaded_at ?? "")
    ]);
    setRows(table);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await refresh();
      } catch (e) {
        if (!cancelled) setErr(e.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <PageBlock title="Ảnh khuôn mặt">
      {err ? <p className="hint api-error">{err}</p> : null}
      <p className="hint">
        Yêu cầu ảnh rõ mặt, không khẩu trang, không tối/mờ, nên upload 5-10 ảnh.
      </p>
      <div className="actions">
        <input
          type="file"
          accept="image/*"
          multiple
          onChange={(e) => setFiles(Array.from(e.target.files || []))}
        />
        <button
          type="button"
          className="primary"
          disabled={uploading || files.length === 0}
          onClick={async () => {
            setErr("");
            setUploading(true);
            try {
              const fd = new FormData();
              files.forEach((f) => fd.append("files", f));
              await apiFetch("/api/student/face-images", { method: "POST", body: fd });
              setFiles([]);
              await refresh();
            } catch (e) {
              setErr(e.message);
            } finally {
              setUploading(false);
            }
          }}
        >
          {uploading ? "Đang tải..." : `Tải lên (${files.length})`}
        </button>
        <button type="button" disabled={uploading} onClick={() => setFiles([])}>
          Xóa chọn
        </button>
      </div>
      {files.length ? (
        <p className="hint">Đã chọn: {files.map((f) => f.name).join(", ")}</p>
      ) : null}
      <DataTable
        headers={["Tên file", "Trạng thái", "Loại", "Training", "Ngày tải"]}
        rows={rows}
      />
    </PageBlock>
  );
}

export function StudentHistoryPage() {
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await apiFetch("/api/student/attendance-history");
        const table = (data || []).map((r) => [
          r.subject_name ?? r.class_name ?? "",
          String(r.session_date ?? ""),
          r.status ?? "",
          r.check_in_time ?? "—"
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
    <PageBlock title="Lịch sử điểm danh cá nhân">
      {err ? <p className="hint api-error">{err}</p> : null}
      <DataTable
        headers={["Môn / lớp", "Ngày", "Trạng thái", "Giờ ghi nhận"]}
        rows={rows}
      />
    </PageBlock>
  );
}

export function StudentJoinClassesPage() {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState([]);
  const [mine, setMine] = useState([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(false);
  const [busyClass, setBusyClass] = useState("");

  async function refreshMine() {
    const data = await apiFetch("/api/student/course-class-join-requests");
    setMine(data || []);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await apiFetch("/api/student/course-class-join-requests");
        if (!cancelled) setMine(data || []);
      } catch (e) {
        if (!cancelled) setErr(e.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function search() {
    setErr("");
    setMsg("");
    const term = q.trim();
    if (term.length < 1) {
      setErr("Nhập ít nhất một ký tự để tìm (mã lớp, mã học phần, tên môn, giảng viên…).");
      return;
    }
    setLoading(true);
    try {
      const data = await apiFetch(
        `/api/student/course-classes/search?q=${encodeURIComponent(term)}&limit=50`
      );
      setHits(data || []);
      if (!(data || []).length) setMsg("Không có lớp phù hợp (hoặc bạn đã tham gia / đang chờ duyệt).");
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function requestJoin(courseClassId) {
    const message = window.prompt("Lời nhắn cho giảng viên (tùy chọn, Enter để bỏ qua)") ?? "";
    setBusyClass(String(courseClassId));
    setErr("");
    setMsg("");
    try {
      await apiFetch("/api/student/course-class-join-requests", {
        method: "POST",
        body: JSON.stringify({
          course_class_id: courseClassId,
          message: message.trim() || null
        })
      });
      setMsg("Đã gửi yêu cầu tham gia lớp.");
      setHits((prev) => prev.filter((h) => String(h.id) !== String(courseClassId)));
      await refreshMine();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusyClass("");
    }
  }

  async function cancelRequest(requestId) {
    if (!window.confirm("Hủy yêu cầu tham gia lớp này?")) return;
    setErr("");
    setMsg("");
    try {
      await apiFetch(`/api/student/course-class-join-requests/${requestId}`, { method: "DELETE" });
      setMsg("Đã hủy yêu cầu.");
      await refreshMine();
    } catch (e) {
      setErr(e.message);
    }
  }

  return (
    <PageBlock title="Tham gia lớp học phần">
      {err ? <p className="hint api-error">{err}</p> : null}
      {msg ? <p className="hint password-success">{msg}</p> : null}
      <p className="hint">
        Tìm theo mã lớp, mã học phần, tên môn, tên/mã giảng viên, học kỳ hoặc năm học. Các lớp bạn đã tham gia hoặc
        đang chờ duyệt sẽ không hiển thị trong kết quả.
      </p>
      <div className="actions join-search">
        <input
          placeholder="VD: INT1481, 13094, Lập trình Web…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") search();
          }}
          aria-label="Từ khóa tìm lớp"
        />
        <button type="button" className="primary" disabled={loading} onClick={search}>
          {loading ? "Đang tìm..." : "Tìm lớp"}
        </button>
      </div>

      {hits.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Mã lớp</th>
                <th>Mã HP</th>
                <th>Tên học phần</th>
                <th>Học kỳ / năm</th>
                <th>Giảng viên</th>
                <th>Sĩ số</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {hits.map((h) => (
                <tr key={h.id}>
                  <td>{h.class_code}</td>
                  <td>{h.subject_code}</td>
                  <td>{h.subject_name}</td>
                  <td>
                    {h.semester} {h.school_year}
                  </td>
                  <td>
                    {h.lecturer_name}
                    <div className="hint">{h.lecturer_code}</div>
                  </td>
                  <td>{h.student_count}</td>
                  <td>
                    <button
                      type="button"
                      className="primary"
                      disabled={busyClass === String(h.id)}
                      onClick={() => requestJoin(h.id)}
                    >
                      Gửi yêu cầu
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <h4 className="subpanel-title">Yêu cầu của tôi</h4>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Trạng thái</th>
              <th>Lớp / môn</th>
              <th>Lời nhắn</th>
              <th>Phản hồi GV</th>
              <th>Thời gian</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {mine.map((r) => (
              <tr key={r.id}>
                <td>{r.status}</td>
                <td>
                  {r.class_code} — {r.subject_name}
                </td>
                <td>{r.message ?? "—"}</td>
                <td>{r.lecturer_note ?? "—"}</td>
                <td className="hint">{String(r.created_at ?? "").slice(0, 19)}</td>
                <td>
                  {r.status === "PENDING" ? (
                    <button type="button" onClick={() => cancelRequest(r.id)}>
                      Hủy yêu cầu
                    </button>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!mine.length ? <p className="hint">Chưa có yêu cầu tham gia lớp.</p> : null}
    </PageBlock>
  );
}

export function StudentReviewPage() {
  const [sessions, setSessions] = useState([]);
  const [requests, setRequests] = useState([]);
  const [sessionId, setSessionId] = useState("");
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [sending, setSending] = useState(false);

  async function loadData(cancelledRef = { current: false }) {
    const [eligible, sent] = await Promise.all([
      apiFetch("/api/student/recheck-eligible-sessions"),
      apiFetch("/api/student/recheck-requests")
    ]);
    if (cancelledRef.current) return;
    setSessions(eligible || []);
    setRequests(sent || []);
    if (eligible?.length && !sessionId) setSessionId(String(eligible[0].session_id));
  }

  useEffect(() => {
    const cancelledRef = { current: false };
    (async () => {
      try {
        await loadData(cancelledRef);
      } catch (e) {
        if (!cancelledRef.current) setErr(e.message);
      }
    })();
    return () => {
      cancelledRef.current = true;
    };
  }, []);

  async function submitRequest() {
    setErr("");
    setMsg("");
    if (!sessionId || !reason.trim()) {
      setErr("Chọn buổi học và nhập lý do kiểm tra lại.");
      return;
    }
    setSending(true);
    try {
      await apiFetch("/api/student/recheck-requests", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, reason: reason.trim() })
      });
      setReason("");
      setMsg("Đã gửi yêu cầu kiểm tra lại.");
      await loadData();
    } catch (e) {
      setErr(e.message);
    } finally {
      setSending(false);
    }
  }

  const requestRows = requests.map((r) => [
    r.class_code ?? "",
    r.subject_name ?? "",
    r.session_date ?? "",
    r.reason ?? "",
    r.status ?? "",
    r.lecturer_response ?? "—"
  ]);

  return (
    <PageBlock title="Gửi yêu cầu kiểm tra lại">
      {err ? <p className="hint api-error">{err}</p> : null}
      {msg ? <p className="hint password-success">{msg}</p> : null}
      <div className="actions">
        <select value={sessionId} onChange={(e) => setSessionId(e.target.value)}>
          {sessions.map((s) => (
            <option
              key={s.session_id}
              value={s.session_id}
              disabled={Boolean(s.existing_request_id)}
            >
              {s.session_date} — {s.class_code} — {s.subject_name} ({s.attendance_status}
              {s.request_status ? `, đang chờ xử lý` : ""})
            </option>
          ))}
        </select>
        <input
          placeholder="Lý do kiểm tra lại điểm danh"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <button type="button" className="primary" disabled={sending} onClick={submitRequest}>
          {sending ? "Đang gửi..." : "Gửi yêu cầu"}
        </button>
      </div>
      <DataTable
        headers={["Lớp", "Môn học", "Ngày", "Lý do", "Trạng thái", "Phản hồi"]}
        rows={requestRows}
      />
    </PageBlock>
  );
}

export function StudentNotificationsPage() {
  return (
    <PageBlock title="Thông báo">
      <p className="hint">API thông báo sẽ kết nối bảng notifications sau.</p>
    </PageBlock>
  );
}
