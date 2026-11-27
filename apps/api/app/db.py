from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def _build_engine():
    """Tạo engine theo loại DB.

    - Turso/libSQL (`sqlite+libsql://...`, D-066): dialect `sqlalchemy-libsql` KHÔNG luôn
      chuyển `authToken` từ query URL sang DBAPI (gây lỗi Turso 401 "empty JWT token").
      Tách token khỏi URL và truyền thẳng qua connect_args `auth_token`; giữ `secure=...`
      trong URL cho dialect chọn giao thức. Không ép `check_same_thread` cho kết nối remote.
    - SQLite file (local/test): `check_same_thread=False` để scheduler nhiều luồng dùng chung.
    - DB khác: mặc định + pool_pre_ping.
    """
    url = make_url(settings.database_url)
    kwargs: dict = {"future": True, "pool_pre_ping": True}
    driver = url.drivername or ""
    if driver.startswith("sqlite+libsql"):
        query = dict(url.query)
        token = query.pop("authToken", None) or query.pop("auth_token", None) or ""
        url = url.set(query=query)  # bỏ authToken khỏi URL, giữ secure=...
        connect_args: dict = {}
        if token:
            connect_args["auth_token"] = token
        kwargs["connect_args"] = connect_args
    elif driver.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


engine = _build_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Alias chuẩn đặt tên FastAPI dependency
get_db = get_session
