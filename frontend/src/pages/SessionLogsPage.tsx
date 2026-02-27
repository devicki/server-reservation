import { Fragment, useEffect, useState } from "react";
import { sessionLogsAPI, resourcesAPI, usersAPI, type SessionLogItem } from "../api/client";
import { useAuth } from "../context/AuthContext";
import Header from "../components/Header";

const LIMIT = 20;
const EVENT_LABEL: Record<string, string> = {
  activated: "활성화",
  deactivated: "비활성화",
  error: "오류",
};
const EVENT_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "전체" },
  { value: "activated", label: "활성화" },
  { value: "deactivated", label: "비활성화" },
  { value: "error", label: "오류" },
];

function formatDate(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleString("ko-KR", {
      dateStyle: "short",
      timeStyle: "medium",
      hour12: false,
    });
  } catch {
    return iso;
  }
}

export default function SessionLogsPage() {
  const { user } = useAuth();
  const [items, setItems] = useState<SessionLogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [resources, setResources] = useState<{ id: string; name: string }[]>([]);
  const [users, setUsers] = useState<{ id: string; name: string; email: string }[]>([]);

  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [serverResourceId, setServerResourceId] = useState("");
  const [reservationTitle, setReservationTitle] = useState("");
  const [userId, setUserId] = useState("");
  const [reservationIdFilter, setReservationIdFilter] = useState("");
  const [eventTypeFilter, setEventTypeFilter] = useState<
    "activated" | "deactivated" | "error" | ""
  >("");

  const [offset, setOffset] = useState(0);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    resourcesAPI
      .list()
      .then((res) => {
        if (!cancelled) setResources(res.data.items ?? []);
      })
      .catch(() => {
        if (!cancelled) setResources([]);
      });
    usersAPI
      .list({ limit: 200 })
      .then((res) => {
        if (!cancelled && res.data?.items)
          setUsers(
            res.data.items.map((u: { id: string; name: string; email: string }) => ({
              id: u.id,
              name: u.name,
              email: u.email,
            })),
          );
      })
      .catch(() => {
        if (!cancelled) setUsers([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const fetchList = async () => {
    setLoading(true);
    setError("");
    try {
      const params: Parameters<typeof sessionLogsAPI.list>[0] = {
        limit: LIMIT,
        offset,
      };
      if (reservationIdFilter.trim())
        params.reservation_id = reservationIdFilter.trim();
      if (startDate.trim()) params.start_date = new Date(startDate).toISOString();
      if (endDate.trim()) params.end_date = new Date(endDate).toISOString();
      if (serverResourceId) params.server_resource_id = serverResourceId;
      if (reservationTitle.trim()) params.reservation_title = reservationTitle.trim();
      if (userId) params.user_id = userId;
      if (eventTypeFilter) params.event_type = eventTypeFilter;

      const res = await sessionLogsAPI.list(params);
      setItems(res.data);
    } catch {
      setError("세션 로그를 불러올 수 없습니다.");
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchList();
  }, [offset]);

  const handleApplyFilter = () => {
    setOffset(0);
    fetchList();
  };

  return (
    <div className="dashboard">
      <Header />

      <div className="feedback-content" style={{ maxWidth: "1100px" }}>
        <section className="feedback-section">
          <h2>세션 로그</h2>
          <p className="feedback-desc">
            예약 활성화/비활성화 이벤트 로그 (관리자 전용)
          </p>

          <div className="session-logs-filters">
            <div className="session-logs-filters-row">
              <label className="session-logs-filter-label">일시</label>
              <input
                type="datetime-local"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="form-control session-logs-filter-input"
              />
              <span className="session-logs-filter-sep">~</span>
              <input
                type="datetime-local"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="form-control session-logs-filter-input"
              />
            </div>
            <div className="session-logs-filters-row">
              <label className="session-logs-filter-label">서버</label>
              <select
                value={serverResourceId}
                onChange={(e) => setServerResourceId(e.target.value)}
                className="form-control session-logs-filter-input"
              >
                <option value="">전체</option>
                {resources.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="session-logs-filters-row">
              <label className="session-logs-filter-label">Title</label>
              <input
                type="text"
                placeholder="예약 타이틀 (부분 일치)"
                value={reservationTitle}
                onChange={(e) => setReservationTitle(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleApplyFilter()}
                className="form-control session-logs-filter-input"
              />
            </div>
            <div className="session-logs-filters-row">
              <label className="session-logs-filter-label">예약 사용자</label>
              <select
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                className="form-control session-logs-filter-input"
              >
                <option value="">전체</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name} ({u.email})
                  </option>
                ))}
              </select>
            </div>
            <div className="session-logs-filters-row">
              <label className="session-logs-filter-label">예약 ID</label>
              <input
                type="text"
                placeholder="UUID"
                value={reservationIdFilter}
                onChange={(e) => setReservationIdFilter(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleApplyFilter()}
                className="form-control session-logs-filter-input"
              />
            </div>
            <div className="session-logs-filters-row">
              <label className="session-logs-filter-label">이벤트</label>
              <select
                value={eventTypeFilter}
                onChange={(e) =>
                  setEventTypeFilter(
                    e.target.value as "activated" | "deactivated" | "error" | "",
                  )
                }
                className="form-control session-logs-filter-input"
              >
                {EVENT_OPTIONS.map((opt) => (
                  <option key={opt.value || "all"} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="session-logs-filters-row session-logs-filters-actions">
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleApplyFilter}
              >
                조회
              </button>
            </div>
          </div>

          {error && <div className="error-msg">{error}</div>}

          {loading ? (
            <p className="feedback-loading">불러오는 중...</p>
          ) : (
            <>
              <div className="session-logs-table-wrap">
                <table className="users-table session-logs-table">
                  <thead>
                    <tr>
                      <th>번호</th>
                      <th>일시</th>
                      <th>서버</th>
                      <th>Title</th>
                      <th>예약 사용자</th>
                      <th>예약 ID</th>
                      <th>이벤트</th>
                      <th>상세</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.length === 0 ? (
                      <tr>
                        <td
                          colSpan={8}
                          style={{
                            textAlign: "center",
                            color: "var(--color-text-muted)",
                          }}
                        >
                          로그가 없습니다.
                        </td>
                      </tr>
                    ) : (
                      items.map((log, index) => (
                        <Fragment key={log.id}>
                          <tr>
                            <td className="session-log-no">
                              {offset + index + 1}
                            </td>
                            <td className="session-log-date">
                              {formatDate(log.created_at)}
                            </td>
                            <td className="session-log-server">
                              {log.server_name ?? "-"}
                            </td>
                            <td className="session-log-title">
                              {log.reservation_title ?? "-"}
                            </td>
                            <td className="session-log-user">
                              {log.reservation_user_name ?? "-"}
                            </td>
                            <td className="session-log-reservation-id">
                              {log.reservation_id}
                            </td>
                            <td>
                              <span
                                className={`session-log-badge session-log-badge-${log.event_type}`}
                              >
                                {EVENT_LABEL[log.event_type] ?? log.event_type}
                              </span>
                            </td>
                            <td>
                              {log.details &&
                              Object.keys(log.details).length > 0 ? (
                                <button
                                  type="button"
                                  className="btn btn-secondary"
                                  style={{
                                    fontSize: "0.8rem",
                                    padding: "0.25rem 0.5rem",
                                  }}
                                  onClick={() =>
                                    setExpandedId(
                                      expandedId === log.id ? null : log.id,
                                    )
                                  }
                                >
                                  {expandedId === log.id ? "접기" : "상세"}
                                </button>
                              ) : (
                                "-"
                              )}
                            </td>
                          </tr>
                          {expandedId === log.id && log.details && (
                            <tr key={`${log.id}-detail`}>
                              <td
                                colSpan={8}
                                className="session-log-details-cell"
                              >
                                <pre className="session-log-details-json">
                                  {JSON.stringify(log.details, null, 2)}
                                </pre>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
              <div className="session-logs-pagination">
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={offset === 0 || loading}
                  onClick={() => setOffset((o) => Math.max(0, o - LIMIT))}
                >
                  이전
                </button>
                <span className="session-logs-page-info">
                  {offset + 1}–{offset + items.length}
                </span>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={items.length < LIMIT || loading}
                  onClick={() => setOffset((o) => o + LIMIT)}
                >
                  다음
                </button>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
