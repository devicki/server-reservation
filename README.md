# GPU Server Reservation System

공유 GPU 서버 자원의 사용 시간을 예약하고 충돌을 방지하며, Google Calendar로 시각화하는 시스템.

## Architecture

- **Backend**: FastAPI + SQLAlchemy (async) + PostgreSQL
- **Frontend**: React + FullCalendar + Vite
- **Auth**: JWT (email/password)
- **Calendar**: Google Calendar API (Service Account, one-way sync)

상세 설계: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Quick Start

### 1. Docker Compose (권장)

```bash
# backend/.env 없으면 생성 (비어 있어도 됨. 구글 캘린더 연동 시 backend/.env.example 참고)
touch backend/.env

# 전체 스택 실행
docker compose up -d

# 확인
# - Backend API:  http://localhost:8000/docs
# - Frontend:     http://localhost:3000
# - PostgreSQL:   localhost:5432
```

### 2. 로컬 개발 (Backend)

```bash
cd backend

# 가상환경 생성
python -m venv .venv
source .venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일을 편집하여 DB URL 등 설정

# DB 마이그레이션
alembic upgrade head

# 서버 실행
uvicorn app.main:app --reload --port 8000
```

### 3. 로컬 개발 (Frontend)

```bash
cd frontend

npm install
npm run dev
# → http://localhost:5173
```

---

## 초기 관리자 생성

회원가입 후, DB에서 직접 관리자 권한 부여:

```sql
UPDATE users SET role = 'admin' WHERE email = 'admin@example.com';
```

---

## Google Calendar 연동 (선택)

1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트 생성
2. Google Calendar API 활성화
3. Service Account 생성 → JSON 키 파일 다운로드
4. Google Calendar 생성 → Service Account 이메일에 "일정 변경 가능" 권한 공유
5. 환경변수 설정 (`backend/.env`에 추가):

```env
GOOGLE_CALENDAR_ENABLED=true
GOOGLE_SERVICE_ACCOUNT_FILE=credentials/key.json
GOOGLE_CALENDAR_ID=your-calendar-id@group.calendar.google.com
```

**상대 경로**(`credentials/key.json`)를 쓰면 로컬·Docker 공용으로 사용할 수 있습니다.  
Docker Compose는 `backend/.env`를 컨테이너에 넘기므로, 테스트 스크립트와 앱이 같은 설정을 사용합니다.

### Google Calendar에 예약이 안 보일 때

1. **환경변수**  
   `GOOGLE_CALENDAR_ENABLED=true`, `GOOGLE_SERVICE_ACCOUNT_FILE`, `GOOGLE_CALENDAR_ID` 모두 설정했는지 확인.
2. **캘린더 공유**  
   Google Calendar 설정에서 해당 캘린더를 Service Account 이메일(JSON 키의 `client_email`)과 공유하고, 권한을 **"일정 변경 가능"**으로 설정.
3. **캘린더 ID**  
   Google Calendar 웹에서 해당 캘린더 → 설정 → "캘린더 통합"의 "캘린더 ID" 사용 (예: `xxx@group.calendar.google.com`).
4. **백엔드 로그**  
   예약 생성 시 `Calendar event created: ...` 로그가 나오는지 확인. 실패 시 `Failed to create calendar event` 또는 `key file not found` 등 원인이 로그에 출력됨.

---

## API Documentation

서버 실행 후:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 주요 엔드포인트

| Method | Endpoint                           | Description        |
|--------|------------------------------------|--------------------|
| POST   | `/api/v1/auth/register`            | 회원가입            |
| POST   | `/api/v1/auth/login`               | 로그인              |
| GET    | `/api/v1/resources/`               | 서버 자원 목록      |
| POST   | `/api/v1/resources/`               | 서버 자원 생성 (admin) |
| GET    | `/api/v1/reservations/`            | 예약 목록           |
| POST   | `/api/v1/reservations/`            | 예약 생성           |
| PUT    | `/api/v1/reservations/{id}`        | 예약 수정 (owner)   |
| DELETE | `/api/v1/reservations/{id}`        | 예약 취소           |
| GET    | `/api/v1/dashboard/timeline`       | 타임라인 뷰         |
| GET    | `/api/v1/dashboard/status`         | 서버 현재 상태      |

---

## Project Structure

```
server-reservation/
├── docs/
│   └── ARCHITECTURE.md          # 상세 설계 문서
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   ├── database.py          # DB engine, session
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   ├── api/
│   │   │   ├── deps.py          # Auth dependencies
│   │   │   └── v1/              # API v1 routers
│   │   ├── services/            # Business logic
│   │   └── core/                # Security, exceptions
│   ├── alembic/                 # DB migrations
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/client.ts        # API client (axios)
│   │   ├── context/             # React context (Auth)
│   │   ├── pages/               # Page components
│   │   ├── components/          # UI components
│   │   └── index.css            # Global styles
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 동시성 충돌 방지

이중 방어 전략 적용:

1. **Application Level**: `SELECT FOR UPDATE` 로 동일 서버의 예약 행 잠금
2. **Database Level**: PostgreSQL `EXCLUDE` 제약조건 (`tstzrange` 기반)

어떤 race condition에서도 시간 중복 예약이 불가능합니다.
