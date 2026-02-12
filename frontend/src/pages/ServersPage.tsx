import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { configAPI, resourcesAPI, type ResourceItem } from "../api/client";
import { useAuth } from "../context/AuthContext";

const emptyForm = {
  name: "",
  description: "",
  capacity: "" as number | "",
  host: "",
  ssh_port: 22,
  ssh_username: "",
  ssh_private_key: "",
  account_exclusions: "",
};

export default function ServersPage() {
  const { user, logout } = useAuth();
  const [items, setItems] = useState<ResourceItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [testResult, setTestResult] = useState<{
    id: string;
    ok: boolean;
    message: string;
  } | null>(null);
  const [permResult, setPermResult] = useState<{
    id: string;
    ok: boolean;
    message?: string | null;
    usermod_ok: boolean;
    pkill_ok: boolean;
    teleport_ok: boolean;
  } | null>(null);
  const [permCheckingId, setPermCheckingId] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [defaultExcludeUsers, setDefaultExcludeUsers] = useState<string[]>([]);

  const fetchConfig = async () => {
    try {
      const res = await configAPI.get();
      setDefaultExcludeUsers(res.data.default_exclude_users ?? []);
    } catch {
      setDefaultExcludeUsers([]);
    }
  };

  const fetchList = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await resourcesAPI.list({ include_inactive: true });
      setItems(res.data.items);
      setTotal(res.data.total);
    } catch {
      setError("서버 목록을 불러올 수 없습니다.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchList();
    fetchConfig();
  }, []);

  const openCreate = () => {
    setEditingId(null);
    setForm(emptyForm);
    setModalOpen(true);
    setTestResult(null);
  };

  const openEdit = async (r: ResourceItem) => {
    setEditingId(r.id);
    setModalOpen(true);
    setTestResult(null);
    setForm({
      name: r.name,
      description: r.description ?? "",
      capacity: r.capacity ?? "",
      host: r.host ?? "",
      ssh_port: r.ssh_port ?? 22,
      ssh_username: r.ssh_username ?? "",
      ssh_private_key: "",
      account_exclusions: r.account_exclusions ?? "",
    });
    try {
      const res = await resourcesAPI.get(r.id);
      const d = res.data;
      setForm({
        name: d.name,
        description: d.description ?? "",
        capacity: d.capacity ?? "",
        host: d.host ?? "",
        ssh_port: d.ssh_port ?? 22,
        ssh_username: d.ssh_username ?? "",
        ssh_private_key: d.ssh_private_key ?? "",
        account_exclusions: d.account_exclusions ?? "",
      });
    } catch {
      setError("서버 정보를 불러올 수 없습니다.");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const payload: {
        name: string;
        description?: string;
        capacity?: number;
        host?: string;
        ssh_port?: number;
        ssh_username?: string;
        ssh_private_key?: string;
        account_exclusions?: string;
      } = {
        name: form.name.trim(),
        description: form.description.trim() || undefined,
        capacity: form.capacity === "" ? undefined : Number(form.capacity),
        host: form.host.trim() || undefined,
        ssh_port: form.ssh_port,
        ssh_username: form.ssh_username.trim() || undefined,
        account_exclusions: form.account_exclusions.trim() || undefined,
      };
      if (form.ssh_private_key.trim()) {
        payload.ssh_private_key = form.ssh_private_key.trim();
      }
      if (editingId) {
        await resourcesAPI.update(editingId, payload);
      } else {
        await resourcesAPI.create(payload);
      }
      setModalOpen(false);
      await fetchList();
    } catch (err: unknown) {
      const detail =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string | string[] } } })
              .response?.data?.detail
          : undefined;
      const message = Array.isArray(detail)
        ? detail[0]
        : typeof detail === "string"
          ? detail
          : editingId
            ? "수정에 실패했습니다."
            : "등록에 실패했습니다.";
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleActiveToggle = async (id: string, is_active: boolean) => {
    setTogglingId(id);
    setError("");
    try {
      await resourcesAPI.update(id, { is_active });
      await fetchList();
      if (editingId === id) setModalOpen(false);
    } catch {
      setError("상태 변경에 실패했습니다.");
    } finally {
      setTogglingId(null);
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`"${name}" 서버를 비활성화(삭제)하시겠습니까?`)) return;
    setError("");
    try {
      await resourcesAPI.delete(id);
      await fetchList();
      if (editingId === id) setModalOpen(false);
    } catch {
      setError("삭제에 실패했습니다.");
    }
  };

  const handleTestConnection = async (id: string) => {
    setTestResult(null);
    try {
      const res = await resourcesAPI.testConnection(id);
      setTestResult({
        id,
        ok: res.data.ok,
        message: res.data.message,
      });
    } catch {
      setTestResult({ id, ok: false, message: "연결 테스트 요청 실패" });
    }
  };

  const handleCheckPermissions = async (id: string) => {
    setPermResult(null);
    setPermCheckingId(id);
    try {
      const res = await resourcesAPI.checkPermissions(id);
      setPermResult({
        id,
        ok: res.data.ok,
        message: res.data.message ?? undefined,
        usermod_ok: res.data.usermod_ok,
        pkill_ok: res.data.pkill_ok,
        teleport_ok: res.data.teleport_ok,
      });
    } catch {
      setPermResult({
        id,
        ok: false,
        message: "권한 확인 요청 실패",
        usermod_ok: false,
        pkill_ok: false,
        teleport_ok: false,
      });
    } finally {
      setPermCheckingId(null);
    }
  };

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div className="header-left">
          <h1>GPU Server Reservation</h1>
        </div>
        <div className="header-right">
          <Link to="/" className="header-link">
            예약
          </Link>
          <Link to="/feedback" className="header-link">
            의견 게시판
          </Link>
          <Link to="/users" className="header-link">
            사용자 관리
          </Link>
          <Link to="/session-logs" className="header-link">
            세션 로그
          </Link>
          <span className="user-info">
            {user?.name}
            <span
              className={`role-badge role-${user?.role ?? "user"}`}
              title="권한"
            >
              {user?.role === "admin" ? "관리자" : "일반 사용자"}
            </span>
          </span>
          <button className="btn btn-secondary" onClick={logout}>
            Logout
          </button>
        </div>
      </header>

      <div className="feedback-content" style={{ maxWidth: "1000px" }}>
        <section className="feedback-section">
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "0.75rem",
            }}
          >
            <div>
              <h2>서버 관리</h2>
              <p className="feedback-desc">
                스케줄링 대상 서버 등록/삭제 및 SSH 연결 정보 설정 (관리자 전용)
              </p>
            </div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={openCreate}
            >
              + 서버 등록
            </button>
          </div>

          {error && <div className="error-msg">{error}</div>}

          {defaultExcludeUsers.length > 0 && (
            <div className="servers-default-exclude">
              <h3 className="servers-default-exclude-heading">
                시스템 기본 예외 (수정·삭제 불가)
              </h3>
              <p className="feedback-desc">
                아래 계정은 모든 서버에서 예약 계정 선택 목록에 항상 제외됩니다.
              </p>
              <div className="servers-default-exclude-list" role="list">
                {defaultExcludeUsers.map((name) => (
                  <span
                    key={name}
                    className="servers-default-exclude-tag"
                    title="시스템 기본 예외 (수정 불가)"
                  >
                    {name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {loading ? (
            <p className="feedback-loading">불러오는 중...</p>
          ) : (
            <>
              <p className="feedback-desc" style={{ marginBottom: "1rem" }}>
                총 {total}개 서버
              </p>
              <div className="users-table-wrap">
                <table className="users-table">
                  <thead>
                    <tr>
                      <th>이름</th>
                      <th>호스트</th>
                      <th>SSH 사용자</th>
                      <th>상태</th>
                      <th>작업</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((r) => (
                      <tr key={r.id}>
                        <td>{r.name}</td>
                        <td>{r.host || "—"}</td>
                        <td>{r.ssh_username || "—"}</td>
                        <td>
                          <span
                            className={`users-status-badge ${
                              r.is_active
                                ? "users-status-active"
                                : "users-status-inactive"
                            }`}
                          >
                            {r.is_active ? "활성" : "비활성"}
                          </span>
                        </td>
                        <td>
                          <div className="servers-actions">
                            <button
                              type="button"
                              className="btn btn-secondary"
                              style={{
                                fontSize: "0.8rem",
                                padding: "0.35rem 0.6rem",
                              }}
                              onClick={() => handleTestConnection(r.id)}
                              title="SSH 연결 테스트"
                            >
                              연결 테스트
                            </button>
                            {testResult?.id === r.id && (
                              <span
                                className={
                                  testResult.ok
                                    ? "servers-test-ok"
                                    : "servers-test-fail"
                                }
                              >
                                {testResult.ok
                                  ? "✓ 성공"
                                  : `✗ ${testResult.message}`}
                              </span>
                            )}
                            <button
                              type="button"
                              className="btn btn-secondary"
                              style={{
                                fontSize: "0.8rem",
                                padding: "0.35rem 0.6rem",
                              }}
                              onClick={() => handleCheckPermissions(r.id)}
                              disabled={permCheckingId === r.id}
                              title="SSH 사용자의 usermod, pkill, teleport 실행 권한 확인"
                            >
                              {permCheckingId === r.id
                                ? "확인 중..."
                                : "권한 확인"}
                            </button>
                            <button
                              type="button"
                              className="btn btn-secondary"
                              style={{
                                fontSize: "0.8rem",
                                padding: "0.35rem 0.6rem",
                              }}
                              onClick={() => openEdit(r)}
                            >
                              수정
                            </button>
                            <button
                              type="button"
                              className={
                                r.is_active
                                  ? "btn btn-secondary servers-toggle-btn"
                                  : "btn btn-primary servers-toggle-btn"
                              }
                              onClick={() =>
                                handleActiveToggle(r.id, !r.is_active)
                              }
                              disabled={togglingId === r.id}
                            >
                              {togglingId === r.id
                                ? "처리 중..."
                                : r.is_active
                                  ? "비활성화"
                                  : "활성화"}
                            </button>
                            <button
                              type="button"
                              className="btn btn-danger"
                              style={{
                                fontSize: "0.8rem",
                                padding: "0.35rem 0.6rem",
                              }}
                              onClick={() => handleDelete(r.id, r.name)}
                              disabled={!r.is_active}
                            >
                              삭제
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <section className="servers-permission-section">
                <h3 className="servers-permission-heading">권한 확인 결과</h3>
                <p className="feedback-desc">
                  아래에서 「권한 확인」 버튼으로 확인한 SSH 사용자(usermod, pkill,
                  teleport) 실행 권한 결과를 확인할 수 있습니다.
                </p>
                {permResult ? (
                  <div
                    className={
                      permResult.ok
                        ? "servers-permission-card"
                        : "servers-permission-card servers-permission-card-error"
                    }
                  >
                    <div className="servers-permission-card-header">
                      <span className="servers-permission-server-name">
                        {items.find((s) => s.id === permResult.id)?.name ??
                          permResult.id}
                      </span>
                      {!permResult.ok && permResult.message && (
                        <span className="servers-permission-msg">
                          {permResult.message}
                        </span>
                      )}
                    </div>
                    {permResult.ok && (
                      <ul className="servers-permission-list">
                        <li>
                          usermod (계정 잠금 등):{" "}
                          {permResult.usermod_ok ? (
                            <span className="servers-perm-ok">✓ 권한 있음</span>
                          ) : (
                            <span className="servers-perm-fail">
                              ✗ 권한 없음
                            </span>
                          )}
                        </li>
                        <li>
                          pkill (프로세스 종료):{" "}
                          {permResult.pkill_ok ? (
                            <span className="servers-perm-ok">✓ 권한 있음</span>
                          ) : (
                            <span className="servers-perm-fail">
                              ✗ 권한 없음
                            </span>
                          )}
                        </li>
                        <li>
                          teleport:{" "}
                          {permResult.teleport_ok ? (
                            <span className="servers-perm-ok">✓ 권한 있음</span>
                          ) : (
                            <span className="servers-perm-fail">
                              ✗ 권한 없음
                            </span>
                          )}
                        </li>
                      </ul>
                    )}
                  </div>
                ) : (
                  <p className="muted servers-permission-placeholder">
                    서버 목록에서 「권한 확인」을 실행하면 결과가 여기에
                    표시됩니다.
                  </p>
                )}
              </section>
            </>
          )}
        </section>
      </div>

      {modalOpen && (
        <div className="modal-overlay" onClick={() => setModalOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{editingId ? "서버 수정" : "서버 등록"}</h2>
              <button
                type="button"
                className="modal-close"
                onClick={() => setModalOpen(false)}
              >
                &times;
              </button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label>이름 *</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, name: e.target.value }))
                  }
                  required
                  placeholder="예: GPU Server A"
                />
              </div>
              <div className="form-group">
                <label>설명</label>
                <input
                  type="text"
                  value={form.description}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, description: e.target.value }))
                  }
                  placeholder="서버 설명"
                />
              </div>
              <div className="form-group">
                <label>용량 (선택)</label>
                <input
                  type="number"
                  min={1}
                  value={form.capacity === "" ? "" : form.capacity}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      capacity:
                        e.target.value === "" ? "" : Number(e.target.value),
                    }))
                  }
                  placeholder="숫자"
                />
              </div>
              <div className="form-group">
                <label>호스트 (IP 또는 도메인)</label>
                <input
                  type="text"
                  value={form.host}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, host: e.target.value }))
                  }
                  placeholder="192.168.1.10 또는 server.example.com"
                />
              </div>
              <div className="form-group">
                <label>SSH 포트</label>
                <input
                  type="number"
                  min={1}
                  max={65535}
                  value={form.ssh_port}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      ssh_port: Number(e.target.value) || 22,
                    }))
                  }
                />
              </div>
              <div className="form-group">
                <label>SSH 사용자명</label>
                <input
                  type="text"
                  value={form.ssh_username}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, ssh_username: e.target.value }))
                  }
                  placeholder="예: root, ubuntu"
                />
              </div>
              <div className="form-group">
                <label>SSH 개인 키 (PEM)</label>
                <textarea
                  value={form.ssh_private_key}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, ssh_private_key: e.target.value }))
                  }
                  placeholder="-----BEGIN ... END ...-----"
                  rows={4}
                  className="modal-description-input"
                />
                <p className="form-hint">
                  원격 명령 실행(getent 등)에 사용됩니다. 수정 시에만 변경된
                  값이 저장됩니다.
                </p>
              </div>
              {defaultExcludeUsers.length > 0 && (
                <div className="form-group">
                  <label>시스템 기본 예외 (수정·삭제 불가)</label>
                  <div className="servers-default-exclude-list servers-default-exclude-list-inline">
                    {defaultExcludeUsers.map((name) => (
                      <span
                        key={name}
                        className="servers-default-exclude-tag"
                        title="시스템 기본 예외"
                      >
                        {name}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              <div className="form-group">
                <label>서버 계정 예외 (추가 제외할 계정)</label>
                <textarea
                  value={form.account_exclusions}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      account_exclusions: e.target.value,
                    }))
                  }
                  placeholder="시스템 기본 예외 외에 이 서버에서만 추가로 제외할 OS 계정명 (한 줄에 하나 또는 쉼표 구분)"
                  rows={2}
                  className="modal-description-input"
                />
                <p className="form-hint">
                  시스템 기본 예외에 더해, 위에 입력한 계정만 이 서버 예약
                  목록에서 제외됩니다.
                </p>
              </div>
              <div className="modal-actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setModalOpen(false)}
                >
                  취소
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={submitting}
                >
                  {submitting ? "처리 중..." : editingId ? "저장" : "등록"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
