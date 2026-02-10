import React, { useState } from 'react';
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
  onClose: () => void;
  onCreated: () => void;
}

function toLocalDatetime(iso: string): string {
  const d = new Date(iso);
  const offset = d.getTimezoneOffset();
  const local = new Date(d.getTime() - offset * 60 * 1000);
  return local.toISOString().slice(0, 16);
}

export default function ReservationModal({
  resources,
  selectedResourceId,
  initialStart,
  initialEnd,
  onClose,
  onCreated,
}: Props) {
  const [resourceId, setResourceId] = useState(selectedResourceId);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [startAt, setStartAt] = useState(toLocalDatetime(initialStart));
  const [endAt, setEndAt] = useState(toLocalDatetime(initialEnd));
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await reservationsAPI.create({
        server_resource_id: resourceId,
        title,
        description: description || undefined,
        start_at: new Date(startAt).toISOString(),
        end_at: new Date(endAt).toISOString(),
      });
      onCreated();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create reservation');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>New Reservation</h2>
          <button className="modal-close" onClick={onClose}>
            &times;
          </button>
        </div>
        {error && <div className="error-msg">{error}</div>}
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Server Resource</label>
            <select
              value={resourceId}
              onChange={(e) => setResourceId(e.target.value)}
              required
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
            />
          </div>
          <div className="form-group">
            <label>Description (optional)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Details about your reservation..."
              rows={3}
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
              />
            </div>
            <div className="form-group">
              <label>End</label>
              <input
                type="datetime-local"
                value={endAt}
                onChange={(e) => setEndAt(e.target.value)}
                required
              />
            </div>
          </div>
          <div className="modal-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading}
            >
              {loading ? 'Creating...' : 'Create Reservation'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
