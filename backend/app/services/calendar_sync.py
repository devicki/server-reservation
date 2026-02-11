import logging
from typing import Optional

from app.config import get_settings
from app.models.reservation import Reservation

logger = logging.getLogger(__name__)


class CalendarSyncService:
    """
    Google Calendar 단방향 동기화 서비스.

    설계 원칙:
    1. 동기화 실패가 예약 실패로 이어지지 않음
    2. 모든 동기화 작업은 DB 커밋 이후 수행
    3. 장애 시 로그 기록 후 skip
    """

    def __init__(self):
        self.settings = get_settings()
        self._service = None

    def _get_service(self):
        """Lazy-initialize Google Calendar API client."""
        if self._service is not None:
            return self._service

        if not self.settings.GOOGLE_CALENDAR_ENABLED:
            logger.debug("Google Calendar sync skipped: GOOGLE_CALENDAR_ENABLED is false")
            return None

        if not (self.settings.GOOGLE_SERVICE_ACCOUNT_FILE or "").strip():
            logger.warning(
                "Google Calendar sync skipped: GOOGLE_SERVICE_ACCOUNT_FILE is not set. "
                "Set it to the path of your Service Account JSON key (e.g. credentials/key.json, 상대 경로 가능)."
            )
            return None

        if not (self.settings.GOOGLE_CALENDAR_ID or "").strip():
            logger.warning(
                "Google Calendar sync skipped: GOOGLE_CALENDAR_ID is not set. "
                "Set it to your calendar ID (e.g. xxx@group.calendar.google.com)."
            )
            return None

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            credentials = service_account.Credentials.from_service_account_file(
                self.settings.GOOGLE_SERVICE_ACCOUNT_FILE.strip(),
                scopes=["https://www.googleapis.com/auth/calendar"],
            )
            self._service = build("calendar", "v3", credentials=credentials)
            logger.info(
                "Google Calendar client initialized. Calendar ID: %s",
                self.settings.GOOGLE_CALENDAR_ID.strip(),
            )
            return self._service
        except FileNotFoundError:
            logger.error(
                "Google Calendar: key file not found at %s. "
                "Use relative path from backend root (e.g. credentials/key.json).",
                self.settings.GOOGLE_SERVICE_ACCOUNT_FILE,
            )
            return None
        except Exception as e:
            logger.error("Failed to initialize Google Calendar service: %s", e, exc_info=True)
            return None

    def _build_event(self, reservation: Reservation) -> dict:
        """Build a Google Calendar event from a reservation."""
        user_name = reservation.user.name if reservation.user else "Unknown"
        resource_name = (
            reservation.server_resource.name if reservation.server_resource else "Unknown"
        )

        return {
            "summary": f"[{resource_name}] {reservation.title}",
            "description": (
                f"Reservationist: {user_name}\n"
                f"Resource: {resource_name}\n"
                f"{reservation.description or ''}"
            ),
            "start": {
                "dateTime": reservation.start_at.isoformat(),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": reservation.end_at.isoformat(),
                "timeZone": "UTC",
            },
        }

    async def sync_create(self, reservation: Reservation) -> Optional[str]:
        """
        Create a Google Calendar event for a reservation.
        Returns the Google event ID or None if sync failed.
        reservation must have user and server_resource loaded for _build_event.
        """
        service = self._get_service()
        if service is None:
            return None

        calendar_id = (self.settings.GOOGLE_CALENDAR_ID or "").strip()
        if not calendar_id:
            return None

        try:
            event = self._build_event(reservation)
            result = (
                service.events()
                .insert(calendarId=calendar_id, body=event)
                .execute()
            )
            logger.info("Calendar event created: %s for reservation %s", result["id"], reservation.id)
            return result["id"]
        except Exception as e:
            logger.error(
                "Failed to create calendar event for reservation %s: %s. "
                "Check: calendar shared with Service Account email (Make changes to events), "
                "GOOGLE_CALENDAR_ID correct.",
                reservation.id,
                e,
                exc_info=True,
            )
            return None

    async def sync_update(self, reservation: Reservation) -> bool:
        """Update the Google Calendar event for a reservation."""
        service = self._get_service()
        if service is None:
            return False

        if not reservation.google_event_id:
            # If no previous event, try creating one
            event_id = await self.sync_create(reservation)
            return event_id is not None

        try:
            event = self._build_event(reservation)
            service.events().update(
                calendarId=self.settings.GOOGLE_CALENDAR_ID,
                eventId=reservation.google_event_id,
                body=event,
            ).execute()
            logger.info(f"Calendar event updated: {reservation.google_event_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update calendar event {reservation.google_event_id}: {e}")
            return False

    async def sync_delete(self, reservation: Reservation) -> bool:
        """Delete the Google Calendar event for a reservation."""
        service = self._get_service()
        if service is None:
            return False

        if not reservation.google_event_id:
            return True  # No event to delete

        try:
            service.events().delete(
                calendarId=self.settings.GOOGLE_CALENDAR_ID,
                eventId=reservation.google_event_id,
            ).execute()
            logger.info(f"Calendar event deleted: {reservation.google_event_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete calendar event {reservation.google_event_id}: {e}")
            return False


# Singleton instance
calendar_sync_service = CalendarSyncService()
