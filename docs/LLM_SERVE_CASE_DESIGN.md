# Local LLM Serve 사례 공유 — 설계 문서

design-guide 에이전트 관점에서 요구사항·아키텍처·작업 목록·개발 가이드를 정리합니다.

---

## 1. 요구사항 정리

### 범위
- **목적:** 예약 시스템을 사용한 사용자들이 해당 서버에서 local LLM 모델 serve에 성공한 사례를 공유하는 페이지.
- **기록 항목**
  - **모델 정보:** 모델 이름·식별자, 필요 시 상세 설명(프레임워크, 버전 등)
  - **Serve 커맨드:** 실제로 성공한 실행 커맨드(예: `python -m vllm.entrypoints.openai.api_server ...`)
  - **리소스 할당:** GPU 개수, 메모리, CUDA_VISIBLE_DEVICES 등
  - **대상 서버:** 어떤 예약 서버(리소스)에서 수행했는지
  - **기타 메모:** 선택 사항

### 제약·가정
- 인증된 사용자만 사례 등록 및 목록/상세 조회 가능 (피드백과 동일한 인증 수준).
- 관리자 전용 아님 — 일반 사용자도 등록·열람 가능.
- 기존 스택 유지: FastAPI + SQLAlchemy(async) + PostgreSQL, React + TypeScript + Vite, JWT.

### 성공 기준
- 사례 목록 조회(페이지네이션), 사례 상세 조회, 사례 등록(모델 정보·커맨드·리소스 할당·서버 선택)이 동작.
- 기존 프로젝트 컨벤션(AGENTS.md) 및 레이어드 구조를 따름.

---

## 2. 아키텍처

### 데이터 흐름 (개념)

```
[Frontend]  ServeCasePage (목록 / 등록 폼 / 상세)
     │
     │  GET /api/v1/serve-cases/          → 목록 (items, total)
     │  POST /api/v1/serve-cases/          → 사례 등록 (201)
     │  GET /api/v1/serve-cases/{id}        → 상세 1건
     ▼
[Backend]   serve_cases.py (Router)
     │
     │  create: body → ServeCaseCreateRequest → DB insert
     │  list:   Query(limit, offset) → select + count → ServeCaseListResponse
     │  get:    Path(id) → select by id → ServeCaseResponse (404 if not found)
     ▼
[DB]        serve_cases 테이블 (user_id, server_resource_id, model_name, ...)
```

### 컴포넌트 구성

| 계층 | 역할 | 파일/위치 |
|------|------|------------|
| **Model** | 엔티티 정의, 관계 | `app/models/serve_case.py` |
| **Schema** | 요청/응답 DTO | `app/schemas/serve_case.py` |
| **API** | 라우트만 (단순 CRUD는 서비스 레이어 생략) | `app/api/v1/serve_cases.py` |
| **Migration** | 테이블 추가 | `alembic/versions/009_add_serve_cases.py` |
| **Frontend API** | axios + 타입 | `frontend/src/api/client.ts` (serveCasesAPI) |
| **Frontend Page** | 목록·등록·상세 UI | `frontend/src/pages/ServeCasePage.tsx` |

### ER (요약)

- **serve_cases**
  - `id` (UUID, PK)
  - `user_id` (FK → users.id, CASCADE)
  - `server_resource_id` (FK → server_resources.id) — 어떤 서버에서 성공했는지
  - `model_name` (필수) — 모델 이름/식별자
  - `model_info` (선택) — 텍스트, 상세 설명
  - `serve_command` (필수) — 성공한 커맨드
  - `resource_allocation` (선택) — GPU/메모리 등 리소스 할당 설명
  - `notes` (선택) — 기타 메모
  - `created_at` (timestamptz)

---

## 3. 세분화된 작업 목록

