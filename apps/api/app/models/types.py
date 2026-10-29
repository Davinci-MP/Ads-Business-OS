from datetime import datetime, timezone

from sqlalchemy import DateTime as ImplDateTime, TypeDecorator


class UTCDateTime(TypeDecorator):
    """Timestamp stored as naive UTC on every dialect; returned as aware UTC."""
    impl = ImplDateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
