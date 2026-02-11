import React, { useEffect, useState } from 'react';
import { reservationsAPI } from '../api/client';

interface Resource {
  id: string;
  name: string;
}

interface Props {
  resources: Resource[];
  selectedResourceId: string;
  initialStart: string;
  initialEnd: string;
  /** Edit mode: reservation ID to load and update/delete */
  reservationId?: string | null;
  onClose: () => void;
  onCreated: () => void;
  onUpdated?: () => void;
  onDeleted?: () => void;
}

function toLocalDatetime(iso: string): string {
  if (!iso || String(iso).trim() === '') return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const offset = d.getTimezoneOffset();
  const local = new Date(d.getTime() - offset * 60 * 1000);
  return local.toISOString().slice(0, 16);
}

export default function ReservationModal({
  resources,
  selectedResourceId,
  initialStart,
  initialEnd,
  reservationId,
  onClose,
  onCreated,
  onUpdated,
  onDeleted,
}: Props) {
  const isEdit = Boolean(reservationId);
  const [resourceId, setResourceId] = useState(selectedResourceId);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [startAt, setStartAt] = useState(toLocalDatetime(initialStart));
  const [endAt, setEndAt] = useState(toLocalDatetime(initialEnd));
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingReservation, setLoadingReservation] = useState(isEdit);
  const [isPastReservation, setIsPastReservation] = useState(false);

  useEffect(() => {
    if (!reservationId) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await reservationsAPI.get(reservationId);
        const r = res.data;
        if (cancelled) return;
        setResourceId(r.server_resource_id);
        setTitle(r.title);
        setDescription(r.description ?? '');
        setStartAt(toLocalDatetime(r.start_at));
        setEndAt(toLocalDatetime(r.end_at));
        setIsPastReservation(new Date(r.end_at) <= new Date());
      } catch (err) {
        if (!cancelled) setError('예약 정보를 불러오지 못했습니다.');
      } finally {
        if (!cancelled) setLoadingReservation(false);
      }
    })();
    return () => { cancelled = true; };
  }, [reservationId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (isEdit && reservationId) {
        await reservationsAPI.update(reservationId, {
          title,
          description: description || undefined,
          start_at: new Date(startAt).toISOString(),
          end_at: new Date(endAt).toISOString(),
        });
        onUpdated?.();
      } else {
        await reservationsAPI.create({
          server_resource_id: resourceId,
          title,
          description: description || undefined,
          start_at: new Date(startAt).toISOString(),
          end_at: new Date(endAt).toISOString(),
        });
        onCreated();
      }
    } catch (err: any) {
      const raw = err.response?.data?.detail;
      const message =
        typeof raw === 'string'
          ? raw
          : Array.isArray(raw) && raw.length > 0
            ? raw.map((e: { msg?: string; message?: string }) => e?.msg ?? e?.message ?? String(e)).join('. ')
            : (isEdit ? '수정에 실패했습니다.' : 'Failed to create reservation');
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!reservationId || !window.confirm('이 예약을 삭제(취소)하시겠습니까?')) return;
    setError('');
    setLoading(true);
    try {
      await reservationsAPI.cancel(reservationId);
      onDeleted?.();
    } catch (err: any) {
      const raw = err.response?.data?.detail;
      setError(typeof raw === 'string' ? raw : '삭제에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{isEdit ? '예약 수정' : 'New Reservation'}</h2>
          <button className="modal-close" onClick={onClose}>
            &times;
          </button>
        </div>
        {loadingReservation ? (
          <div className="modal-loading">불러오는 중...</div>
        ) : (
          <>
        {error && <div className="error-msg">{error}</div>}
        {isEdit && isPastReservation && (
          <div className="past-reservation-msg" role="alert">
            과거 일정은 수정 및 삭제할 수 없습니다.
          </div>
        )}
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Server Resource</label>
            <select
              value={resourceId}
              onChange={(e) => setResourceId(e.target.value)}
              required
              disabled={isEdit || isPastReservation}
              title={isEdit ? '예약 수정 시 리소스는 변경할 수 없습니다.' : undefined}
            >
              {resources.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label>Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              placeholder="e.g. Model Training - ResNet50"
              disabled={isPastReservation}
            />
          </div>
          <div className="form-group">
            <label>Description (optional)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Details about your reservation..."
              rows={3}
              disabled={isPastReservation}
            />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Start</label>
              <input
                type="datetime-local"
                value={startAt}
                onChange={(e) => setStartAt(e.target.value)}
                required
                disabled={isPastReservation}
              />
            </div>
            <div className="form-group">
              <label>End</label>
              <input
                type="datetime-local"
                value={endAt}
                onChange={(e) => setEndAt(e.target.value)}
                required
                disabled={isPastReservation}
              />
            </div>
          </div>
          <div className="modal-actions">
            {isEdit && (
              <button
                type="button"
                className="btn btn-danger"
                onClick={handleDelete}
                disabled={loading || isPastReservation}
              >
                {loading ? '처리 중...' : '삭제'}
              </button>
            )}
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
            >
              취소
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading || isPastReservation}
            >
              {loading ? (isEdit ? '저장 중...' : 'Creating...') : (isEdit ? '저장' : 'Create Reservation')}
            </button>
          </div>
        </form>
          </>
        )}
      </div>
    </div>
  );
}
