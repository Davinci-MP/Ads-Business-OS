from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def _build_engine():
    """Tạo engine theo loại DB.

    - Turso/libSQL (`sqlite+libsql://host/?authToken=...&secure=true`, D-066):
      dialect `sqlalchemy-libsql` tự build URL `https://host` + `uri=True` khiến token
      KHÔNG tới driver (Turso trả 401 "empty JWT token"). Thay vào đó dùng SQLAlchemy
      `creator` gọi trực tiếp `libsql_experimental.connect("libsql://host", auth_token=...)`
      theo API chuẩn remote — bỏ qua phần build URL của dialect.
    - SQLite file (local/test): `check_same_thread=False` cho scheduler nhiều luồng.
    - DB khác: mặc định + pool_pre_ping.
    """
    url = make_url(settings.database_url)
    driver = url.drivername or ""

    if driver.startswith("sqlite+libsql") and url.host:
        query = dict(url.query)
        token = query.get("authToken") or query.get("auth_token") or ""
        remote = f"libsql://{url.host}"
        if url.port:
            remote += f":{url.port}"

        def _creator():
            import libsql_experimental as libsql

            return libsql.connect(remote, auth_token=token, check_same_thread=False)

        return create_engine(
            "sqlite+libsql://",
            creator=_creator,
            future=True,
            pool_pre_ping=True,
        )

    kwargs: dict = {"future": True, "pool_pre_ping": True}
    if driver.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(settings.database_url, **kwargs)


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
