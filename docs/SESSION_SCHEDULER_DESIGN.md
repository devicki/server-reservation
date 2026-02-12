# 예약 기반 세션 스케줄링 시스템 설계서

## 1. 개요

예약 시간에 따라 자동으로 서버 계정의 접근 권한을 제어하고, 프로세스를 관리하는 핵심 기능.

### 목표
- **예약 시작**: 예약자에게만 서버 접근 허용, 나머지 계정 차단
- **예약 중**: 리소스 독점 보장 (프로세스 클린업)
- **예약 종료**: 모든 권한 회수, 리소스 정리

## 2. 아키텍처 설계

### 2.1 컴포넌트 구조

```
┌─────────────────────────────────────────────────────────┐
│                   Scheduler (APScheduler)                │
│  - 1분마다 예약 상태 체크                                 │
│  - 예약 시작/종료 이벤트 트리거                           │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│            SessionSchedulerService                       │
│  - process_reservation_events()                          │
│  - activate_reservation()                                │
│  - deactivate_reservation()                              │
└──────────┬────────────────────┬─────────────────────────┘
           │                    │
           ▼                    ▼
┌──────────────────┐   ┌───────────────────────────┐
│ SessionManager   │   │ TeleportService           │
│ Service          │   │ (향후 구현)                │
│                  │   │                           │
│ - lock_user()    │   │ - grant_access()          │
│ - unlock_user()  │   │ - revoke_access()         │
│ - kill_processes │   │                           │
└────────┬─────────┘   └───────────────────────────┘
         │
         ▼
┌─────────────────┐
│  SSH Runner     │
│  (기존)          │
└─────────────────┘
```

### 2.2 데이터 모델 확장

**Reservation 테이블** (기존 필드 활용)
- `account_name`: 예약자가 사용할 OS 계정명
- `start_at`, `end_at`: 예약 시작/종료 시각
- `status`: active/canceled

**ServerResource 테이블** (기존 필드 활용)
- `account_exclusions`: 서버별 추가 예외 계정 (쉼표 구분)
- `host`, `ssh_username`, `ssh_private_key`: SSH 연결 정보

## 3. 워크플로우 상세

### 3.1 예약 시작 (Activation)

**트리거 조건**
- 현재 시각 >= `start_at`
- 현재 시각 < `end_at`
- `status` = `active`
- 이전에 활성화되지 않음 (중복 방지)

**실행 단계**

```
1. [Teleport 접근 권한 부여] (향후 구현)
   → TeleportService.grant_access(account_name, server_id)

2. [예약자 계정 잠금 해제]
   → SessionManager.unlock_user(account_name)
   → SSH: sudo usermod -U {account_name}

3. [다른 계정 잠금]
   → 예외 계정 목록 = EXCLUDE_USERS + account_exclusions + account_name
   → 서버의 모든 일반 계정 조회 (getent passwd)
   → 예외 제외한 모든 계정에 대해:
      - SSH: sudo usermod -L {other_account}

4. [잔류 프로세스 정리]
   → 예외 계정 제외한 모든 계정의 프로세스 종료:
      - SSH: sudo pkill -u {other_account}
```

### 3.2 예약 종료 (Deactivation)

**트리거 조건**
- 현재 시각 >= `end_at`
- `status` = `active`
- 이전에 비활성화되지 않음

**실행 단계**

```
1. [Teleport 권한 회수] (향후 구현)
   → TeleportService.revoke_access(account_name, server_id)

2. [예약자 프로세스 강제 종료]
   → SSH: sudo pkill -u {account_name} -9

3. [예약자 계정 잠금]
   → SSH: sudo usermod -L {account_name}

4. [모든 일반 계정 잠금 유지]
   → 다음 예약이 있으면 활성화 루틴으로 넘어감
   → 없으면 모든 계정 잠금 상태 유지 (안전)
```

### 3.3 스케줄러 실행 로직

```python
# 매 1분마다 실행
async def process_reservation_events():
    now = datetime.now(timezone.utc)
    
    # 시작할 예약 찾기
    starting_reservations = await find_reservations(
        start_at <= now,
        end_at > now,
        status = active,
        not_activated_yet
    )
    
    for res in starting_reservations:
        await activate_reservation(res)
        # 활성화 플래그 기록 (중복 방지)
    
    # 종료할 예약 찾기
    ending_reservations = await find_reservations(
        end_at <= now,
        status = active,
        not_deactivated_yet
    )
    
    for res in ending_reservations:
        await deactivate_reservation(res)
        # 비활성화 플래그 기록
```

## 4. 예외 계정 관리

### 4.1 예외 계정 우선순위

1. **시스템 기본 예외**: `EXCLUDE_USERS` (환경변수)
   - 예: root, dev, admin, teleport, ubuntu
2. **서버별 추가 예외**: `ServerResource.account_exclusions`
   - 예: monitoring, backup
3. **현재 예약자**: `Reservation.account_name`

### 4.2 예외 계정 병합 로직

```python
def get_exception_accounts(reservation: Reservation) -> set[str]:
    """예약에 대한 모든 예외 계정 목록 반환"""
    exceptions = set(settings.EXCLUDE_USERS)
    
    # 서버별 예외 추가
    if reservation.server_resource.account_exclusions:
        server_exceptions = [
            x.strip() 
            for x in reservation.server_resource.account_exclusions.split(',')
            if x.strip()
        ]
        exceptions.update(server_exceptions)
    
    # 현재 예약자 추가
    if reservation.account_name:
        exceptions.add(reservation.account_name)
    
    return exceptions
```

