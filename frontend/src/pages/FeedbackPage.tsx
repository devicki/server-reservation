import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { feedbackAPI } from '../api/client';
import { useAuth } from '../context/AuthContext';

interface FeedbackItem {
  id: string;
  user_id: string;
  user_name: string;
  content: string;
  created_at: string;
}

export default function FeedbackPage() {
  const { user, logout } = useAuth();
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [total, setTotal] = useState(0);
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [submitLoading, setSubmitLoading] = useState(false);

  const fetchList = async () => {
    setLoading(true);
    try {
      const res = await feedbackAPI.list({ limit: 50, offset: 0 });
      setItems(res.data.items);
      setTotal(res.data.total);
    } catch {
      setError('의견 목록을 불러올 수 없습니다.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchList();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!content.trim()) return;
    setSubmitLoading(true);
    try {
      await feedbackAPI.create({ content: content.trim() });
      setContent('');
      await fetchList();
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } };
      setError(ax.response?.data?.detail ?? '의견 등록에 실패했습니다.');
    } finally {
      setSubmitLoading(false);
    }
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleString('ko-KR', {
      dateStyle: 'short',
      timeStyle: 'short',
    });
  };

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div className="header-left">
          <h1>GPU Server Reservation</h1>
        </div>
        <div className="header-right">
          <Link to="/" className="header-link">예약</Link>
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

      <div className="feedback-content">
        <section className="feedback-section">
          <h2>시스템 개선 의견</h2>
          <p className="feedback-desc">불편한 점이나 개선 아이디어를 남겨 주세요.</p>

          <form onSubmit={handleSubmit} className="feedback-form">
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="의견을 입력하세요 (최대 2000자)"
              rows={4}
              maxLength={2000}
              className="feedback-textarea"
              required
            />
            <div className="feedback-form-actions">
              <span className="feedback-char-count">{content.length} / 2000</span>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={submitLoading || !content.trim()}
              >
                {submitLoading ? '등록 중...' : '의견 등록'}
              </button>
            </div>
          </form>

          {error && <div className="error-msg">{error}</div>}
        </section>

        <section className="feedback-list-section">
          <h3>의견 목록 ({total})</h3>
          {loading ? (
            <p className="feedback-loading">불러오는 중...</p>
          ) : items.length === 0 ? (
            <p className="feedback-empty">아직 등록된 의견이 없습니다.</p>
          ) : (
            <ul className="feedback-list">
              {items.map((fb) => (
                <li key={fb.id} className="feedback-item">
                  <div className="feedback-item-meta">
                    <span className="feedback-item-author">{fb.user_name}</span>
                    <span className="feedback-item-date">{formatDate(fb.created_at)}</span>
                  </div>
                  <p className="feedback-item-content">{fb.content}</p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
