# 릴리즈 노트

기능 추가 및 변경 사항을 기록합니다.

---

## 2026-02-27

### 세션 로그 필터 확장

- **변경 내용:** 세션 로그 목록에서 기존 예약 ID 필터 외에 **일시, 서버, Title, 예약 사용자, 이벤트** 필터를 추가했습니다.
- **필터 항목**
  - **일시:** 로그 생성 일시 범위(시작~끝)로 조회
  - **서버:** 대상 서버(리소스) 선택
  - **Title:** 예약 타이틀 부분 일치 검색
  - **예약 사용자:** 예약한 사용자 선택
  - **예약 ID:** 기존과 동일 (UUID)
  - **이벤트:** 활성화 / 비활성화 / 오류 중 선택
- **API:** `GET /api/v1/session-logs/` 쿼리 파라미터 확장 (`start_date`, `end_date`, `server_resource_id`, `reservation_title`, `user_id`, `event_type`).

### 관리자 예약 상세 모달 개선

- **변경 내용:** 관리자가 다른 사용자의 예약을 클릭했을 때, 기존처럼 삭제 확인만 뜨던 것을 **상세 정보 모달**을 먼저 띄우도록 변경했습니다.
- **동작:** 모달에서 예약 상세를 확인한 뒤 **삭제**(확인 후 취소) 또는 **수정**(저장)이 가능합니다. 일반 사용자가 본인 예약을 클릭했을 때와 동일한 흐름입니다.
- **백엔드:** 관리자가 타인 예약을 수정할 수 있도록 API 권한을 확장했습니다 (기존에는 삭제만 가능).

### Local LLM Serve 사례 공유

- **추가 내용:** 예약 서버에서 local LLM 모델 serve에 성공한 사례를 공유하는 **사례 공유** 페이지를 추가했습니다.
- **기능**
  - **목록:** 모델명, 서버, 작성자, 등록일 기준 목록 조회 (20개 단위 페이징)
  - **등록:** 대상 서버, 모델명, 모델 상세, Serve 커맨드, 리소스 할당, 메모 입력 후 등록
  - **상세:** 한 건의 사례를 열어 커맨드·리소스 할당 등 전체 내용 확인
- **접근:** 로그인한 사용자만 이용 가능 (헤더 메뉴 **사례 공유** → `/serve-cases`)
- **백엔드:** `serve_cases` 테이블 및 `GET/POST /api/v1/serve-cases/`, `GET /api/v1/serve-cases/{id}` API 추가

---

## 2026-02-24

### CUDA Toolkit 버전 업그레이드 (v12.0 → v12.8)

변경 내용: 기존 CUDA SDK 12.0 버전을 최신 요구 사양인 12.8로 업그레이드 완료.

작업 목적: H100 GPU 성능 최적화 및 최신 프레임워크(vLLM 등) 호환성 확보.

주요 변경 사항:

NVIDIA 공식 저장소(cuda-keyring) 등록 및 업데이트.

cuda-toolkit-12-8 패키지 설치.

시스템 환경 변수(PATH, LD_LIBRARY_PATH) 경로 수정 적용.

확인 방법: nvcc --version 명령어를 통해 release 12.8 확인.

\*\* 기존 cuda 12.0 에서 12.8 로 업그레이드 진행하면서,
환경변수의 수정이 필요.

전역으로 적용하기 위해, /etc/profile.d/cuda.sh 파일을 생성하여 CUDA 경로를 추가하는 방식으로 변경.
사용자 로그인시 자동으로 적용되도록 설정.

# 새로운 설정 파일 생성 (모든 사용자용)

echo 'export PATH=/usr/local/cuda-12.8/bin:$PATH' | sudo tee /etc/profile.d/cuda.sh
echo 'export LD_LIBRARY_PATH=/usr/local/cuda-12.8/lib64:$LD_LIBRARY_PATH' | sudo tee -a /etc/profile.d/cuda.sh

# 실행 권한 부여

sudo chmod +x /etc/profile.d/cuda.sh

### GPU 프로파일링 권한 개방 (Non-root User)

변경 내용: 일반 계정에서도 GPU 성능 분석 도구(nvprof, ncu)를 사용할 수 있도록 커널 모듈 설정 변경.

작업 목적: 개발자 및 분석가가 루트 권한 없이 GPU 커널 성능 및 메모리 대역폭을 분석할 수 있는 환경 제공.

적용 사항:

NVreg_RestrictProfilingToAdminUsers=0 옵션 적용.

/etc/modprobe.d/nvidia-profiler.conf 설정을 통한 영구적 권한 부여.

도구 경로: /usr/local/cuda-12.8/bin/ncu 및 nvprof 사용 가능.

---

### 릴리즈 노트 뷰어

- MD 파일을 볼 수 있는 뷰어 페이지 추가 (`/release-notes`)
- 이 파일(`RELEASE_NOTES.md`)을 수정하면 앱에서 바로 확인할 수 있습니다.

### 의견 게시판 개선

- 의견 목록에 **댓글** 기능 추가
- 의견에 **좋아요 반응** 기능 추가 (토글)

### 헤더 공통화 및 UX 개선

- 헤더를 공통 컴포넌트(`Header`)로 통일
- 모든 페이지에서 동일한 네비게이션 링크 표시
- 현재 페이지 메뉴 강조 (NavLink)
- 네비게이션 링크를 헤더 좌측으로 이동

### 예약 계정 잠금·해제 시 SSH 차단/복구

- **비활성화(잠금):** 계정 잠금 시 **SSH 키 접근도 차단**
- **재활성화(해제):** 계정 해제 시 **SSH 키 접근 허용**

---
