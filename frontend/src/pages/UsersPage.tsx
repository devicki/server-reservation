import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { usersAPI } from '../api/client';
import { useAuth } from '../context/AuthContext';
import Header from '../components/Header';

interface UserItem {
  id: string;
  email: string;
  name: string;
  role: 'user' | 'admin';
  is_active: boolean;
  created_at: string;
}

export default function UsersPage() {
  const { user, logout } = useAuth();
  const [items, setItems] = useState<UserItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const fetchList = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await usersAPI.list({ limit: 100, offset: 0 });
      setItems(res.data.items);
      setTotal(res.data.total);
    } catch {
      setError('사용자 목록을 불러올 수 없습니다.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchList();
  }, []);

  const handleRoleChange = async (userId: string, role: 'user' | 'admin') => {
    setUpdatingId(userId);
    try {
      await usersAPI.update(userId, { role });
      await fetchList();
    } catch (err: unknown) {
      const detail = err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string | string[] } } }).response?.data?.detail
        : undefined;
      const message = Array.isArray(detail) ? detail[0] : typeof detail === 'string' ? detail : '역할 변경에 실패했습니다.';
      setError(message);
    } finally {
      setUpdatingId(null);
    }
  };

  const handleActiveToggle = async (userId: string, is_active: boolean) => {
    setUpdatingId(userId);
    try {
      await usersAPI.update(userId, { is_active });
      await fetchList();
    } catch (err: unknown) {
      const detail = err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string | string[] } } }).response?.data?.detail
        : undefined;
      const message = Array.isArray(detail) ? detail[0] : typeof detail === 'string' ? detail : '상태 변경에 실패했습니다.';
      setError(message);
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div className="dashboard">
      <Header />

      <div className="feedback-content" style={{ maxWidth: '900px' }}>
        <section className="feedback-section">
          <h2>사용자 관리</h2>
          <p className="feedback-desc">역할 변경 및 계정 활성/비활성 설정 (관리자 전용)</p>

          {error && <div className="error-msg">{error}</div>}

          {loading ? (
            <p className="feedback-loading">불러오는 중...</p>
          ) : (
            <>
              <p className="feedback-desc" style={{ marginBottom: '1rem' }}>총 {total}명</p>
              <div className="users-table-wrap">
                <table className="users-table">
                  <thead>
                    <tr>
                      <th>이메일</th>
                      <th>이름</th>
                      <th>역할</th>
                      <th>상태</th>
                      <th>작업</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((u) => (
                      <tr key={u.id}>
                        <td>{u.email}</td>
                        <td>{u.name}</td>
                        <td>
                          <select
                            value={u.role}
                            disabled={updatingId === u.id || user?.id === u.id}
                            onChange={(e) => handleRoleChange(u.id, e.target.value as 'user' | 'admin')}
                            className="users-role-select"
                            title={user?.id === u.id ? '본인 역할은 변경할 수 없습니다' : undefined}
                          >
                            <option value="user">일반 사용자</option>
                            <option value="admin">관리자</option>
                          </select>
                        </td>
                        <td>
                          <span className={`users-status-badge ${u.is_active ? 'users-status-active' : 'users-status-inactive'}`}>
                            {u.is_active ? '활성' : '비활성'}
                          </span>
                        </td>
                        <td>
                          {user?.id !== u.id && (
                            <button
                              type="button"
                              className="btn btn-secondary"
                              style={{ fontSize: '0.8rem', padding: '0.35rem 0.6rem' }}
                              disabled={updatingId === u.id}
                              onClick={() => handleActiveToggle(u.id, !u.is_active)}
                            >
                              {u.is_active ? '비활성화' : '활성화'}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
