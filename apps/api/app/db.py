from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.db_url import normalize_database_url


def _build_engine():
    """Tạo engine theo loại DB.

    - PostgreSQL (production, Railway/Neon/Supabase): psycopg3, pool_pre_ping.
    - Turso/libSQL (`sqlite+libsql://...`): dùng creator gọi thẳng
      libsql_experimental.connect("libsql://host", auth_token=...) — giữ để dự phòng.
    - SQLite file (local/test): check_same_thread=False cho scheduler nhiều luồng.
    """
    url = make_url(normalize_database_url(settings.database_url))
    driver = url.drivername or ""

    if driver.startswith("sqlite+libsql") and url.host:
        query = dict(url.query)
        token = query.get("authToken") or query.get("auth_token") or ""
        remote = f"libsql://{url.host}" + (f":{url.port}" if url.port else "")

        def _creator():
            import libsql_experimental as libsql

            return libsql.connect(remote, auth_token=token, check_same_thread=False)

        return create_engine("sqlite+libsql://", creator=_creator, future=True, pool_pre_ping=True)

    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if driver.startswith("sqlite"):
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
