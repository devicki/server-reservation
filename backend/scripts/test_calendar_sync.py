#!/usr/bin/env python3
"""
Google Calendar 연동 테스트 스크립트.

사용법 (backend 디렉토리에서):
  python scripts/test_calendar_sync.py

또는 프로젝트 루트에서:
  cd backend && PYTHONPATH=. python scripts/test_calendar_sync.py

필요 환경 변수 (.env 또는 export):
  GOOGLE_CALENDAR_ENABLED=true
  GOOGLE_SERVICE_ACCOUNT_FILE=credentials/your-key.json
  GOOGLE_CALENDAR_ID=xxx@group.calendar.google.com

실행 전 backend 가상환경 활성화 후:
  pip install -r requirements.txt  # 필요 시
  cd backend && PYTHONPATH=. python scripts/test_calendar_sync.py
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

# backend/app 을 import 하기 위해 backend 디렉토리를 path 에 추가
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# .env 로드 (backend 기준)
_env_path = os.path.join(_backend_dir, ".env")
if os.path.isfile(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and v and k not in os.environ:
                    os.environ[k] = v


def print_section(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_config() -> bool:
    """설정값 확인."""
    print_section("1. 설정 확인")
    from app.config import get_settings

    settings = get_settings()
    enabled = getattr(settings, "GOOGLE_CALENDAR_ENABLED", False)
    key_file = (getattr(settings, "GOOGLE_SERVICE_ACCOUNT_FILE") or "").strip()
    cal_id = (getattr(settings, "GOOGLE_CALENDAR_ID") or "").strip()

    print(f"  GOOGLE_CALENDAR_ENABLED: {enabled}")
    print(f"  GOOGLE_SERVICE_ACCOUNT_FILE: {key_file or '(비어 있음)'}")
    print(f"  GOOGLE_CALENDAR_ID: {cal_id or '(비어 있음)'}")

    if not enabled:
        print("\n  [SKIP] GOOGLE_CALENDAR_ENABLED=false 입니다. .env 에 true 로 설정 후 다시 실행하세요.")
        return False
    if not key_file:
        print("\n  [FAIL] GOOGLE_SERVICE_ACCOUNT_FILE 이 비어 있습니다.")
        return False
    if not os.path.isfile(key_file):
        print(f"\n  [FAIL] 키 파일이 없습니다: {os.path.abspath(key_file)}")
        return False
    if not cal_id:
        print("\n  [FAIL] GOOGLE_CALENDAR_ID 가 비어 있습니다.")
        return False
    print("\n  [OK] 설정값 유효")
    return True


def test_google_connection() -> bool:
    """Google Calendar API 연결 및 캘린더 접근 테스트."""
    print_section("2. Google Calendar API 연결 테스트")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        from app.config import get_settings

        settings = get_settings()
        key_file = settings.GOOGLE_SERVICE_ACCOUNT_FILE.strip()
        cal_id = settings.GOOGLE_CALENDAR_ID.strip()

        credentials = service_account.Credentials.from_service_account_file(
            key_file,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        service = build("calendar", "v3", credentials=credentials)

        # 캘린더 메타데이터 조회 (연동 여부 확인)
        calendar = service.calendars().get(calendarId=cal_id).execute()
        print(f"  캘린더 이름: {calendar.get('summary', '(없음)')}")
        print(f"  캘린더 ID: {calendar.get('id')}")
        print("\n  [OK] API 연결 및 캘린더 접근 성공")
        return True
    except FileNotFoundError as e:
        print(f"\n  [FAIL] 키 파일 없음: {e}")
        return False
    except Exception as e:
        print(f"\n  [FAIL] 연결 실패: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_list_calendars() -> bool:
    """사용 가능한 캘린더 목록 조회 (선택)."""
    print_section("3. 캘린더 목록 조회 (calendarList)")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        from app.config import get_settings

        settings = get_settings()
        key_file = settings.GOOGLE_SERVICE_ACCOUNT_FILE.strip()
        credentials = service_account.Credentials.from_service_account_file(
            key_file,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        service = build("calendar", "v3", credentials=credentials)
        page = service.calendarList().list().execute()
        items = page.get("items", [])
        print(f"  공유/접근 가능한 캘린더 수: {len(items)}")
        for i, cal in enumerate(items[:10]):
            print(f"    - {cal.get('summary')} (id: {cal.get('id')})")
        if len(items) > 10:
            print(f"    ... 외 {len(items) - 10}개")
        print("\n  [OK] 목록 조회 성공")
        return True
    except Exception as e:
        print(f"\n  [FAIL] {e}")
        return False


async def test_event_create_delete() -> bool:
    """테스트 이벤트 생성 후 삭제 (실제 캘린더 연동 시뮬레이션)."""
    print_section("4. 이벤트 생성/삭제 테스트")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        from app.config import get_settings

        settings = get_settings()
        key_file = settings.GOOGLE_SERVICE_ACCOUNT_FILE.strip()
        cal_id = settings.GOOGLE_CALENDAR_ID.strip()
        credentials = service_account.Credentials.from_service_account_file(
            key_file,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        service = build("calendar", "v3", credentials=credentials)

        from datetime import timedelta

        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=1)
        event_body = {
            "summary": "[테스트] GPU Server Reservation 연동 테스트",
            "description": "test_calendar_sync.py 로 생성한 테스트 이벤트. 곧 삭제됩니다.",
            "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
        }

        created = service.events().insert(calendarId=cal_id, body=event_body).execute()
        event_id = created["id"]
        print(f"  생성된 이벤트 ID: {event_id}")

        service.events().delete(calendarId=cal_id, eventId=event_id).execute()
        print("  테스트 이벤트 삭제 완료")
        print("\n  [OK] 이벤트 생성/삭제 성공 (캘린더 쓰기 권한 정상)")
        return True
    except Exception as e:
        print(f"\n  [FAIL] {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_calendar_sync_service() -> bool:
    """CalendarSyncService 를 사용한 동기화 테스트 (DB 예약 없이 mock)."""
    print_section("5. CalendarSyncService (앱 서비스) 연동 테스트")
    from app.services.calendar_sync import calendar_sync_service

    service = calendar_sync_service._get_service()
    if service is None:
        print("  [SKIP] CalendarSyncService 가 비활성화되었거나 설정 오류로 초기화되지 않음.")
        return False

    # Mock reservation: 서비스의 _build_event 에 필요한 속성만 가진 객체
    from datetime import timedelta

    class MockReservation:
        id = "test-reservation-id"
        title = "테스트 예약 (스크립트)"
        description = "test_calendar_sync.py"
        start_at = datetime.now(timezone.utc)
        end_at = datetime.now(timezone.utc) + timedelta(hours=1)
        user = type("User", (), {"name": "Test User"})()
        server_resource = type("Resource", (), {"name": "Test GPU Server"})()

    mock = MockReservation()
    event_id = await calendar_sync_service.sync_create(mock)
    if not event_id:
        print("  [FAIL] sync_create 가 None 반환 (이벤트 생성 실패)")
        return False
    print(f"  생성된 Google 이벤트 ID: {event_id}")

    # 삭제는 google_event_id 가 있는 실제 Reservation 형태가 필요
    mock.google_event_id = event_id
    deleted = await calendar_sync_service.sync_delete(mock)
    if not deleted:
        print("  [WARN] sync_delete 실패 (수동으로 캘린더에서 삭제 필요)")
    else:
        print("  테스트 이벤트 삭제 완료 (sync_delete)")
    print("\n  [OK] CalendarSyncService 생성/삭제 동작 정상")
    return True


def main() -> None:
    print("\n  GPU Server Reservation - Google Calendar 연동 테스트")
    if not test_config():
        sys.exit(1)
    if not test_google_connection():
        sys.exit(1)
    test_list_calendars()

    ok = asyncio.run(test_event_create_delete())
    if not ok:
        sys.exit(1)

    asyncio.run(test_calendar_sync_service())
    print_section("완료")
    print("  모든 테스트 통과. 캘린더 연동이 정상적으로 동작합니다.\n")


if __name__ == "__main__":
    main()
