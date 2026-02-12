# 예약 세션 스케줄러 구현 완료 보고서

## 구현 개요

예약 시간에 따라 자동으로 서버 계정의 접근 권한을 제어하고 프로세스를 관리하는 **예약 기반 세션 스케줄링 시스템**을 구현했습니다.

**구현 날짜**: 2026-02-12  
**구현 범위**: Phase 1 & 2 (기본 세션 관리 + 스케줄러 통합)

## 구현된 기능

### 1. 자동 스케줄링 시스템

- **APScheduler** 기반 비동기 스케줄러
- 매 1분마다 예약 상태 자동 체크
- 예약 시작/종료 이벤트 자동 트리거
- 서버 시작 시 자동 시작, 종료 시 안전한 셧다운

### 2. 예약 활성화 (시작 시)

**구현된 단계**:
1. 예약자 계정 잠금 해제 (`usermod -U`)
2. 예외 계정 제외한 모든 계정 잠금 (`usermod -L`)
3. 예외 계정 제외한 모든 프로세스 종료 (`pkill`)

**예외 계정 관리**:
- 시스템 기본 예외: `EXCLUDE_USERS` 환경변수
- 서버별 추가 예외: `ServerResource.account_exclusions`
- 현재 예약자: `Reservation.account_name`

### 3. 예약 비활성화 (종료 시)

**구현된 단계**:
1. 예약자 프로세스 강제 종료 (`pkill -9`)
2. 예약자 계정 잠금 (`usermod -L`)

### 4. 세션 로그 시스템

**새 테이블**: `reservation_session_logs`
- 모든 활성화/비활성화 이벤트 기록
- 성공/실패 상세 정보 저장 (JSONB)
- 중복 실행 방지 (Idempotency)
- 디버깅 및 감사 로그

**API 엔드포인트**:
- `GET /api/v1/session-logs`: 모든 로그 조회 (관리자)
- `GET /api/v1/session-logs/reservation/{id}`: 특정 예약 로그 조회

## 파일 구조

### 새로 생성된 파일

```
backend/
├── app/
│   ├── models/
│   │   └── reservation_session_log.py          # 세션 로그 모델
│   ├── services/
│   │   ├── session_manager.py                  # 계정 잠금/해제, 프로세스 관리
│   │   └── session_scheduler.py                # 스케줄러 메인 로직
│   ├── schemas/
│   │   └── session_log.py                      # 세션 로그 스키마
│   └── api/v1/
│       └── session_logs.py                     # 세션 로그 API
├── alembic/versions/
│   └── 006_add_reservation_session_logs.py     # 데이터베이스 마이그레이션
├── scripts/
│   └── test_session_scheduler.py               # 테스트 스크립트
└── requirements.txt                            # apscheduler 추가

docs/
├── SESSION_SCHEDULER_DESIGN.md                 # 설계 문서
├── SESSION_SCHEDULER_IMPLEMENTATION.md         # 이 문서
└── SESSION_SCHEDULER_USAGE.md                  # 사용 가이드
```

### 수정된 파일

```
backend/
├── app/
│   ├── models/__init__.py                      # 새 모델 export
│   └── main.py                                 # 스케줄러 통합
```

## 기술 스택

| 컴포넌트 | 기술 | 버전 |
|---------|------|------|
| 스케줄러 | APScheduler | 3.10.4+ |
| SSH 클라이언트 | Paramiko | 3.4.0+ (기존) |
| 비동기 처리 | asyncio | Python 3.11+ |
| 데이터베이스 | PostgreSQL + SQLAlchemy | 2.0+ |

## 데이터베이스 스키마

### reservation_session_logs 테이블

```sql
CREATE TABLE reservation_session_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_id UUID NOT NULL REFERENCES reservations(id) ON DELETE CASCADE,
    event_type session_event_type NOT NULL,  -- 'activated', 'deactivated', 'error'
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TYPE session_event_type AS ENUM ('activated', 'deactivated', 'error');
CREATE INDEX idx_session_logs_reservation ON reservation_session_logs (reservation_id, created_at);
```

## 실행 흐름

```
┌─────────────────────────────────────────────────────────┐
│ 1. FastAPI 서버 시작                                     │
│    └─> APScheduler 시작 (매 1분마다 실행)               │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ 2. SessionScheduler.process_reservation_events()         │
│    ├─> 현재 시각 체크                                    │
│    ├─> 시작할 예약 조회 (start_at <= now < end_at)      │
│    └─> 종료할 예약 조회 (end_at <= now)                 │
└────────────────┬────────────────────────────────────────┘
                 │
       ┌─────────┴─────────┐
       │                   │
       ▼                   ▼
┌──────────────┐    ┌──────────────┐
│ 3. 예약 활성화 │    │ 3. 예약 비활성화 │
│ activate()   │    │ deactivate() │
└──────┬───────┘    └──────┬───────┘
       │                   │
       ▼                   ▼
┌─────────────────────────────────┐
│ 4. SessionManager (SSH 명령)     │
│    ├─> unlock_user()            │
│    ├─> lock_user()              │
│    ├─> kill_user_processes()   │
│    ├─> get_all_users()          │
│    ├─> lock_all_except()        │
│    └─> kill_processes_except()  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ 5. 로그 기록                     │
│    └─> reservation_session_logs │
└─────────────────────────────────┘
```

