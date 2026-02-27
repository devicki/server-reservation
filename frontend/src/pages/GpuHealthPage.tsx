import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  dashboardAPI,
  type GpuInfo,
  type GpuProcessInfo,
  type ServerGpuHealth,
} from '../api/client';
import { useAuth } from '../context/AuthContext';
import Header from '../components/Header';

function formatMib(mib: number | null): string {
  if (mib == null) return '—';
  if (mib >= 1024) return `${(mib / 1024).toFixed(1)} GiB`;
  return `${mib} MiB`;
}

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString('ko-KR', {
    dateStyle: 'short',
    timeStyle: 'short',
    hour12: false,
  });
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
      setError('GPU 사용 정보를 불러올 수 없습니다.');
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
      <Header />

      <div className="gpu-health-content">
        <div className="gpu-health-toolbar">
          <h2>GPU 사용 정보</h2>
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
            SSH가 설정된 활성 서버가 없거나, GPU 정보 수집 대상이 없습니다.
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
              {s.ok && (s.processes?.length ?? 0) > 0 && (
                <div className="gpu-usage-processes">
                  <h4 className="gpu-usage-section-title">GPU 사용 프로세스</h4>
                  <table className="gpu-health-table gpu-process-table">
                    <thead>
                      <tr>
                        <th>GPU</th>
                        <th>PID</th>
                        <th>프로세스</th>
                        <th>vRAM 사용</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(s.processes ?? []).map((proc, idx) => (
                        <tr key={`${proc.gpu_name}-${proc.pid}-${idx}`}>
                          <td>{proc.gpu_name}</td>
                          <td>{proc.pid}</td>
                          <td className="gpu-process-name">{proc.process_name}</td>
                          <td>
                            {proc.used_memory_mib != null
                              ? formatMib(proc.used_memory_mib)
                              : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {s.ok && (s.recent_serve_cases?.length ?? 0) > 0 && (
                <div className="gpu-usage-serve-cases">
                  <h4 className="gpu-usage-section-title">이 서버에서 공유된 LLM Serve 사례</h4>
                  <ul className="gpu-serve-case-list">
                    {(s.recent_serve_cases ?? []).map((c) => (
                      <li key={c.id} className="gpu-serve-case-item">
                        <div className="gpu-serve-case-model">{c.model_name}</div>
                        {c.serve_command_preview && (
                          <pre className="gpu-serve-case-command">{c.serve_command_preview}</pre>
                        )}
                        <span className="gpu-serve-case-date">{formatDate(c.created_at)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
