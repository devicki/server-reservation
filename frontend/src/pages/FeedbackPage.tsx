import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import type { FeedbackItem } from '../api/client';
import { feedbackAPI } from '../api/client';
import { useAuth } from '../context/AuthContext';
import Header from '../components/Header';
import './FeedbackPage.css';

export default function FeedbackPage() {
  const { user, logout } = useAuth();
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [total, setTotal] = useState(0);
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [submitLoading, setSubmitLoading] = useState(false);
  const [commentContent, setCommentContent] = useState<Record<string, string>>({});
  const [commentLoading, setCommentLoading] = useState<Record<string, boolean>>({});
  const [reactionLoading, setReactionLoading] = useState<Record<string, boolean>>({});

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
      const detail = err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string | string[] } } }).response?.data?.detail
        : undefined;
      const message = Array.isArray(detail) ? detail[0] : typeof detail === 'string' ? detail : '의견 등록에 실패했습니다.';
      setError(message || '의견 등록에 실패했습니다.');
    } finally {
      setSubmitLoading(false);
    }
  };

  const handleCommentSubmit = async (feedbackId: string, e: React.FormEvent) => {
    e.preventDefault();
    const text = commentContent[feedbackId]?.trim();
    if (!text) return;
    setCommentLoading((prev) => ({ ...prev, [feedbackId]: true }));
    try {
      const res = await feedbackAPI.createComment(feedbackId, { content: text });
      setItems((prev) =>
        prev.map((fb) => {
          if (fb.id !== feedbackId) return fb;
          return {
            ...fb,
            comment_count: fb.comment_count + 1,
            comments: [...fb.comments, res.data],
          };
        })
      );
      setCommentContent((prev) => ({ ...prev, [feedbackId]: '' }));
    } catch {
      setError('댓글 등록에 실패했습니다.');
    } finally {
      setCommentLoading((prev) => ({ ...prev, [feedbackId]: false }));
    }
  };

  const handleToggleReaction = async (feedbackId: string) => {
    setReactionLoading((prev) => ({ ...prev, [feedbackId]: true }));
    try {
      const res = await feedbackAPI.toggleReaction(feedbackId);
      setItems((prev) =>
        prev.map((fb) => (fb.id === feedbackId ? res.data : fb))
      );
    } catch {
      setError('반응을 적용할 수 없습니다.');
    } finally {
      setReactionLoading((prev) => ({ ...prev, [feedbackId]: false }));
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
      <Header />

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
                  <div className="feedback-item-actions">
                    <button
                      type="button"
                      className={`feedback-reaction-btn ${fb.user_reaction === 'like' ? 'active' : ''}`}
                      onClick={() => handleToggleReaction(fb.id)}
                      disabled={reactionLoading[fb.id]}
                      title="좋아요"
                    >
                      👍 {fb.reaction_counts?.like ?? 0}
                      {reactionLoading[fb.id] ? ' ...' : ''}
                    </button>
                    <span className="feedback-comment-count">💬 댓글 {fb.comment_count ?? 0}개</span>
                  </div>
                  <div className="feedback-comments">
                    {fb.comments?.map((c) => (
                      <div key={c.id} className="feedback-comment">
                        <div className="feedback-comment-meta">
                          <span className="feedback-comment-author">{c.user_name}</span>
                          <span className="feedback-comment-date">{formatDate(c.created_at)}</span>
                        </div>
                        <p className="feedback-comment-content">{c.content}</p>
                      </div>
                    ))}
                    <form
                      onSubmit={(e) => handleCommentSubmit(fb.id, e)}
                      className="feedback-comment-form"
                    >
                      <input
                        type="text"
                        value={commentContent[fb.id] ?? ''}
                        onChange={(e) =>
                          setCommentContent((prev) => ({
                            ...prev,
                            [fb.id]: e.target.value,
                          }))
                        }
                        placeholder="댓글을 입력하세요 (최대 1000자)"
                        maxLength={1000}
                        className="feedback-comment-input"
                      />
                      <button
                        type="submit"
                        className="btn btn-primary btn-sm"
                        disabled={commentLoading[fb.id] || !(commentContent[fb.id]?.trim())}
                      >
                        {commentLoading[fb.id] ? '등록 중...' : '댓글 등록'}
                      </button>
                    </form>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
