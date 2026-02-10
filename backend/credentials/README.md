# Google Service Account credentials

이 디렉터리에 Google Calendar API용 Service Account JSON 키 파일을 저장하세요.

- 파일 예: `service-account-key.json`
- `.gitignore`에 의해 `*.json` 파일은 커밋되지 않습니다.

**로컬 실행 시**
- `GOOGLE_SERVICE_ACCOUNT_FILE=./credentials/service-account-key.json` (또는 절대 경로)

**Docker Compose 실행 시** (컨테이너 내부 경로)
- `GOOGLE_SERVICE_ACCOUNT_FILE=/app/credentials/service-account-key.json`
- `GOOGLE_CALENDAR_ENABLED=true`
- 백엔드가 `./backend`를 `/app`에 마운트하므로, 이 디렉터리는 컨테이너에서 `/app/credentials`입니다.
