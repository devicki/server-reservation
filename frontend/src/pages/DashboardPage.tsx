import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import {
  configAPI,
  dashboardAPI,
  resourcesAPI,
  reservationsAPI,
} from "../api/client";
import { useAuth } from "../context/AuthContext";
import Header from "../components/Header";
import ReservationModal from "../components/ReservationModal";
import ServerStatus from "../components/ServerStatus";

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
    reservation_id: string;
    instance_id: string;
    reservation_title: string;
    user_name: string;
    user_id: string;
    resource_name: string;
    resource_color: string;
    is_mine: boolean;
    is_recurring: boolean;
    account_name?: string | null;
    status?: string;
  };
}

const COLORS = [
  "#3b82f6",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#ec4899",
  "#06b6d4",
  "#84cc16",
];

export default function DashboardPage() {
  const { user, logout } = useAuth();
  const [resources, setResources] = useState<Resource[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedDates, setSelectedDates] = useState<{
    start: string;
    end: string;
  } | null>(null);
  const [selectedResource, setSelectedResource] = useState<string>("");
  const [editReservationId, setEditReservationId] = useState<string | null>(
    null,
  );
  const [editInstanceId, setEditInstanceId] = useState<string | null>(null);
  const [maxReservationHours, setMaxReservationHours] = useState<number | null>(
    null,
  );
  const dateRangeRef = useRef({ startStr: "", endStr: "" });

  const fetchConfig = async () => {
    try {
      const res = await configAPI.get();
      setMaxReservationHours(res.data.max_reservation_hours ?? null);
    } catch {
      setMaxReservationHours(null);
    }
  };

  const fetchResources = async () => {
    try {
      const res = await resourcesAPI.list();
      setResources(res.data.items);
      if (res.data.items.length > 0 && !selectedResource) {
        setSelectedResource(res.data.items[0].id);
      }
    } catch (err) {
      console.error("Failed to fetch resources:", err);
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
          const accountPart = r.account_name ? ` (${r.account_name})` : "";
          const isCompleted = r.status === "completed";
          const isRecurring = Boolean(r.is_recurring);
          allEvents.push({
            id: r.id, // instance_id (고유 키)
            title: `[${resource.name}${accountPart}] ${r.title} - ${r.user_name}`,
            start: r.start_at,
            end: r.end_at,
            backgroundColor: isCompleted
              ? undefined
              : r.is_mine
                ? color
                : `${color}88`,
            borderColor: isCompleted ? undefined : color,
            extendedProps: {
              reservation_id: r.reservation_id,
              instance_id: r.id,
              reservation_title: r.title,
              user_name: r.user_name,
              user_id: r.user_id,
              resource_name: resource.name,
              resource_color: color,
              is_mine: r.is_mine,
              is_recurring: isRecurring,
              account_name: r.account_name ?? null,
              status: r.status ?? "active",
            },
          });
        });
      });
      setEvents(allEvents);
    } catch (err) {
      console.error("Failed to fetch timeline:", err);
    }
  };

  useEffect(() => {
    fetchResources();
    fetchConfig();
  }, []);

  const handleDateSelect = (selectInfo: any) => {
    setEditReservationId(null);
    setSelectedDates({
      start: selectInfo.startStr,
      end: selectInfo.endStr,
    });
    setModalOpen(true);
  };

  const handleDatesSet = (dateInfo: any) => {
    dateRangeRef.current = {
      startStr: dateInfo.startStr,
      endStr: dateInfo.endStr,
    };
    fetchTimeline(dateInfo.startStr, dateInfo.endStr);
  };

  const handleEventClick = async (clickInfo: any) => {
    const reservationId =
      clickInfo.event.extendedProps?.reservation_id ?? clickInfo.event.id;
    const instanceId =
      clickInfo.event.extendedProps?.instance_id ?? clickInfo.event.id;
    const isMine = clickInfo.event.extendedProps?.is_mine === true;
    const isAdmin = user?.role === "admin";
    const status = clickInfo.event.extendedProps?.status as string | undefined;

    if (status === "completed") {
      alert("완료된 예약은 수정 및 삭제할 수 없습니다.");
      return;
    }

    const eventEnd = clickInfo.event.end ? new Date(clickInfo.event.end) : null;
    if (eventEnd && eventEnd <= new Date()) {
      alert("과거 일정은 수정 및 삭제할 수 없습니다.");
      return;
    }

    // 본인 예약이거나 관리자가 다른 사용자 예약을 클릭한 경우: 상세 모달을 열어 수정/삭제 가능
    if (isMine || isAdmin) {
      setSelectedDates(null);
      setEditReservationId(reservationId);
      setEditInstanceId(instanceId);
      setModalOpen(true);
      return;
    }
  };

  const handleReservationCreated = () => {
    setModalOpen(false);
    setEditReservationId(null);
    setEditInstanceId(null);
    setEvents([...events]);
    window.location.reload();
  };

  const handleReservationUpdatedOrDeleted = () => {
    setModalOpen(false);
    setEditReservationId(null);
    setEditInstanceId(null);
    const { startStr, endStr } = dateRangeRef.current;
    if (startStr && endStr) fetchTimeline(startStr, endStr);
  };

  return (
    <div className="dashboard">
      <Header />

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
            <div className="legend">
              <div className="legend-item">
                <span className="legend-dot legend-dot--solid" />
                <span>일반 예약</span>
              </div>
              <div className="legend-item">
                <span className="legend-dot legend-dot--recurring" />
                <span>반복 예약</span>
              </div>
              <div className="legend-item">
                <span className="legend-dot legend-dot--others" />
                <span>다른 사용자</span>
              </div>
            </div>
          </div>
        </div>

        <div className="calendar-container">
          <FullCalendar
            plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
            initialView="timeGridWeek"
            headerToolbar={{
              left: "prev,next today",
              center: "title",
              right: "dayGridMonth,timeGridWeek,timeGridDay",
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
            eventClassNames={(arg) => {
              const classes: string[] = [];
              const isCompleted =
                arg.event.extendedProps?.status === "completed";
              const isRecurring =
                arg.event.extendedProps?.is_recurring === true;
              if (isCompleted) {
                classes.push("calendar-event-completed");
              } else {
                if (isRecurring) classes.push("calendar-event-recurring");
                if (
                  arg.event.extendedProps?.is_mine ||
                  user?.role === "admin"
                ) {
                  classes.push("calendar-event-clickable");
                }
              }
              return classes;
            }}
            eventContent={(arg) => {
              const {
                is_recurring,
                is_mine,
                resource_name,
                resource_color,
                reservation_title,
                user_name,
                account_name,
                status,
              } = arg.event.extendedProps;
              const isCompleted = status === "completed";
              const isMonth = arg.view.type === "dayGridMonth";
              const accountPart = account_name ? ` (${account_name})` : "";
              const color: string = resource_color ?? "";
              const dotColor = is_mine ? color : `${color}88`;

              if (isMonth) {
                // ── Month 뷰: 서버 색상 도트 + 서버명 + 제목 한 줄 ──
                return (
                  <div
                    className="fc-event-inner fc-event-inner--month"
                    style={
                      isCompleted
                        ? {}
                        : { color: is_mine ? color : `${color}cc` }
                    }
                  >
                    <span
                      className="fc-event-server-dot"
                      style={{ background: dotColor, borderColor: color }}
                    />
                    {is_recurring && (
                      <span
                        className="fc-event-recurring-icon"
                        title="반복 예약"
                      >
                        ↻
                      </span>
                    )}
                    <span className="fc-event-title">
                      {accountPart}
                      {reservation_title}
                    </span>
                    <span className="fc-event-user"> {user_name}</span>
                  </div>
                );
              }

              // ── Week / Day 뷰: 기존 레이아웃 ──
              const timeText = arg.timeText;
              return (
                <div className="fc-event-inner">
                  {timeText && (
                    <span className="fc-event-time">{timeText}</span>
                  )}
                  <span className="fc-event-title-wrap">
                    {is_recurring && (
                      <span
                        className="fc-event-recurring-icon"
                        title="반복 예약"
                      >
                        ↻
                      </span>
                    )}
                    <span className="fc-event-title">{arg.event.title}</span>
                  </span>
                </div>
              );
            }}
          />
        </div>
      </div>

      {modalOpen && (
        <ReservationModal
          resources={resources}
          selectedResourceId={selectedResource}
          initialStart={selectedDates?.start ?? ""}
          initialEnd={selectedDates?.end ?? ""}
          reservationId={editReservationId}
          instanceId={editInstanceId}
          maxReservationHours={maxReservationHours ?? undefined}
          onClose={() => {
            setModalOpen(false);
            setEditReservationId(null);
            setEditInstanceId(null);
          }}
          onCreated={handleReservationCreated}
          onUpdated={handleReservationUpdatedOrDeleted}
          onDeleted={handleReservationUpdatedOrDeleted}
        />
      )}
    </div>
  );
}
