# 예약 세션 스케줄러 사용 가이드

## 개요

예약 세션 스케줄러는 예약 시간에 따라 자동으로 서버 계정의 접근 권한을 제어하고 프로세스를 관리하는 시스템입니다.

## 시스템 동작 방식

### 1. 자동 스케줄링

스케줄러는 **매 1분마다** 자동으로 실행되며, 다음 작업을 수행합니다:

- **예약 시작 감지**: 현재 시각이 예약 시작 시간에 도달한 예약을 찾아 활성화
- **예약 종료 감지**: 현재 시각이 예약 종료 시간에 도달한 예약을 찾아 비활성화

### 2. 예약 활성화 (시작 시)

예약이 시작되면 다음 작업이 자동으로 수행됩니다:

```
1. 예약자 계정 잠금 해제
   → sudo usermod -U {예약자계정}
   
2. 예외 계정을 제외한 모든 계정 잠금
   → sudo usermod -L {기타계정}
   
3. 예외 계정을 제외한 모든 프로세스 종료
   → sudo pkill -u {기타계정}
```

**예외 계정**:
- 시스템 기본: `root`, `dev`, `admin`, `teleport`, `ubuntu`
- 서버별 추가: `ServerResource.account_exclusions` 설정
- 현재 예약자: 예약의 `account_name`

### 3. 예약 비활성화 (종료 시)

예약이 종료되면 다음 작업이 자동으로 수행됩니다:

```
1. 예약자 프로세스 강제 종료
   → sudo pkill -u {예약자계정} -9
   
2. 예약자 계정 잠금
   → sudo usermod -L {예약자계정}
```

## 설정 방법

### 1. 서버 SSH 설정

서버 자원에 SSH 연결 정보를 설정해야 합니다:

```bash
# API 호출 예시 (관리자 권한 필요)
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

**주의사항**:
- SSH 사용자는 `sudo` 권한이 필요합니다
- 비밀키는 OpenSSH 형식의 RSA 또는 Ed25519 키를 사용하세요

### 2. 서버별 예외 계정 설정

특정 서버에서 추가로 예외 처리할 계정을 설정할 수 있습니다:

```bash
curl -X PUT http://localhost:8000/api/v1/resources/{server_id} \
  -H "Authorization: Bearer {admin_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "account_exclusions": "monitoring,backup,jenkins"
  }'
```

### 3. 예약 생성 시 계정 지정

예약 생성 시 `account_name`을 반드시 지정해야 합니다:

```bash
curl -X POST http://localhost:8000/api/v1/reservations \
  -H "Authorization: Bearer {user_token}" \
  -H "Content-Type: application/json" \
  -d '{
    "server_resource_id": "{server_id}",
    "title": "GPU 훈련",
    "account_name": "user01",
    "start_at": "2026-02-15T10:00:00+09:00",
    "end_at": "2026-02-15T18:00:00+09:00"
  }'
```

## 세션 로그 조회

### API 엔드포인트

**모든 세션 로그 조회** (관리자 전용):
```bash
GET /api/v1/session-logs?limit=50&offset=0
```

**특정 예약의 세션 로그 조회**:
```bash
GET /api/v1/session-logs/reservation/{reservation_id}
```

### 로그 이벤트 타입

- `activated`: 예약 활성화 성공
- `deactivated`: 예약 비활성화 성공
- `error`: 오류 발생

### 로그 상세 정보

각 로그의 `details` 필드에는 다음 정보가 포함됩니다:

```json
{
  "reservation_id": "uuid",
  "account_name": "user01",
  "server_name": "GPU Server A",
  "exception_accounts": ["root", "dev", "admin", "user01"],
  "steps": [
    {
      "step": "unlock_reservee",
      "ok": true,
      "message": "User 'user01' unlocked successfully"
    },
    {
      "step": "lock_others",
      "ok": true,
      "message": "Locked 5 accounts, 0 failed",
      "details": {
        "locked": ["user02", "user03", "user04", "user05", "user06"],
        "failed": []
      }
    },
    {
      "step": "kill_processes",
      "ok": true,
      "message": "Killed processes for 5 accounts, 0 failed"
    }
  ],
  "success": true
}
```

## 수동 테스트

스케줄러를 수동으로 실행하여 테스트할 수 있습니다:

```bash
cd backend
python -m scripts.test_session_scheduler
```

## 트러블슈팅

### 1. 스케줄러가 실행되지 않음

**증상**: 예약 시간이 되어도 계정이 활성화되지 않음

**확인사항**:
- FastAPI 서버 로그 확인: `Starting session scheduler` 메시지 확인
- 데이터베이스 연결 상태 확인
- 서버 SSH 설정 확인

### 2. SSH 연결 실패

**증상**: 세션 로그에 "SSH error" 또는 "Authentication failed" 에러

**해결방법**:
- 서버 `host`, `ssh_port` 확인
- SSH 사용자 계정 확인
- SSH 비밀키 형식 확인 (OpenSSH 형식)
- 방화벽 설정 확인

### 3. 계정 잠금/해제 실패

**증상**: "Failed to lock/unlock user" 에러

**해결방법**:
- SSH 사용자에게 `sudo` 권한이 있는지 확인
- 서버에 해당 계정이 존재하는지 확인
- `/etc/sudoers` 설정 확인

### 4. 프로세스 종료 실패

**증상**: "Failed to kill processes" 에러

**해결방법**:
- 일부 프로세스는 종료에 실패할 수 있습니다 (정상)
- 로그의 `details.failed` 확인하여 어떤 계정에서 실패했는지 확인
- 필요시 서버에 직접 접속하여 수동으로 프로세스 종료

## 보안 고려사항

### SSH 키 관리

- SSH 비밀키는 데이터베이스에 평문으로 저장됩니다
- 프로덕션 환경에서는 데이터베이스 암호화를 권장합니다
- SSH 키는 최소 권한 원칙을 따라 관리하세요

### 예외 계정 설정

- 예외 계정에는 시스템 필수 계정만 포함하세요
- 불필요한 계정을 예외로 설정하면 예약 독점이 보장되지 않습니다

### 감사 로그

- 모든 세션 활성화/비활성화 이벤트는 `reservation_session_logs`에 기록됩니다
- 주기적으로 로그를 검토하여 이상 징후를 모니터링하세요

## FAQ

### Q1. 예약 시간 전에 미리 활성화할 수 있나요?

A. 현재는 예약 시작 시간 정확히 도달했을 때만 활성화됩니다. 필요시 스케줄러 로직을 수정하여 N분 전 활성화를 구현할 수 있습니다.

### Q2. 예약이 겹치는 경우 어떻게 되나요?

A. 예약 생성 시 충돌 검사를 수행하므로, 겹치는 예약은 생성되지 않습니다.

### Q3. 스케줄러 실행 주기를 변경할 수 있나요?

A. `app/main.py`의 `scheduler.add_job()` 부분에서 `minutes=1`을 원하는 값으로 변경하면 됩니다.

### Q4. Teleport 연동은 언제 추가되나요?

A. 현재는 OS 레벨 계정 잠금/해제만 구현되어 있습니다. Teleport API 연동은 향후 구현 예정입니다.

## 관련 문서

- [설계 문서](./SESSION_SCHEDULER_DESIGN.md)
- [아키텍처 문서](./ARCHITECTURE.md)
