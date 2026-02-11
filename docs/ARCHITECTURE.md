# 공유 서버 자원 예약 시스템 - 아키텍처 설계서

## 핵심 개념

- **예약의 소스 오브 트루스는 PostgreSQL DB**
- Google Calendar는 "시각화 및 외부 공유용" 보조 수단
- Google OAuth는 사용자 로그인에 사용하지 않음
- Google Calendar API는 Service Account로만 연동

---

## 1. 시스템 목적

여러 사용자가 하나 이상의 서버 자원을 공유하는 환경에서,
서버 사용 시간을 사전에 예약하고 충돌을 방지하며,
예약 현황을 Google Calendar로 시각화한다.

---

## 2. 전체 아키텍처

```
┌──────────────────────────────────────────────────────────────┐
│                        클라이언트                              │
│  ┌────────────┐   ┌────────────┐   ┌──────────────────────┐  │
│  │ Web (React) │   │ Mobile     │   │ Google Calendar      │  │
│  │ FullCalendar│   │ (선택적)    │   │ (읽기전용 공유)       │  │
│  └──────┬─────┘   └──────┬─────┘   └──────────────────────┘  │
└─────────┼────────────────┼────────────────────────────────────┘
          │                │
          ▼                ▼
┌──────────────────────────────────────────────────────────────┐
│                     FastAPI Application                       │
│  ┌──────────┐ ┌───────────┐ ┌──────────────┐ ┌───────────┐  │
│  │ Auth API │ │Resource   │ │Reservation   │ │Dashboard  │  │
│  │          │ │API        │ │API           │ │API        │  │
│  └──────────┘ └───────────┘ └──────────────┘ └───────────┘  │
│                        │                                      │
│               Service Layer                                   │
│  ┌──────────┐ ┌───────────┐ ┌──────────────┐ ┌───────────┐  │
│  │AuthSvc   │ │ResourceSvc│ │ReservationSvc│ │CalendarSvc│  │
│  └──────────┘ └───────────┘ └──────────────┘ └─────┬─────┘  │
└───────────────────────┬──────────────────────────────┼────────┘
                        │                              │
                        ▼                              ▼
              ┌──────────────────┐          ┌──────────────────┐
              │   PostgreSQL     │          │ Google Calendar   │
              │  Source of Truth │ ───────▶ │ (단방향 동기화)    │
              └──────────────────┘          └──────────────────┘
```

---

## 3. DB 스키마 (ERD)

### users

| Column        | Type         | Constraint       |
|---------------|--------------|------------------|
| id            | UUID         | PK               |
| email         | VARCHAR(255) | UNIQUE, NOT NULL |
| password_hash | VARCHAR(255) | NOT NULL         |
| name          | VARCHAR(100) | NOT NULL         |
| role          | ENUM         | DEFAULT 'user'   |
| is_active     | BOOLEAN      | DEFAULT true     |
| created_at    | TIMESTAMPTZ  | DEFAULT NOW()    |
| updated_at    | TIMESTAMPTZ  | DEFAULT NOW()    |

### server_resources

| Column      | Type         | Constraint       |
|-------------|--------------|------------------|
| id          | UUID         | PK               |
| name        | VARCHAR(100) | NOT NULL         |
| description | TEXT         |                  |
| capacity    | INTEGER      | NULLABLE         |
| is_active   | BOOLEAN      | DEFAULT true     |
| created_at  | TIMESTAMPTZ  | DEFAULT NOW()    |
| updated_at  | TIMESTAMPTZ  | DEFAULT NOW()    |

### reservations

| Column             | Type                | Constraint                    |
|--------------------|---------------------|-------------------------------|
| id                 | UUID                | PK                            |
| user_id            | UUID                | FK → users.id                 |
| server_resource_id | UUID                | FK → server_resources.id      |
| title              | VARCHAR(200)        | NOT NULL                      |
| description        | TEXT                |                               |
| start_at           | TIMESTAMPTZ         | NOT NULL                      |
| end_at             | TIMESTAMPTZ         | NOT NULL                      |
| status             | ENUM                | DEFAULT 'active'              |
| google_event_id    | VARCHAR(255)        | NULLABLE                      |
| created_at         | TIMESTAMPTZ         | DEFAULT NOW()                 |
| updated_at         | TIMESTAMPTZ         | DEFAULT NOW()                 |