## 5. 구현 상세

### 5.1 새로운 서비스 파일

1. **`app/services/session_manager.py`**
   - `unlock_user(server, account)`: 계정 잠금 해제
   - `lock_user(server, account)`: 계정 잠금
   - `kill_user_processes(server, account, force=False)`: 프로세스 종료
   - `get_all_users(server)`: 서버의 모든 일반 계정 조회

2. **`app/services/session_scheduler.py`**
   - `process_reservation_events()`: 메인 스케줄러 로직
   - `activate_reservation(reservation)`: 예약 활성화
   - `deactivate_reservation(reservation)`: 예약 비활성화
   - `get_exception_accounts(reservation)`: 예외 계정 목록

3. **`app/services/teleport.py`** (향후 구현)
   - `grant_access(account, server)`: 접근 권한 부여
   - `revoke_access(account, server)`: 접근 권한 회수

### 5.2 데이터베이스 확장

**새 테이블: `reservation_session_logs`**

```sql
CREATE TABLE reservation_session_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_id UUID NOT NULL REFERENCES reservations(id),
    event_type VARCHAR(50) NOT NULL,  -- 'activated', 'deactivated', 'error'
    details JSONB,  -- 실행 결과, 에러 메시지 등
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**목적**
- 예약 활성화/비활성화 이력 추적
- 중복 실행 방지 (idempotency)
- 디버깅 및 감사 로그

### 5.3 스케줄러 통합 (APScheduler)

**`app/main.py`에 추가**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.services.session_scheduler import process_reservation_events

scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def startup_event():
    # 매 1분마다 실행
    scheduler.add_job(
        process_reservation_events,
        'interval',
        minutes=1,
        id='reservation_processor'
    )
    scheduler.start()

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
```

## 6. 에러 처리 및 안전성

### 6.1 에러 시나리오

1. **SSH 연결 실패**
   - 로그 기록 후 재시도 (최대 3회)
   - 관리자 알림

2. **계정 잠금/해제 실패**
   - 계정이 존재하지 않음 → 경고 로그, 건너뜀
   - 권한 부족 → 치명적 에러, 관리자 알림

3. **프로세스 종료 실패**
   - 일부 프로세스 종료 실패 → 경고 로그
   - 모든 프로세스 종료 실패 → 에러 로그

### 6.2 Idempotency 보장

- `reservation_session_logs`로 이벤트 기록
- 중복 활성화/비활성화 방지
- 실패 시 재시도 가능

### 6.3 Race Condition 방지

- 데이터베이스 트랜잭션 사용
- `SELECT FOR UPDATE`로 예약 잠금
- 이벤트 처리 중 상태 플래그 설정

## 7. 모니터링 및 알림

### 7.1 로그 레벨

- **INFO**: 정상적인 활성화/비활성화
- **WARNING**: 일부 작업 실패 (계정 없음, 일부 프로세스 종료 실패)
- **ERROR**: 치명적 실패 (SSH 연결 실패, 권한 부족)

### 7.2 메트릭 (향후)

- 예약 활성화 성공/실패 카운트
- 평균 처리 시간
- SSH 명령 실패율

## 8. 보안 고려사항

### 8.1 권한 최소화

- SSH 키는 sudo 권한 필요
- usermod, pkill 명령만 허용

### 8.2 감사 로그

- 모든 계정 잠금/해제 이벤트 기록
- 프로세스 종료 이벤트 기록
- 누가, 언제, 어떤 예약으로 실행했는지 추적

### 8.3 SSH 키 보안

- 데이터베이스 암호화 고려
- 환경변수로 암호화 키 관리

## 9. 테스트 전략

### 9.1 단위 테스트

- `SessionManager` 각 메서드 테스트 (Mock SSH)
- 예외 계정 병합 로직 테스트

### 9.2 통합 테스트

- 스케줄러 실행 테스트 (시간 Mock)
- 예약 생성 → 활성화 → 비활성화 플로우

### 9.3 수동 테스트

- 실제 서버에서 계정 잠금/해제 확인
- 프로세스 종료 확인
- Teleport 연동 (향후)

## 10. 구현 순서

### Phase 1: 기본 세션 관리
1. ✅ 설계 문서 작성
2. `session_manager.py` 구현
3. `reservation_session_logs` 테이블 생성
4. 단위 테스트

### Phase 2: 스케줄러 통합
5. `session_scheduler.py` 구현
6. APScheduler 통합
7. 통합 테스트

### Phase 3: 안정화
8. 에러 처리 강화
9. 로깅 개선
10. 모니터링 대시보드

### Phase 4: Teleport 연동 (향후)
11. Teleport API 클라이언트
12. 권한 부여/회수 로직
13. 종단간 테스트

## 11. 의존성

- `APScheduler`: 스케줄링
- `paramiko`: SSH 연결 (기존)
- `SQLAlchemy`: 데이터베이스 (기존)

## 12. 환경변수 추가

```bash
# Teleport 설정 (향후)
TELEPORT_API_URL=https://teleport.example.com
TELEPORT_API_TOKEN=<token>

# 스케줄러 설정
SCHEDULER_INTERVAL_MINUTES=1  # 기본값 1분
```
