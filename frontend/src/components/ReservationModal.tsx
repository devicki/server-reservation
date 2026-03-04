import React, { useEffect, useState } from "react";
import { recurringReservationsAPI, reservationsAPI, resourcesAPI } from "../api/client";

// ─── 상수 ────────────────────────────────────────────────
const WEEKDAYS = [
  { key: "MON", label: "월" },
  { key: "TUE", label: "화" },
  { key: "WED", label: "수" },
  { key: "THU", label: "목" },
  { key: "FRI", label: "금" },
  { key: "SAT", label: "토" },
  { key: "SUN", label: "일" },
] as const;

type WeekdayKey = (typeof WEEKDAYS)[number]["key"];
type FreqType = "DAILY" | "WEEKLY" | "MONTHLY";

// ─── 타입 ────────────────────────────────────────────────
interface Resource {
  id: string;
  name: string;
}

interface Props {
  resources: Resource[];
  selectedResourceId: string;
  initialStart: string;
  initialEnd: string;
  reservationId?: string | null;
  maxReservationHours?: number;
  onClose: () => void;
  onCreated: () => void;
  onUpdated?: () => void;
  onDeleted?: () => void;
}

// ─── 유틸 ────────────────────────────────────────────────
function toLocalDatetime(iso: string): string {
  if (!iso || String(iso).trim() === "") return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const offset = d.getTimezoneOffset();
  const local = new Date(d.getTime() - offset * 60 * 1000);
  return local.toISOString().slice(0, 16);
}

