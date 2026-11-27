from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def _engine_kwargs(url: str) -> dict:
    """Tham số engine theo loại DB.

    SQLite-family (local file, và Turso/libSQL `sqlite+libsql://` ở production theo D-066):
    - check_same_thread=False để BackgroundScheduler (nhiều luồng) dùng chung engine.
    - pool_pre_ping để phát hiện kết nối libSQL đã rớt (mạng) và tự mở lại.
    Postgres và DB khác: dùng pool_pre_ping, giữ mặc định còn lại.
    """
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Alias chuẩn đặt tên FastAPI dependency
get_db = get_session
