from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Alias chuẩn đặt tên FastAPI dependency
get_db = get_session
