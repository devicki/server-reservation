import { useEffect, useState } from 'react';
import { dashboardAPI } from '../api/client';

interface ResourceStatus {
  id: string;
  name: string;
  current_status: 'in_use' | 'reserved' | 'available';
  current_reservation: {
    title: string;
    user_name: string;
    end_at: string;
  } | null;
  next_reservation: {
    title: string;
    user_name: string;
    start_at: string;
  } | null;
}

const STATUS_LABELS: Record<string, { label: string; className: string }> = {
  in_use: { label: 'In Use', className: 'status-in-use' },
  reserved: { label: 'Reserved', className: 'status-reserved' },
  available: { label: 'Available', className: 'status-available' },
};

export default function ServerStatus() {
  const [statuses, setStatuses] = useState<ResourceStatus[]>([]);

  useEffect(() => {
    const fetch = async () => {
      try {
        const res = await dashboardAPI.status();
        setStatuses(res.data.resources);
      } catch (err) {
        console.error('Failed to fetch server status:', err);
      }
    };
    fetch();
    const interval = setInterval(fetch, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="sidebar-section">
      <h3>Server Status</h3>
      <div className="status-list">
        {statuses.map((s) => {
          const statusInfo = STATUS_LABELS[s.current_status] || STATUS_LABELS.available;
          return (
            <div key={s.id} className="status-card">
              <div className="status-card-header">
                <span className="status-card-name">{s.name}</span>
                <span className={`status-badge ${statusInfo.className}`}>
                  {statusInfo.label}
                </span>
              </div>
              {s.current_reservation && (
                <div className="status-detail">
                  {s.current_reservation.user_name}: {s.current_reservation.title}
                  <br />
                  <small>
                    Until{' '}
                    {new Date(s.current_reservation.end_at).toLocaleTimeString(
                      'ko-KR',
                      { hour: '2-digit', minute: '2-digit' }
                    )}
                  </small>
                </div>
              )}
              {!s.current_reservation && s.next_reservation && (
                <div className="status-detail">
                  Next: {s.next_reservation.user_name} -{' '}
                  {new Date(s.next_reservation.start_at).toLocaleString('ko-KR', {
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </div>
              )}
            </div>
          );
        })}
        {statuses.length === 0 && (
          <p className="muted">No server resources configured.</p>
        )}
      </div>
    </div>
  );
}