function getMinDatetimeLocal(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

/** time 문자열("HH:MM")에서 같은 날짜 기준 datetime-local 문자열 생성 */
function timeToDatetimeLocal(dateBase: string, time: string): string {
  if (!dateBase || !time) return "";
  return dateBase.slice(0, 10) + "T" + time;
}

/** datetime-local 값에서 "HH:MM" 추출 */
function extractTime(dt: string): string {
  return dt.slice(11, 16);
}

/** 기준 시각 + offsetMinutes 를 "HH:MM" 으로 반환 */
function addMinutesToTime(hhmm: string, offsetMinutes: number): string {
  const [h, m] = hhmm.split(":").map(Number);
  const total = h * 60 + m + offsetMinutes;
  const clampedH = Math.floor(total / 60) % 24;
  const clampedM = total % 60;
  return `${String(clampedH).padStart(2, "0")}:${String(clampedM).padStart(2, "0")}`;
}

/** 현재 날짜 기준 오늘로부터 +N개월 yyyy-MM-dd 반환 */
function addMonthsToToday(months: number): string {
  const d = new Date();
  d.setMonth(d.getMonth() + months);
  return d.toISOString().slice(0, 10);
}

export default function ReservationModal({
  resources,
  selectedResourceId,
  initialStart,
  initialEnd,
  reservationId,
  maxReservationHours,
  onClose,
  onCreated,
  onUpdated,
  onDeleted,
}: Props) {
  const isEdit = Boolean(reservationId);

  // ─── 공통 필드 ─────────────────────────────────────────
  const [resourceId, setResourceId] = useState(selectedResourceId);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [accountList, setAccountList] = useState<string[]>([]);
  const [selectedAccount, setSelectedAccount] = useState("");
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingReservation, setLoadingReservation] = useState(isEdit);
  const [isPastReservation, setIsPastReservation] = useState(false);

  // ─── 예약 타입 토글 ────────────────────────────────────
  const [isRecurring, setIsRecurring] = useState(false);

  // ─── 단일 예약 필드 ─────────────────────────────────────
  const [startAt, setStartAt] = useState(toLocalDatetime(initialStart));
  const [endAt, setEndAt] = useState(toLocalDatetime(initialEnd));

  // ─── 반복 예약 필드 ─────────────────────────────────────
  // 시작 시각 (HH:MM) — 날짜와 분리해서 관리
  const [recurStartDate, setRecurStartDate] = useState(
    initialStart ? toLocalDatetime(initialStart).slice(0, 10) : new Date().toISOString().slice(0, 10),
  );
  const [recurStartTime, setRecurStartTime] = useState("09:00");
  const [recurEndTime, setRecurEndTime] = useState("18:00");
  const [freq, setFreq] = useState<FreqType>("WEEKLY");
  const [interval, setIntervalVal] = useState(1);
  const [selectedDays, setSelectedDays] = useState<Set<WeekdayKey>>(new Set(["MON"]));
  const [byMonthDay, setByMonthDay] = useState(1);
  const [recurrenceEndDate, setRecurrenceEndDate] = useState(addMonthsToToday(3));

  // ─── 편집 모드: 예약 정보 로드 ──────────────────────────
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
        setDescription(r.description ?? "");
        setSelectedAccount(r.account_name ?? "");
        if (r.start_at) {
          setStartAt(toLocalDatetime(r.start_at));
          setEndAt(toLocalDatetime(r.end_at));
          setIsPastReservation(new Date(r.end_at) <= new Date());
        }
      } catch {
        if (!cancelled) setError("예약 정보를 불러오지 못했습니다.");
      } finally {
        if (!cancelled) setLoadingReservation(false);
      }
    })();
    return () => { cancelled = true; };
  }, [reservationId]);

  // ─── 서버 계정 목록 ─────────────────────────────────────
  useEffect(() => {
    if (!resourceId) { setAccountList([]); setSelectedAccount(""); return; }
    let cancelled = false;
    setLoadingAccounts(true);
    setAccountList([]);
    resourcesAPI
      .getRemoteUsers(resourceId)
      .then((res) => { if (!cancelled) setAccountList(res.data.items.map((i) => i.username)); })
      .catch(() => { if (!cancelled) setAccountList([]); })
      .finally(() => { if (!cancelled) setLoadingAccounts(false); });
    return () => { cancelled = true; };
  }, [resourceId]);

  // ─── 반복 예약: 시작 시간 변경 시 종료 시간 자동 보정 ────
  useEffect(() => {
    if (!isRecurring) return;
    // 종료 시간이 시작 시간보다 앞서거나 같으면 +1시간으로 보정
    const [sh, sm] = recurStartTime.split(":").map(Number);
    const [eh, em] = recurEndTime.split(":").map(Number);
    if (eh * 60 + em <= sh * 60 + sm) {
      setRecurEndTime(addMinutesToTime(recurStartTime, 60));
    }
  }, [recurStartTime, isRecurring]);

  // ─── 요일 토글 ──────────────────────────────────────────
  const toggleDay = (day: WeekdayKey) => {
    setSelectedDays((prev) => {
      const next = new Set(prev);
      if (next.has(day)) {
        if (next.size === 1) return prev; // 최소 1개 선택 강제
        next.delete(day);
      } else {
        next.add(day);
      }
      return next;
    });
  };

  // ─── 시간 유효성 검사 (단일 예약) ──────────────────────
  const isSameDay = (a: string, b: string) => a.slice(0, 10) === b.slice(0, 10);

  const singleTimeError = (() => {
    if (!startAt || !endAt) return null;
    const s = new Date(startAt);
    const e = new Date(endAt);
    if (e <= s) return "종료 시각은 시작 시각 이후여야 합니다.";
    if (!isSameDay(startAt, endAt)) return "익일 예약은 허용되지 않습니다. 당일 내로 설정해주세요.";
    if (maxReservationHours && (e.getTime() - s.getTime()) > maxReservationHours * 3600 * 1000)
      return `예약은 최대 ${maxReservationHours}시간까지 가능합니다.`;
    return null;
  })();

  // ─── 반복 예약 시간 유효성 ─────────────────────────────
  const recurTimeError = (() => {
    if (!isRecurring) return null;
    const [sh, sm] = recurStartTime.split(":").map(Number);
    const [eh, em] = recurEndTime.split(":").map(Number);
    if (eh * 60 + em <= sh * 60 + sm) return "종료 시각은 시작 시각 이후여야 합니다.";
    if (maxReservationHours && (eh * 60 + em - (sh * 60 + sm)) > maxReservationHours * 60)
      return `예약은 최대 ${maxReservationHours}시간까지 가능합니다.`;
    if (!recurrenceEndDate) return "반복 종료일을 선택해주세요.";
    if (new Date(recurrenceEndDate) <= new Date(recurStartDate))
      return "반복 종료일은 시작일 이후여야 합니다.";
    return null;
  })();

  // ─── 제출 ───────────────────────────────────────────────
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!isEdit) {
      const timeErr = isRecurring ? recurTimeError : singleTimeError;
      if (timeErr) { setError(timeErr); return; }
    }

    setLoading(true);
    try {
      if (isEdit && reservationId) {
        await reservationsAPI.update(reservationId, {
          title,
          description: description || undefined,
          account_name: selectedAccount,
          start_at: new Date(startAt).toISOString(),
          end_at: new Date(endAt).toISOString(),
        });
        onUpdated?.();
      } else if (isRecurring) {
        // ── 반복 예약 생성 ──
        const startIso = new Date(`${recurStartDate}T${recurStartTime}:00`).toISOString();
        const endIso = new Date(`${recurStartDate}T${recurEndTime}:00`).toISOString();
        await recurringReservationsAPI.create({
          server_resource_id: resourceId,
          title,
          description: description || undefined,
          account_name: selectedAccount,
          start_at: startIso,
          end_at: endIso,
          recurrence: {
            freq,
            interval,
            by_day: freq === "WEEKLY" ? Array.from(selectedDays).join(",") : null,
            by_month_day: freq === "MONTHLY" ? byMonthDay : null,
          },
          recurrence_end_date: recurrenceEndDate
            ? new Date(`${recurrenceEndDate}T23:59:59`).toISOString()
            : null,
        });
        onCreated();
      } else {
        // ── 단일 예약 생성 ──
        await reservationsAPI.create({
          server_resource_id: resourceId,
          title,
          description: description || undefined,
          account_name: selectedAccount,
          start_at: new Date(startAt).toISOString(),
          end_at: new Date(endAt).toISOString(),
        });
        onCreated();
      }
    } catch (err: any) {
      const raw = err.response?.data?.detail;
      const message =
        typeof raw === "string"
          ? raw
          : Array.isArray(raw) && raw.length > 0
            ? raw.map((e: { msg?: string; message?: string }) => e?.msg ?? e?.message ?? String(e)).join(". ")
            : isEdit ? "수정에 실패했습니다." : "예약 생성에 실패했습니다.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!reservationId || !window.confirm("이 예약을 삭제(취소)하시겠습니까?")) return;
    setError("");
    setLoading(true);
    try {
      await reservationsAPI.cancel(reservationId);
      onDeleted?.();
    } catch (err: any) {
      const raw = err.response?.data?.detail;
      setError(typeof raw === "string" ? raw : "삭제에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };

  const submitDisabled =
    loading ||
    isPastReservation ||
    (!isEdit && !loadingAccounts && accountList.length === 0) ||
    (!isEdit && !isRecurring && !!singleTimeError) ||
    (!isEdit && isRecurring && !!recurTimeError);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal--wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{isEdit ? "예약 수정" : "새 예약"}</h2>
          <button className="modal-close" onClick={onClose}>&times;</button>
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

            {/* 예약 타입 토글 — 생성 모드에서만 표시 */}
            {!isEdit && (
              <div className="reservation-type-toggle">
                <button
                  type="button"
                  className={`type-toggle-btn${!isRecurring ? " active" : ""}`}
                  onClick={() => setIsRecurring(false)}
                >
                  일반 예약
                </button>
                <button
                  type="button"
                  className={`type-toggle-btn${isRecurring ? " active" : ""}`}
                  onClick={() => setIsRecurring(true)}
                >
                  반복 예약
                </button>
              </div>
            )}

            <form onSubmit={handleSubmit} className="modal-form">
              <div className="modal-body">

                {/* ── 공통: 서버 선택 ── */}
                <div className="form-group">
                  <label>Server Resource</label>
                  <select
                    value={resourceId}
                    onChange={(e) => setResourceId(e.target.value)}
                    required
                    disabled={isEdit || isPastReservation}
                  >
                    {resources.map((r) => (
                      <option key={r.id} value={r.id}>{r.name}</option>
                    ))}
                  </select>
                </div>

                {/* ── 공통: 계정 선택 ── */}
                <div className="form-group">
                  <label>서버 계정 *</label>
                  <select
                    value={selectedAccount}
                    onChange={(e) => setSelectedAccount(e.target.value)}
                    disabled={isPastReservation || loadingAccounts}
                    required
                  >
                    <option value="">선택하세요</option>
                    {accountList.map((u) => <option key={u} value={u}>{u}</option>)}
                  </select>
                  {loadingAccounts && <p className="form-hint">계정 목록 불러오는 중...</p>}
                  {!loadingAccounts && accountList.length === 0 && resourceId && (
                    <p className="form-hint" style={{ color: "var(--color-danger)" }}>
                      계정 목록을 불러올 수 없습니다. 서버 관리에서 SSH 설정을 확인하세요.
                    </p>
                  )}
                </div>

                {/* ── 공통: 제목 / 설명 ── */}
                <div className="form-group">
                  <label>Title</label>
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    required
                    placeholder="예: Model Training - ResNet50"
                    disabled={isPastReservation}
                  />
                </div>
                <div className="form-group">
                  <label>Description (선택)</label>
                  <textarea
                    className="modal-description-input"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="예약 관련 상세 내용..."
                    rows={2}
                    disabled={isPastReservation}
                  />
                </div>

                {/* ════════════════════════════════════
                    단일 예약 시간 입력
                ════════════════════════════════════ */}
                {(!isRecurring || isEdit) && (
                  <>
                    <div className="form-row">
                      <div className="form-group">
                        <label>시작</label>
                        <input
                          type="datetime-local"
                          value={startAt}
                          onChange={(e) => setStartAt(e.target.value)}
                          min={!isPastReservation ? getMinDatetimeLocal() : undefined}
                          required
                          disabled={isPastReservation}
                        />
                      </div>
                      <div className="form-group">
                        <label>종료</label>
                        <input
                          type="datetime-local"
                          value={endAt}
                          onChange={(e) => setEndAt(e.target.value)}
                          min={!isPastReservation ? (startAt || getMinDatetimeLocal()) : undefined}
                          required
                          disabled={isPastReservation}
                        />
                      </div>
                    </div>
                    {singleTimeError && !isEdit && (
                      <p className="form-hint form-hint--error">{singleTimeError}</p>
                    )}
                    {!isEdit && maxReservationHours != null && maxReservationHours > 0 && (
                      <p className="reservation-max-hours-hint">
                        단일 예약은 최대 {maxReservationHours}시간까지 가능합니다.
                      </p>
                    )}
                  </>
                )}

                {/* ════════════════════════════════════
                    반복 예약 옵션
                ════════════════════════════════════ */}
                {isRecurring && !isEdit && (
                  <div className="recurrence-panel">

                    {/* 반복 주기 선택 */}
                    <div className="form-group">
                      <label>반복 주기</label>
                      <div className="recurrence-freq-group">
                        {(["DAILY", "WEEKLY", "MONTHLY"] as FreqType[]).map((f) => (
                          <button
                            key={f}
                            type="button"
                            className={`freq-btn${freq === f ? " active" : ""}`}
                            onClick={() => setFreq(f)}
                          >
                            {{ DAILY: "매일", WEEKLY: "매주", MONTHLY: "매월" }[f]}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* 간격 */}
                    <div className="form-group form-group--inline">
                      <label>반복 간격</label>
                      <div className="interval-input-wrap">
                        <input
                          type="number"
                          min={1}
                          max={52}
                          value={interval}
                          onChange={(e) => setIntervalVal(Math.max(1, Number(e.target.value)))}
                          className="interval-input"
                        />
                        <span className="interval-unit">
                          {{ DAILY: "일", WEEKLY: "주", MONTHLY: "개월" }[freq]}마다
                        </span>
                      </div>
                    </div>

                    {/* WEEKLY: 요일 선택 */}
                    {freq === "WEEKLY" && (
                      <div className="form-group">
                        <label>반복 요일</label>
                        <div className="weekday-picker">
                          {WEEKDAYS.map(({ key, label }) => (
                            <button
                              key={key}
                              type="button"
                              className={`weekday-btn${selectedDays.has(key) ? " active" : ""}`}
                              onClick={() => toggleDay(key)}
                            >
                              {label}
                            </button>
                          ))}
                        </div>
                        <p className="form-hint">최소 1개 이상 선택해야 합니다.</p>
                      </div>
                    )}

                    {/* MONTHLY: 일 선택 */}
                    {freq === "MONTHLY" && (
                      <div className="form-group form-group--inline">
                        <label>반복 날짜</label>
                        <div className="interval-input-wrap">
                          <span className="interval-unit">매월</span>
                          <input
                            type="number"
                            min={1}
                            max={28}
                            value={byMonthDay}
                            onChange={(e) => setByMonthDay(Math.min(28, Math.max(1, Number(e.target.value))))}
                            className="interval-input"
                          />
                          <span className="interval-unit">일</span>
                        </div>
                        <p className="form-hint">매월 말일 보정이 있어 최대 28일까지 선택 가능합니다.</p>
                      </div>
                    )}

                    {/* 시작일 */}
                    <div className="form-group">
                      <label>첫 반복 시작일</label>
                      <input
                        type="date"
                        value={recurStartDate}
                        min={new Date().toISOString().slice(0, 10)}
                        onChange={(e) => setRecurStartDate(e.target.value)}
                        required
                      />
                    </div>

                    {/* 시작/종료 시각 (당일 내) */}
                    <div className="form-row">
                      <div className="form-group">
                        <label>시작 시각</label>
                        <input
                          type="time"
                          value={recurStartTime}
                          onChange={(e) => setRecurStartTime(e.target.value)}
                          required
                        />
                      </div>
                      <div className="form-group">
                        <label>종료 시각 <span className="form-hint-inline">(당일 내)</span></label>
                        <input
                          type="time"
                          value={recurEndTime}
                          min={addMinutesToTime(recurStartTime, 1)}
                          max="23:59"
                          onChange={(e) => setRecurEndTime(e.target.value)}
                          required
                        />
                      </div>
                    </div>

                    {recurTimeError && (
                      <p className="form-hint form-hint--error">{recurTimeError}</p>
                    )}

                    {/* 반복 종료일 */}
                    <div className="form-group">
                      <label>반복 종료일</label>
                      <input
                        type="date"
                        value={recurrenceEndDate}
                        min={recurStartDate}
                        max={addMonthsToToday(12)}
                        onChange={(e) => setRecurrenceEndDate(e.target.value)}
                        required
                      />
                      <p className="form-hint">최대 12개월 후까지 생성 가능합니다.</p>
                    </div>

                    {/* 반복 예약 미리보기 요약 */}
                    <div className="recurrence-summary">
                      <span className="recurrence-summary-icon">🔁</span>
                      <span>
                        {freq === "DAILY" && `매 ${interval}일마다`}
                        {freq === "WEEKLY" && `매 ${interval}주 ${Array.from(selectedDays).map((d) => WEEKDAYS.find((w) => w.key === d)?.label).join("·")}요일마다`}
                        {freq === "MONTHLY" && `매 ${interval}개월 ${byMonthDay}일마다`}
                        {" "}
                        <strong>{recurStartTime} ~ {recurEndTime}</strong>
                        {recurrenceEndDate && ` · ${recurrenceEndDate}까지`}
                      </span>
                    </div>

                    {maxReservationHours != null && maxReservationHours > 0 && (
                      <p className="reservation-max-hours-hint">
                        반복 예약도 1회당 최대 {maxReservationHours}시간까지 가능합니다.
                      </p>
                    )}
                  </div>
                )}
              </div>

              <div className="modal-actions">
                {isEdit && (
                  <button
                    type="button"
                    className="btn btn-danger"
                    onClick={handleDelete}
                    disabled={loading || isPastReservation}
                  >
                    {loading ? "처리 중..." : "삭제"}
                  </button>
                )}
                <button type="button" className="btn btn-secondary" onClick={onClose}>취소</button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={submitDisabled}
                >
                  {loading
                    ? isEdit ? "저장 중..." : "생성 중..."
                    : isEdit
                      ? "저장"
                      : isRecurring
                        ? "반복 예약 생성"
                        : "예약 생성"}
                </button>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
