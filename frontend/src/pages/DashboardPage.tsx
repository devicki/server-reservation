import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import FullCalendar from '@fullcalendar/react';
import dayGridPlugin from '@fullcalendar/daygrid';
import timeGridPlugin from '@fullcalendar/timegrid';
import interactionPlugin from '@fullcalendar/interaction';
import { dashboardAPI, resourcesAPI, reservationsAPI } from '../api/client';
import { useAuth } from '../context/AuthContext';
import ReservationModal from '../components/ReservationModal';
import ServerStatus from '../components/ServerStatus';

interface Resource {
  id: string;
  name: string;
  description: string | null;
  capacity: number | null;
  is_active: boolean;
}

interface CalendarEvent {
  id: string;
  title: string;
  start: string;
  end: string;
  backgroundColor?: string;
  borderColor?: string;
  extendedProps: {
    user_name: string;
    user_id: string;
    resource_name: string;
    is_mine: boolean;
  };
}

const COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
  '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16',
];

export default function DashboardPage() {
  const { user, logout } = useAuth();
  const [resources, setResources] = useState<Resource[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedDates, setSelectedDates] = useState<{ start: string; end: string } | null>(null);
  const [selectedResource, setSelectedResource] = useState<string>('');
  const dateRangeRef = useRef({ startStr: '', endStr: '' });

  const fetchResources = async () => {
    try {
      const res = await resourcesAPI.list();
      setResources(res.data.items);
      if (res.data.items.length > 0 && !selectedResource) {
        setSelectedResource(res.data.items[0].id);
      }
    } catch (err) {
      console.error('Failed to fetch resources:', err);
    }
  };

  const fetchTimeline = async (startStr: string, endStr: string) => {
    try {
      const res = await dashboardAPI.timeline({
        start_date: startStr,
        end_date: endStr,
      });
      const allEvents: CalendarEvent[] = [];
      res.data.resources.forEach((resource: any, idx: number) => {
        const color = COLORS[idx % COLORS.length];
        resource.reservations.forEach((r: any) => {
          allEvents.push({
            id: r.id,
            title: `[${resource.name}] ${r.title} - ${r.user_name}`,
            start: r.start_at,
            end: r.end_at,
            backgroundColor: r.is_mine ? color : `${color}88`,
            borderColor: color,
            extendedProps: {
              user_name: r.user_name,
              user_id: r.user_id,
              resource_name: resource.name,
              is_mine: r.is_mine,
            },
          });
        });
      });
      setEvents(allEvents);
    } catch (err) {
      console.error('Failed to fetch timeline:', err);
    }
  };

  useEffect(() => {
    fetchResources();
  }, []);

  const handleDateSelect = (selectInfo: any) => {
    setSelectedDates({
      start: selectInfo.startStr,
      end: selectInfo.endStr,
    });
    setModalOpen(true);
  };

  const handleDatesSet = (dateInfo: any) => {
    dateRangeRef.current = { startStr: dateInfo.startStr, endStr: dateInfo.endStr };
    fetchTimeline(dateInfo.startStr, dateInfo.endStr);
  };

  const handleEventClick = async (clickInfo: any) => {
    if (user?.role !== 'admin') return;
    const eventId = clickInfo.event.id;
    const title = clickInfo.event.title || '이 일정';
    if (!window.confirm(`"${title}" 일정을 삭제(취소)하시겠습니까?`)) return;
    try {
      await reservationsAPI.cancel(eventId);
      const { startStr, endStr } = dateRangeRef.current;
      if (startStr && endStr) fetchTimeline(startStr, endStr);
    } catch (err) {
      console.error('Failed to cancel reservation:', err);
      alert('일정 삭제에 실패했습니다.');
    }
  };

  const handleReservationCreated = () => {
    setModalOpen(false);
    // Refetch by triggering a re-render; FullCalendar will call handleDatesSet
    setEvents([...events]);
    window.location.reload();
  };

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div className="header-left">
          <h1>GPU Server Reservation</h1>
        </div>
        <div className="header-right">
          <Link to="/feedback" className="header-link">의견 게시판</Link>
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

      <div className="dashboard-content">
        <div className="sidebar">
          <ServerStatus />

          <div className="sidebar-section">
            <h3>Quick Reserve</h3>
            <select
              value={selectedResource}
              onChange={(e) => setSelectedResource(e.target.value)}
              className="resource-select"
            >
              {resources.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
            <div className="quick-reserve-buttons">
              <button
                className="btn btn-primary"
                onClick={() => {
                  const now = new Date();
                  const end = new Date(now.getTime() + 2 * 60 * 60 * 1000);
                  setSelectedDates({
                    start: now.toISOString(),
                    end: end.toISOString(),
                  });
                  setModalOpen(true);
                }}
              >
                + 2h 예약
              </button>
              <button
                className="btn btn-primary"
                onClick={() => {
                  const now = new Date();
                  const end = new Date(now.getTime() + 24 * 60 * 60 * 1000);
                  setSelectedDates({
                    start: now.toISOString(),
                    end: end.toISOString(),
                  });
                  setModalOpen(true);
                }}
              >
                + 24h 예약
              </button>
            </div>
          </div>

          <div className="sidebar-section">
            <h3>Resources</h3>
            <ul className="resource-list">
              {resources.map((r, idx) => (
                <li key={r.id} className="resource-item">
                  <span
                    className="color-dot"
                    style={{ backgroundColor: COLORS[idx % COLORS.length] }}
                  />
                  {r.name}
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="calendar-container">
          <FullCalendar
            plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
            initialView="timeGridWeek"
            headerToolbar={{
              left: 'prev,next today',
              center: 'title',
              right: 'dayGridMonth,timeGridWeek,timeGridDay',
            }}
            selectable={true}
            selectMirror={true}
            editable={false}
            events={events}
            select={handleDateSelect}
            eventClick={handleEventClick}
            datesSet={handleDatesSet}
            slotMinTime="00:00:00"
            slotMaxTime="24:00:00"
            scrollTime="00:00:00"
            expandRows={true}
            allDaySlot={false}
            nowIndicator={true}
            height="auto"
            locale="ko"
            eventClassNames={user?.role === 'admin' ? ['calendar-event-admin-deletable'] : undefined}
          />
        </div>
      </div>

      {modalOpen && (
        <ReservationModal
          resources={resources}
          selectedResourceId={selectedResource}
          initialStart={selectedDates?.start || ''}
          initialEnd={selectedDates?.end || ''}
          onClose={() => setModalOpen(false)}
          onCreated={handleReservationCreated}
        />
      )}
    </div>
  );
}
