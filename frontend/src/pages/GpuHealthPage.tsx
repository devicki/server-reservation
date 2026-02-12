import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  dashboardAPI,
  type GpuInfo,
  type ServerGpuHealth,
} from '../api/client';
import { useAuth } from '../context/AuthContext';

function formatMib(mib: number | null): string {
  if (mib == null) return '—';
  if (mib >= 1024) return `${(mib / 1024).toFixed(1)} GiB`;
  return `${mib} MiB`;
}

function GpuRow({ gpu }: { gpu: GpuInfo }) {
  const used = gpu.memory_used_mib ?? 0;
  const total = gpu.memory_total_mib ?? 1;
  const pct = total > 0 ? Math.round((used / total) * 100) : null;
  const utilPct = gpu.utilization_gpu_pct ?? null;
  const temp = gpu.temperature_gpu_c ?? null;

  return (
    <tr>
      <td>{gpu.index}</td>
      <td className="gpu-name">{gpu.name}</td>
      <td>
        {formatMib(gpu.memory_used_mib)} / {formatMib(gpu.memory_total_mib)}
        {pct != null && (
          <span className="gpu-pct-bar-wrap">
            <span
              className="gpu-pct-bar"
              style={{
                width: `${Math.min(100, pct)}%`,
                backgroundColor:
                  pct >= 90
                    ? 'var(--color-danger)'
                    : pct >= 70
                      ? 'var(--color-warning)'
                      : 'var(--color-primary)',
              }}
            />
          </span>
        )}
      </td>
      <td>{utilPct != null ? `${utilPct}%` : '—'}</td>
      <td>
        {temp != null ? (
          <span className={temp >= 85 ? 'gpu-temp-high' : ''}>{temp}°C</span>
        ) : (
          '—'
        )}
      </td>
    </tr>
  );
}

export default function GpuHealthPage() {
  const { user, logout } = useAuth();
  const [servers, setServers] = useState<ServerGpuHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = useCallback(async () => {
    setError(null);
    try {
      const res = await dashboardAPI.gpuHealth();
      setServers(res.data.servers);
    } catch {
      setError('GPU 헬스 정보를 불러올 수 없습니다.');
      setServers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, [fetchHealth]);

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div className="header-left">
          <h1>GPU Server Reservation</h1>
        </div>
        <div className="header-right">
          <Link to="/" className="header-link">
            예약 캘린더
          </Link>
          <Link to="/gpu-health" className="header-link header-link-active">
            GPU 헬스
          </Link>
          <Link to="/feedback" className="header-link">
            의견 게시판
          </Link>
          {user?.role === 'admin' && (
            <>
              <Link to="/servers" className="header-link">
                서버 관리
              </Link>
              <Link to="/users" className="header-link">
                사용자 관리
              </Link>
            </>
          )}
          <span className="user-info">
            {user?.name}
            <span
              className={`role-badge role-${user?.role ?? 'user'}`}
              title="권한"
            >
              {user?.role === 'admin' ? '관리자' : '일반 사용자'}
            </span>
          </span>
          <button className="btn btn-secondary" onClick={logout}>
            Logout
          </button>
        </div>
      </header>

      <div className="gpu-health-content">
        <div className="gpu-health-toolbar">
          <h2>GPU 리소스 현황</h2>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              setLoading(true);
              fetchHealth();
            }}
            disabled={loading}
          >
            {loading ? '새로고침 중…' : '새로고침'}
          </button>
        </div>

        {error && <p className="error-msg">{error}</p>}

        {!error && loading && servers.length === 0 && (
          <p className="muted">불러오는 중…</p>
        )}

        {!error && !loading && servers.length === 0 && (
          <p className="muted">
            SSH가 설정된 활성 서버가 없거나, GPU 헬스 수집 대상이 없습니다.
          </p>
        )}

        <div className="gpu-health-cards">
          {servers.map((s) => (
            <div
              key={s.server_resource_id}
              className={`gpu-health-card ${s.ok ? '' : 'gpu-health-card-error'}`}
            >
              <div className="gpu-health-card-header">
                <span className="gpu-health-server-name">{s.server_name}</span>
                {s.ok ? (
                  <span className="gpu-health-badge ok">수집 완료</span>
                ) : (
                  <span className="gpu-health-badge error">수집 실패</span>
                )}
              </div>
              {!s.ok && s.error_message && (
                <p className="gpu-health-error-msg">{s.error_message}</p>
              )}
              {s.ok && s.gpus.length === 0 && (
                <p className="muted">GPU가 없거나 nvidia-smi 결과가 비어 있습니다.</p>
              )}
              {s.ok && s.gpus.length > 0 && (
                <div className="gpu-health-table-wrap">
                  <table className="gpu-health-table">
                    <thead>
                      <tr>
                        <th>GPU</th>
                        <th>이름</th>
                        <th>vRAM (사용/전체)</th>
                        <th>점유율</th>
                        <th>온도</th>
                      </tr>
                    </thead>
                    <tbody>
                      {s.gpus.map((gpu) => (
                        <GpuRow key={gpu.index} gpu={gpu} />
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
