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
