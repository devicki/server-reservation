import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import Header from '../components/Header';
import './ReleaseNotesPage.css';

const RELEASE_NOTES_URL = '/RELEASE_NOTES.md';

export default function ReleaseNotesPage() {
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    fetch(RELEASE_NOTES_URL)
      .then((res) => {
        if (!res.ok) throw new Error('파일을 불러올 수 없습니다.');
        return res.text();
      })
      .then((text) => {
        if (!cancelled) setContent(text);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '릴리즈 노트를 불러올 수 없습니다.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="dashboard">
      <Header />

      <div className="release-notes-content">
        <section className="release-notes-section">
          <h2 className="release-notes-title">릴리즈 노트</h2>
          <p className="release-notes-desc">
            기능 추가 및 변경 사항 기록입니다. <code>public/RELEASE_NOTES.md</code> 파일을 수정하면 여기에 반영됩니다.
          </p>

          {loading && <p className="release-notes-loading">불러오는 중...</p>}
          {error && <div className="error-msg">{error}</div>}
          {!loading && !error && content && (
            <div className="markdown-body">
              <ReactMarkdown>{content}</ReactMarkdown>
            </div>
          )}
          {!loading && !error && !content && (
            <p className="release-notes-empty">내용이 없습니다.</p>
          )}
        </section>
      </div>
    </div>
  );
}