## 안전성 및 에러 처리

### Idempotency (멱등성)

- `reservation_session_logs`로 이벤트 기록
- 동일 예약에 대해 활성화/비활성화 중복 실행 방지
- 스케줄러가 여러 번 실행되어도 안전

### 에러 처리

| 에러 시나리오 | 처리 방법 |
|-------------|----------|
| SSH 연결 실패 | 로그 기록, 재시도 없음 (다음 스케줄러 실행 시 재시도) |
| 계정 없음 | 경고 로그, 건너뜀 |
| 권한 부족 | 에러 로그, 관리자 확인 필요 |
| 프로세스 종료 실패 | 경고 로그, 일부 실패 허용 |

### 트랜잭션 관리

- 데이터베이스 트랜잭션 사용
- SSH 작업 실패 시 롤백 없음 (SSH는 외부 시스템)
- 로그는 항상 기록 (성공/실패 무관)

## 테스트

### 수동 테스트

```bash
cd backend
python -m scripts.test_session_scheduler
```

### 통합 테스트 시나리오

1. **예약 생성 → 시작 → 종료**
   - 예약 생성 (account_name 포함)
   - 시작 시간 도달 → 계정 활성화 확인
   - 종료 시간 도달 → 계정 비활성화 확인

2. **예외 계정 확인**
   - 시스템 기본 예외 (`root`, `dev` 등)
   - 서버별 예외 (`account_exclusions`)
   - 예약자 계정

3. **로그 확인**
   - `reservation_session_logs` 테이블
   - API `/api/v1/session-logs`

## 배포 방법

### 1. 의존성 설치

```bash
cd backend
pip install -r requirements.txt
```

### 2. 데이터베이스 마이그레이션

```bash
cd backend
alembic upgrade head
```

### 3. 서버 SSH 설정

관리자 계정으로 각 서버의 SSH 정보를 설정:

```bash
curl -X PUT http://localhost:8000/api/v1/resources/{server_id} \
  -H "Authorization: Bearer {admin_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "host": "192.168.1.100",
    "ssh_port": 22,
    "ssh_username": "admin",
    "ssh_private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----"
  }'
```

### 4. 서버 시작

```bash
cd backend
uvicorn app.main:app --reload
```

서버 시작 시 로그 확인:
```
Starting session scheduler (interval: 1 minute)
Session scheduler started successfully
```

## 향후 개선사항

### Phase 3: 안정화 (미구현)

- [ ] 에러 처리 강화 (재시도 로직)
- [ ] 알림 시스템 (이메일/슬랙)
- [ ] 모니터링 대시보드
- [ ] 성능 메트릭 수집

### Phase 4: Teleport 연동 (미구현)

- [ ] Teleport API 클라이언트 구현
- [ ] 접근 권한 부여/회수 로직
- [ ] Teleport + OS 통합 테스트

### 추가 기능 (선택)

- [ ] 예약 N분 전 사전 활성화
- [ ] 예약 종료 후 자동 정리 (디스크 사용량 체크)
- [ ] 프로세스 강제 종료 전 경고 알림
- [ ] GPU 메모리 사용량 기반 프로세스 우선순위 종료

## 알려진 제한사항

1. **Teleport 연동 미구현**
   - 현재는 OS 레벨 계정 잠금/해제만 지원
   - SSH를 통한 우회 접속은 여전히 가능

2. **단일 스케줄러 인스턴스**
   - 다중 서버 환경에서는 스케줄러 중복 실행 주의
   - `max_instances=1` 설정으로 단일 인스턴스 보장

3. **SSH 키 평문 저장**
   - 데이터베이스에 SSH 키가 평문으로 저장
   - 프로덕션 환경에서는 암호화 권장

4. **프로세스 종료 보장 없음**
   - 일부 프로세스는 종료에 실패할 수 있음
   - 수동 확인 및 정리 필요

## 성능 고려사항

- **스케줄러 주기**: 1분 (변경 가능)
- **SSH 타임아웃**: 10~20초 (명령별 상이)
- **동시 처리**: 비동기 처리로 여러 예약 동시 처리
- **데이터베이스 부하**: 예약 개수에 비례 (인덱스 최적화)

## 결론

예약 기반 세션 스케줄링 시스템의 **핵심 기능**이 구현되었습니다:

✅ 자동 스케줄링 (APScheduler)  
✅ 예약 활성화 (계정 잠금 해제, 타 계정 차단, 프로세스 정리)  
✅ 예약 비활성화 (프로세스 종료, 계정 잠금)  
✅ 예외 계정 관리  
✅ 세션 로그 시스템  
✅ API 엔드포인트  

시스템은 **즉시 사용 가능**하며, 서버 SSH 설정만 완료하면 자동으로 작동합니다.

향후 Teleport 연동, 알림 시스템, 모니터링 대시보드 등을 추가하여 시스템을 더욱 강화할 수 있습니다.
