? 전 계정이 잠기는지? 프로세스 종료 하는지?

스케줄링이 여러 서버에 대해 돌아가는지 확인,

다른 사용자가 다른 예약 수정이 가능한지?

- 삭제를 진행하여 수정할수 있도록 삭제 버튼 따로 두기.

- 어드민은 수정 가능한지

페이지 이동시, 버그 존재

해당 서버의 - vLLM 성공 커맨드공유

teleport API 연동 - 예약자 계정에 Teleport 접속 권한 부여/회수 - Teleport API 호출로 Role 할당 및 제거

- 서버 목록 관리
  - 서버와 1:1 매핑된 캘린더 관리
    1. 서버와 1:1 매핑되는 캘린더를 관리 할 수 있다.
    2. 캘린더 연동 정보는 데이터베이스에 저장한다.

- teleport 접속 허용 / 차단
  - 계정의 teleport 접속 이력 조회
  - 예약 계정의 활동이력 디비 저장

- 알림 기능
  - 서버 상태 변경 알림 (예: 서버 다운 시)
  - 예약 만료 알림
  - 다른 사용자의 수정 히스토리도 알수 있도록

llm목록과 띄어주기 기능

새션 공유를 1 스케줄에 1 계정 접근이 아닌

- vRAM 의 할당 % 에 따라 동시 접속 허용

////////////////////////

/////////////////////

의견 게시판

nvprof와 ncu가 설치되어있으면 좋겠고 또한, Non-root user에게 profiling권한을 주셨으면 좋겠습니다.

수행 요 명령:
modprobe nvidia NVreg_RestrictProfilingToAdminUsers=0

관련 링크:
https://forums.developer.nvidia.com/t/nvprof-warning-the-user-does-not-have-permission-to-profile-on-the-target-device/72374

cuda sdk의 버전이 12.0으로 보입니다. 12.8 이상 혹은 13.1 이상의 버전으로 설치를 부탁드립니다.