**제약조건:**
- `CHECK (end_at > start_at)`
- `EXCLUDE USING gist (server_resource_id WITH =, tstzrange(start_at, end_at) WITH &&) WHERE (status = 'active')`

---

## 4. API 스펙

### Auth (`/api/v1/auth`)

| Method | Endpoint    | 설명               | 인증 |
|--------|-------------|-------------------|------|
| POST   | `/register` | 회원가입            | ❌   |
| POST   | `/login`    | 로그인 (JWT 발급)   | ❌   |
| GET    | `/me`       | 내 정보 조회        | ✅   |

### Resources (`/api/v1/resources`)

| Method | Endpoint | 설명       | 권한    |
|--------|----------|----------|---------|
| GET    | `/`      | 목록 조회  | all     |
| GET    | `/{id}`  | 상세 조회  | all     |
| POST   | `/`      | 생성      | admin   |
| PUT    | `/{id}`  | 수정      | admin   |
| DELETE | `/{id}`  | 삭제      | admin   |

### Reservations (`/api/v1/reservations`)

| Method | Endpoint               | 설명         | 권한          |
|--------|------------------------|------------|---------------|
| GET    | `/`                    | 목록 (필터)  | all           |
| GET    | `/{id}`                | 상세 조회    | all           |
| POST   | `/`                    | 생성         | all           |
| PUT    | `/{id}`                | 수정         | owner         |
| DELETE | `/{id}`                | 취소         | owner / admin |
| GET    | `/check-availability`  | 가용 확인    | all           |

### Dashboard (`/api/v1/dashboard`)

| Method | Endpoint            | 설명                |
|--------|---------------------|-------------------|
| GET    | `/timeline`         | 서버별 타임라인      |
| GET    | `/my-reservations`  | 내 예약 목록        |
| GET    | `/status`           | 현재 서버 상태      |

---

## 5. Google Calendar 연동

### 연동 방식
- Service Account 사용
- 전용 캘린더 1개에 Service Account 이메일 공유 (일정 변경 권한)

### 동기화 규칙 (단방향: DB → Calendar)
- DB 예약 생성 성공 → Calendar 이벤트 생성
- DB 예약 수정 → Calendar 이벤트 수정
- DB 예약 취소 → Calendar 이벤트 삭제
- **Calendar에서 직접 수정한 이벤트는 DB에 반영하지 않음**

### 장애 처리
- Calendar API 장애 시에도 예약 시스템은 정상 동작
- 동기화 실패 시 로그 기록, `google_event_id = null` 유지
- 응답에 `calendar_synced: false` 포함

---

## 6. 동시성 충돌 방지

### 이중 방어 전략
1. **Application Level**: `SELECT FOR UPDATE` 로 동일 서버 예약 행 잠금 → 트랜잭션 내 충돌 검사
2. **Database Level**: `EXCLUDE CONSTRAINT` (tstzrange) → 최종 안전망

---

## 7. 기술 스택

| 분류       | 기술                          |
|-----------|-------------------------------|
| Backend   | Python, FastAPI               |
| ORM       | SQLAlchemy (async)            |
| Migration | Alembic                       |
| Database  | PostgreSQL                    |
| Auth      | JWT (PyJWT), bcrypt           |
| Frontend  | React, FullCalendar           |
| Calendar  | Google Calendar API (Service Account) |
| Infra     | Docker, docker-compose        |

---

## 8. 로드맵

### Phase 1: MVP
- 사용자 인증 (JWT)
- 서버 자원 CRUD (admin)
- 예약 CRUD + 충돌 방지
- Google Calendar 단방향 동기화
- 간단한 타임라인 UI

### Phase 2: 안정화
- 반복 예약
- 예약 알림 (이메일/슬랙)
- 관리자 대시보드 (통계)
- Background Task (Celery/ARQ)

### Phase 3: 확장
- 팀/조직 구조 도입
- 예약 정책 (최대 시간, 사전 예약 제한)
- Audit Log
- SSO 연동 (선택적)
