# GPU 헬스 체크 기능 설계 (Design Guide 산출물)

## 1. 요구사항 정리

- **목표**: GPU 서버들의 GPU에 대한 헬스 정보를 앱에서 제공.
- **제공 정보**:
  - **vRAM**: 할당(사용) / 전체 메모리 (MiB 또는 %)
  - **점유율(Utilization)**: GPU 연산 사용률 (%)
  - **온도(Temperature)**: GPU 온도 (°C)
  - 기타: GPU 인덱스, 이름 등 식별 정보
- **노출 위치**: 대시보드 또는 별도 페이지에서 조회 가능.

**가정**:
- 서버는 이미 `server_resources`에 등록되어 있으며, SSH(host, ssh_username, ssh_private_key)가 설정된 서버만 GPU 헬스를 수집 대상으로 한다.
- 원격 수집 도구는 해당 서버에 설치된 `nvidia-smi`를 SSH로 실행하여 결과를 파싱한다.
- SSH/네트워크 오류 또는 nvidia-smi 미설치 시 해당 서버는 "수집 실패" 상태로 표시한다.

---

## 2. 아키텍처

```
[클라이언트]
  - 모든 로그인 사용자: "GPU 헬스" 페이지에서 서버별 GPU 리소스 현황 조회
  - (선택) 대시보드 사이드바에 요약 위젯 링크

[Backend]
  - 기존 ServerResource + SSH 러너 활용.
  - 신규: GPU 헬스 수집 서비스 (SSH로 nvidia-smi 실행 → CSV/텍스트 파싱).
  - API:
    GET /api/v1/dashboard/gpu-health  → 전체 활성 서버에 대해 GPU 헬스 목록 (서버별 GPU 리스트)
    GET /api/v1/dashboard/gpu-health?server_resource_id={id}  → 특정 서버만 (선택)

[데이터 소스]
  - DB에는 GPU 스냅샷을 저장하지 않고, 조회 시점마다 SSH로 nvidia-smi 실행 (실시간성).
  - 향후 캐시(예: 30초 TTL) 또는 Background Worker 도입 가능.
```

**nvidia-smi 쿼리**:
- `nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu --format=csv,noheader,nounits`
- 출력 예: 한 줄당 한 GPU, 쉼표 구분. (메모리: MiB, utilization: %, temperature: °C)
- 파싱 시 숫자 필드가 "N/A"일 수 있음 → null 또는 0으로 처리.

---

## 3. 세분화된 작업 목록

| # | 작업 | 의존성 | 비고 |
|---|------|--------|------|
| 1 | GPU 헬스 스키마 정의 (Pydantic) | - | GpuInfo, ServerGpuHealth, GpuHealthResponse |
| 2 | gpu_health 서비스: nvidia-smi 실행 및 파싱 | ssh_runner | CSV 파싱, N/A 처리 |
| 3 | Dashboard API: GET /dashboard/gpu-health | 1, 2, get_db, get_current_user | 서버별로 SSH 호출 (병렬 가능) |
| 4 | Frontend: api client에 gpuHealth API | - | dashboardAPI.gpuHealth() |
| 5 | Frontend: GPU 헬스 전용 페이지 (GpuHealthPage) | 4 | 서버별 카드/테이블, vRAM/점유율/온도 표시 |
| 6 | App 라우트 및 네비: /gpu-health, 헤더 링크 | 5 | 로그인 사용자 공통 |

---

## 4. 개발 가이드 (구현 순서)

1. **Backend schemas** → `GpuInfo` (index, name, memory_total_mib, memory_used_mib, memory_free_mib, utilization_gpu_pct, temperature_gpu_c), `ServerGpuHealth` (server_resource_id, server_name, ok, error_message?, gpus), `GpuHealthResponse` (servers).
2. **Backend service** → `app/services/gpu_health.py`: `collect_gpu_health(host, port, username, private_key)` → 서버 한 대분 GPU 리스트 반환. 내부에서 nvidia-smi CSV 파싱.
3. **Backend dashboard router** → `GET /dashboard/gpu-health`: 활성 서버 중 SSH 설정된 것만 필터, 각 서버에 대해 `collect_gpu_health` 호출(병렬), 결과를 `GpuHealthResponse`로 반환.
4. **Frontend client** → `dashboardAPI.gpuHealth(server_resource_id?)` 추가.
5. **Frontend GpuHealthPage** → API 호출 후 서버별로 카드/테이블 렌더링. vRAM(used/total), 사용률 %, 온도 °C, 수집 실패 시 메시지 표시.
6. **Frontend App** → Route `/gpu-health`, 헤더에 "GPU 헬스" 링크 추가.

---

## 5. 참고 패턴/원칙

- **실시간 조회**: DB 저장 없이 요청 시마다 SSH로 nvidia-smi 실행. 응답 지연을 줄이기 위해 서버별 비동기 병렬 실행.
- **권한**: 기존 대시보드와 동일하게 로그인 사용자(get_current_user)만 허용. (관리자 전용이 아닌 전체 사용자 공개)
- **에러 처리**: SSH 실패 또는 nvidia-smi 실패 시 해당 서버만 `ok: false`, `error_message` 설정, 나머지 서버는 정상 반환.
- **기존 아키텍처 정합성**: ARCHITECTURE.md의 Dashboard API, ssh_runner 패턴과 동일하게 유지.
