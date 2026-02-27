import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  serveCasesAPI,
  resourcesAPI,
  type ServeCaseItem,
  type ResourceItem,
} from '../api/client';
import { useAuth } from '../context/AuthContext';
import Header from '../components/Header';

const LIMIT = 20;

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString('ko-KR', {
    dateStyle: 'short',
    timeStyle: 'short',
    hour12: false,
  });
}

export default function ServeCasePage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const [items, setItems] = useState<ServeCaseItem[]>([]);
  const [total, setTotal] = useState(0);
  const [detail, setDetail] = useState<ServeCaseItem | null>(null);
  const [resources, setResources] = useState<ResourceItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [view, setView] = useState<'list' | 'detail' | 'create'>('list');
  const [offset, setOffset] = useState(0);

  const [formServerId, setFormServerId] = useState('');
  const [formModelName, setFormModelName] = useState('');
  const [formModelInfo, setFormModelInfo] = useState('');
  const [formServeCommand, setFormServeCommand] = useState('');
  const [formResourceAllocation, setFormResourceAllocation] = useState('');
  const [formNotes, setFormNotes] = useState('');
  const [submitLoading, setSubmitLoading] = useState(false);

  const fetchList = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await serveCasesAPI.list({ limit: LIMIT, offset });
      setItems(res.data.items);
      setTotal(res.data.total);
    } catch {
      setError('사례 목록을 불러올 수 없습니다.');
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchDetail = async (caseId: string) => {
    setLoading(true);
    setError('');
    try {
      const res = await serveCasesAPI.get(caseId);
      setDetail(res.data);
    } catch {
      setError('사례를 불러올 수 없습니다.');
      setDetail(null);
    } finally {
      setLoading(false);
    }
  };

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
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (id) {
      setView('detail');
      fetchDetail(id);
    } else {
      setView('list');
      setDetail(null);
    }
  }, [id]);

  useEffect(() => {
    if (view === 'list' && !id) fetchList();
  }, [view, offset]);

  const handleOpenDetail = (caseId: string) => {
    navigate(`/serve-cases/${caseId}`);
    setView('detail');
    setDetail(null);
  };

  const handleBackToList = () => {
    navigate('/serve-cases');
    setView('list');
    setDetail(null);
  };

  const handleOpenCreate = () => {
    setView('create');
    setFormServerId(resources[0]?.id ?? '');
    setFormModelName('');
    setFormModelInfo('');
    setFormServeCommand('');
    setFormResourceAllocation('');
    setFormNotes('');
    setError('');
  };

  const handleSubmitCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!formModelName.trim() || !formServeCommand.trim() || !formServerId) {
      setError('서버, 모델명, Serve 커맨드는 필수입니다.');
      return;
    }
    setSubmitLoading(true);
    try {
      await serveCasesAPI.create({
        server_resource_id: formServerId,
        model_name: formModelName.trim(),
        model_info: formModelInfo.trim() || undefined,
        serve_command: formServeCommand.trim(),
        resource_allocation: formResourceAllocation.trim() || undefined,
        notes: formNotes.trim() || undefined,
      });
      handleBackToList();
      fetchList();
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setError(typeof detail === 'string' ? detail : '사례 등록에 실패했습니다.');
    } finally {
      setSubmitLoading(false);
    }
  };

  return (
    <div className="dashboard">
      <Header />

      <div className="feedback-content" style={{ maxWidth: '900px' }}>
        <section className="feedback-section">
          <h2>Local LLM Serve 사례 공유</h2>
          <p className="feedback-desc">
            예약 서버에서 모델 serve에 성공한 커맨드·리소스 할당을 공유해 보세요.
          </p>

          {view === 'list' && (
            <>
              <div className="serve-case-actions">
                <button type="button" className="btn btn-primary" onClick={handleOpenCreate}>
                  사례 등록
                </button>
              </div>
              {error && <div className="error-msg">{error}</div>}
              {loading ? (
                <p className="feedback-loading">불러오는 중...</p>
              ) : items.length === 0 ? (
                <p className="feedback-empty">등록된 사례가 없습니다.</p>
              ) : (
                <>
                  <div className="serve-case-table-wrap">
                    <table className="users-table serve-case-table">
                      <thead>
                        <tr>
                          <th>모델</th>
                          <th>서버</th>
                          <th>작성자</th>
                          <th>등록일</th>
                        </tr>
                      </thead>
                      <tbody>
                        {items.map((c) => (
                          <tr
                            key={c.id}
                            className="serve-case-row"
                            onClick={() => handleOpenDetail(c.id)}
                            role="button"
                            tabIndex={0}
                            onKeyDown={(e) =>
                              e.key === 'Enter' && handleOpenDetail(c.id)
                            }
                          >
                            <td className="serve-case-model">{c.model_name}</td>
                            <td>{c.server_name}</td>
                            <td>{c.user_name}</td>
                            <td className="serve-case-date">{formatDate(c.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="serve-case-pagination">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={offset === 0 || loading}
                      onClick={() => setOffset((o) => Math.max(0, o - LIMIT))}
                    >
                      이전
                    </button>
                    <span className="serve-case-page-info">
                      {offset + 1}–{offset + items.length} / {total}
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
            </>
          )}

          {view === 'detail' && (
            <>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleBackToList}
                style={{ marginBottom: '1rem' }}
              >
                ← 목록으로
              </button>
              {error && <div className="error-msg">{error}</div>}
              {loading ? (
                <p className="feedback-loading">불러오는 중...</p>
              ) : detail ? (
                <div className="serve-case-detail">
                  <div className="serve-case-detail-row">
                    <span className="serve-case-detail-label">모델명</span>
                    <span>{detail.model_name}</span>
                  </div>
                  {detail.model_info && (
                    <div className="serve-case-detail-row">
                      <span className="serve-case-detail-label">모델 상세</span>
                      <pre className="serve-case-detail-pre">{detail.model_info}</pre>
                    </div>
                  )}
                  <div className="serve-case-detail-row">
                    <span className="serve-case-detail-label">서버</span>
                    <span>{detail.server_name}</span>
                  </div>
                  <div className="serve-case-detail-row">
                    <span className="serve-case-detail-label">Serve 커맨드</span>
                    <pre className="serve-case-detail-pre serve-case-command">
                      {detail.serve_command}
                    </pre>
                  </div>
                  {detail.resource_allocation && (
                    <div className="serve-case-detail-row">
                      <span className="serve-case-detail-label">리소스 할당</span>
                      <pre className="serve-case-detail-pre">
                        {detail.resource_allocation}
                      </pre>
                    </div>
                  )}
                  {detail.notes && (
                    <div className="serve-case-detail-row">
                      <span className="serve-case-detail-label">메모</span>
                      <pre className="serve-case-detail-pre">{detail.notes}</pre>
                    </div>
                  )}
                  <div className="serve-case-detail-row">
                    <span className="serve-case-detail-label">작성자</span>
                    <span>{detail.user_name}</span>
                  </div>
                  <div className="serve-case-detail-row">
                    <span className="serve-case-detail-label">등록일</span>
                    <span>{formatDate(detail.created_at)}</span>
                  </div>
                </div>
              ) : (
                <p className="feedback-empty">사례를 찾을 수 없습니다.</p>
              )}
            </>
          )}

          {view === 'create' && (
            <>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleBackToList}
                style={{ marginBottom: '1rem' }}
              >
                ← 목록으로
              </button>
              {error && <div className="error-msg">{error}</div>}
              <form onSubmit={handleSubmitCreate} className="serve-case-form">
                <div className="form-group">
                  <label>대상 서버 *</label>
                  <select
                    value={formServerId}
                    onChange={(e) => setFormServerId(e.target.value)}
                    className="form-control"
                    required
                  >
                    <option value="">선택</option>
                    {resources.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>모델명 *</label>
                  <input
                    type="text"
                    value={formModelName}
                    onChange={(e) => setFormModelName(e.target.value)}
                    placeholder="예: Llama-3.2-3B-Instruct"
                    className="form-control"
                    maxLength={200}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>모델 상세 (선택)</label>
                  <textarea
                    value={formModelInfo}
                    onChange={(e) => setFormModelInfo(e.target.value)}
                    placeholder="프레임워크, 버전 등"
                    className="form-control"
                    rows={3}
                    maxLength={4000}
                  />
                </div>
                <div className="form-group">
                  <label>Serve 커맨드 *</label>
                  <textarea
                    value={formServeCommand}
                    onChange={(e) => setFormServeCommand(e.target.value)}
                    placeholder="실제로 성공한 실행 커맨드 전체"
                    className="form-control serve-case-command-input"
                    rows={6}
                    maxLength={8000}
                    required
                  />
                </div>
                <div className="form-group">
                  <label>리소스 할당 (선택)</label>
                  <textarea
                    value={formResourceAllocation}
                    onChange={(e) => setFormResourceAllocation(e.target.value)}
                    placeholder="GPU 개수, CUDA_VISIBLE_DEVICES, 메모리 등"
                    className="form-control"
                    rows={3}
                    maxLength={2000}
                  />
                </div>
                <div className="form-group">
                  <label>메모 (선택)</label>
                  <textarea
                    value={formNotes}
                    onChange={(e) => setFormNotes(e.target.value)}
                    placeholder="기타 참고 사항"
                    className="form-control"
                    rows={2}
                    maxLength={2000}
                  />
                </div>
                <div className="serve-case-form-actions">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleBackToList}
                  >
                    취소
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={submitLoading}
                  >
                    {submitLoading ? '등록 중...' : '등록'}
                  </button>
                </div>
              </form>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
