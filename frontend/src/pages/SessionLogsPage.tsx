import { Fragment, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { sessionLogsAPI, type SessionLogItem } from '../api/client';
import { useAuth } from '../context/AuthContext';

const LIMIT = 50;
const EVENT_LABEL: Record<string, string> = {
  activated: '활성화',
  deactivated: '비활성화',
  error: '오류',
};

function formatDate(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleString('ko-KR', {
      dateStyle: 'short',
      timeStyle: 'medium',
      hour12: false,
    });
  } catch {
    return iso;
  }
}

export default function SessionLogsPage() {
  const { user, logout } = useAuth();
  const [items, setItems] = useState<SessionLogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [reservationIdFilter, setReservationIdFilter] = useState('');
  const [offset, setOffset] = useState(0);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchList = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await sessionLogsAPI.list({
        reservation_id: reservationIdFilter.trim() || undefined,
        limit: LIMIT,
        offset,
      });
      setItems(res.data);
    } catch {
      setError('세션 로그를 불러올 수 없습니다.');
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
      <header className="dashboard-header">
        <div className="header-left">
          <h1>GPU Server Reservation</h1>
        </div>
        <div className="header-right">
          <Link to="/" className="header-link">예약</Link>
          <Link to="/feedback" className="header-link">의견 게시판</Link>
          <Link to="/servers" className="header-link">서버 관리</Link>
          <Link to="/users" className="header-link">사용자 관리</Link>
          <Link to="/session-logs" className="header-link">세션 로그</Link>
          <span className="user-info">
            {user?.name}
            <span className={`role-badge role-${user?.role ?? 'user'}`} title="권한">
              {user?.role === 'admin' ? '관리자' : '일반 사용자'}
            </span>
          </span>
          <button className="btn btn-secondary" onClick={logout}>
            Logout
          </button>
        </div>
      </header>

      <div className="feedback-content" style={{ maxWidth: '1100px' }}>
        <section className="feedback-section">
          <h2>세션 로그</h2>
          <p className="feedback-desc">
            예약 활성화/비활성화 이벤트 로그 (관리자 전용)
          </p>

          <div className="session-logs-filters">
            <input
              type="text"
              placeholder="예약 ID (UUID) 필터"
              value={reservationIdFilter}
              onChange={(e) => setReservationIdFilter(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleApplyFilter()}
              className="form-control"
              style={{ maxWidth: '320px', marginRight: '0.5rem' }}
            />
            <button type="button" className="btn btn-primary" onClick={handleApplyFilter}>
              조회
            </button>
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
                      <th>일시</th>
                      <th>예약 ID</th>
                      <th>이벤트</th>
                      <th>상세</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.length === 0 ? (
                      <tr>
                        <td colSpan={4} style={{ textAlign: 'center', color: 'var(--color-text-muted)' }}>
                          로그가 없습니다.
                        </td>
                      </tr>
                    ) : (
                      items.map((log) => (
                        <Fragment key={log.id}>
                          <tr>
                            <td className="session-log-date">{formatDate(log.created_at)}</td>
                            <td className="session-log-reservation-id">{log.reservation_id}</td>
                            <td>
                              <span className={`session-log-badge session-log-badge-${log.event_type}`}>
                                {EVENT_LABEL[log.event_type] ?? log.event_type}
                              </span>
                            </td>
                            <td>
                              {log.details && Object.keys(log.details).length > 0 ? (
                                <button
                                  type="button"
                                  className="btn btn-secondary"
                                  style={{ fontSize: '0.8rem', padding: '0.25rem 0.5rem' }}
                                  onClick={() => setExpandedId(expandedId === log.id ? null : log.id)}
                                >
                                  {expandedId === log.id ? '접기' : '상세'}
                                </button>
                              ) : (
                                '-'
                              )}
                            </td>
                          </tr>
                          {expandedId === log.id && log.details && (
                            <tr key={`${log.id}-detail`}>
                              <td colSpan={4} className="session-log-details-cell">
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