| # | 작업 | 의존성 | 위치/힌트 |
|---|------|--------|-----------|
| 1 | `ServeCase` ORM 모델 정의 | - | `app/models/serve_case.py` |
| 2 | Alembic 마이그레이션 추가 | 1 | `alembic/versions/009_add_serve_cases.py` |
| 3 | Pydantic 스키마 (Create, Response, ListResponse) | 1 | `app/schemas/serve_case.py` |
| 4 | serve_cases 라우터 (list, create, get) | 2, 3 | `app/api/v1/serve_cases.py` |
| 5 | main.py 라우터 등록, models/__init__ export | 4 | `app/main.py`, `app/models/__init__.py` |
| 6 | Frontend API (serveCasesAPI + 타입) | 4 | `frontend/src/api/client.ts` |
| 7 | ServeCasePage (목록 + 등록 폼 + 상세) | 6 | `frontend/src/pages/ServeCasePage.tsx` |
| 8 | 라우트·헤더 링크 추가 | 7 | `frontend/src/App.tsx`, `Header.tsx` |

---

## 4. 개발 가이드 (구현 순서)

### Step 1 — Backend Model
- `app/models/serve_case.py` 생성.
- `Base` 상속, `__tablename__ = "serve_cases"`.
- 컬럼: id(UUID), user_id(FK users), server_resource_id(FK server_resources), model_name(String, 필수), model_info(Text, nullable), serve_command(Text, 필수), resource_allocation(Text, nullable), notes(Text, nullable), created_at(DateTime(timezone=True)).
- 관계: `user = relationship("User", ...)`, `server_resource = relationship("ServerResource", ...)`.
- User / ServerResource 쪽에는 `serve_cases` back_populates는 선택(필요 시 추가).

### Step 2 — Migration
- `alembic revision --autogenerate -m "add_serve_cases"` 또는 수동 작성.
- 008 이후 revision이면 `down_revision = "008"` (또는 현재 head 확인).

### Step 3 — Schemas
- `ServeCaseCreateRequest`: server_resource_id, model_name, model_info(optional), serve_command, resource_allocation(optional), notes(optional). Field(min_length, max_length) 적용.
- `ServeCaseResponse`: id, user_id, user_name, server_resource_id, server_name, model_name, model_info, serve_command, resource_allocation, notes, created_at. model_config from_attributes.
- `ServeCaseListResponse`: items: list[ServeCaseResponse], total: int.

### Step 4 — API Router
- `GET /` list: limit, offset, get_current_user. select + count, order_by created_at.desc().
- `POST /` create: body ServeCaseCreateRequest, get_current_user. Insert 후 server_resource 존재 여부 검증(선택), 201 반환.
- `GET /{id}` get: Path(id), get_current_user. 404 if not found.
- 응답 시 user_name, server_name은 relationship 로딩(selectinload) 후 채우기.

### Step 5 — Register & Export
- `main.py`: `from app.api.v1.serve_cases import router as serve_cases_router`, `app.include_router(serve_cases_router, prefix=API_V1_PREFIX)`.
- `app/models/__init__.py`: ServeCase export.

### Step 6 — Frontend API
- `client.ts`에 `ServeCaseItem`, `ServeCaseCreateRequest` 타입 및 `serveCasesAPI.list()`, `serveCasesAPI.create(body)`, `serveCasesAPI.get(id)` 정의.

### Step 7 — ServeCasePage
- 목록: 테이블 또는 카드 형태, 모델명·서버·작성자·일시 표시, 행 클릭 시 상세로 이동.
- 등록 버튼 → 폼(서버 선택, 모델명, 모델 상세, 커맨드, 리소스 할당, 메모). 제출 시 create 호출 후 목록 갱신 또는 상세로 이동.
- 상세: 한 건 표시(모델 정보, 커맨드, 리소스 할당, 서버, 작성자, 일시). 목록으로 돌아가기 버튼.

### Step 8 — Routing & Nav
- `App.tsx`: Route path `/serve-cases`, PrivateRoute, ServeCasePage.
- `Header.tsx`: 네비 링크 "사례 공유" → `/serve-cases`.

---

## 5. 참고 패턴/원칙

- **REST:** 리소스 `/serve-cases`, GET 목록/단건, POST 생성.
- **Layered:** Route → (선택적 Service) → DB; 본 기능은 단순 CRUD라 라우트에서 직접 DB 접근 허용(기존 feedback 패턴 준수).
- **Stateless Auth:** JWT, get_current_user 의존성으로 인증.
- **Naming:** 스네이크 케이스(DB, API 경로), PascalCase(모델/스키마 클래스), kebab-case(CSS, URL 경로).
