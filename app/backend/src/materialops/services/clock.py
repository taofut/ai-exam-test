from datetime import datetime, timezone

from materialops.errors import AppError
from materialops.models import ExamClock


def utc(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AppError("VALIDATION_ERROR", "时间须为带时区的 ISO 8601 时刻。") from exc
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise AppError("VALIDATION_ERROR", "时间须为带时区的 ISO 8601 时刻。")
    return value.astimezone(timezone.utc)


def stored_utc(value):
    return utc(value.replace(tzinfo=timezone.utc) if isinstance(value, datetime) and value.tzinfo is None else value)


def iso(value):
    return stored_utc(value).isoformat().replace("+00:00", "Z") if value is not None else None


def now(session, fallback):
    row = session.get(ExamClock, 1)
    return stored_utc(row.now) if row else utc(fallback)

