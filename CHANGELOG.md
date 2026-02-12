# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2026-02-12

### Added - 예약 기반 세션 관리 시스템

#### 핵심 기능
- **자동 스케줄링 시스템**: APScheduler 기반, 매 1분마다 예약 상태 체크
- **예약 활성화**: 예약 시작 시 자동으로 예약자 계정 활성화, 나머지 계정 차단
- **예약 비활성화**: 예약 종료 시 자동으로 프로세스 종료 및 계정 잠금
- **세션 로그 시스템**: 모든 활성화/비활성화 이벤트 기록 및 조회

#### 새로운 파일
- `app/models/reservation_session_log.py` - 세션 로그 모델
- `app/services/session_manager.py` - 계정 잠금/해제, 프로세스 관리
- `app/services/session_scheduler.py` - 스케줄러 메인 로직
- `app/schemas/session_log.py` - 세션 로그 스키마
- `app/api/v1/session_logs.py` - 세션 로그 API
- `alembic/versions/006_add_reservation_session_logs.py` - DB 마이그레이션
- `scripts/test_session_scheduler.py` - 테스트 스크립트

#### 문서
- `docs/SESSION_SCHEDULER_DESIGN.md` - 설계 문서
- `docs/SESSION_SCHEDULER_USAGE.md` - 사용 가이드
- `docs/SESSION_SCHEDULER_IMPLEMENTATION.md` - 구현 보고서

#### API 엔드포인트
- `GET /api/v1/session-logs` - 세션 로그 목록 조회 (관리자)
- `GET /api/v1/session-logs/reservation/{id}` - 특정 예약의 세션 로그 조회

#### 의존성
- `apscheduler>=3.10.4` - 스케줄링

#### 데이터베이스
- `reservation_session_logs` 테이블 추가
- `session_event_type` ENUM 추가 (activated, deactivated, error)

### Changed
- `app/main.py` - APScheduler 통합, 스케줄러 자동 시작/종료
- `app/models/__init__.py` - 새 모델 export
- `requirements.txt` - apscheduler 추가
- `README.md` - 세션 스케줄러 섹션 추가

### Technical Details

#### 예약 활성화 워크플로우
1. 예약자 계정 잠금 해제 (`usermod -U`)
2. 예외 계정 제외 모든 계정 잠금 (`usermod -L`)
3. 예외 계정 제외 모든 프로세스 종료 (`pkill`)

#### 예약 비활성화 워크플로우
1. 예약자 프로세스 강제 종료 (`pkill -9`)
2. 예약자 계정 잠금 (`usermod -L`)

#### 예외 계정 관리
- 시스템 기본: `EXCLUDE_USERS` 환경변수 (root, dev, admin, teleport, ubuntu)
- 서버별 추가: `ServerResource.account_exclusions`
- 현재 예약자: `Reservation.account_name`

#### 안전성
- Idempotency: 중복 실행 방지
- 트랜잭션 관리: 데이터베이스 일관성 보장
- 에러 처리: SSH 실패, 계정 없음, 권한 부족 등

### Future Improvements
- Teleport API 연동
- 알림 시스템 (이메일/슬랙)
- 모니터링 대시보드
- 성능 메트릭 수집

---

## [0.1.0] - 2026-02-10

### Initial Release

#### Features
- 사용자 인증 (JWT)
- 서버 자원 관리 (CRUD)
- 예약 관리 (CRUD + 충돌 방지)
- Google Calendar 단방향 동기화
- 타임라인 대시보드
- GPU 헬스 모니터링
- 피드백 시스템

#### Architecture
- Backend: FastAPI + SQLAlchemy (async) + PostgreSQL
- Frontend: React + FullCalendar + Vite
- Auth: JWT (email/password)
- Calendar: Google Calendar API (Service Account)
