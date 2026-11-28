"""Chuẩn hóa ADSOS_DATABASE_URL dùng chung cho app (db.py) và Alembic (env.py)."""

from __future__ import annotations


def normalize_database_url(raw: str | None) -> str:
    """Trả về URL SQLAlchemy dùng được, hoặc báo lỗi rõ ràng (không in ra URL vì chứa mật khẩu).

    - Bỏ khoảng trắng và dấu nháy bao quanh (hay gặp khi dán vào ô biến môi trường).
    - Railway/Neon/Supabase cấp `postgres://` hoặc `postgresql://` (SQLAlchemy mặc định
      psycopg2); ép sang `postgresql+psycopg://` vì image chỉ cài psycopg3.
    """
    url = (raw or "").strip().strip("'\"").strip()
    if not url:
        raise RuntimeError(
            "ADSOS_DATABASE_URL đang rỗng. Trên Railway hãy đặt "
            "ADSOS_DATABASE_URL=${{<tên service Postgres>.DATABASE_URL}} cho service backend."
        )
    if "://" not in url:
        raise RuntimeError(
            "ADSOS_DATABASE_URL không phải URL hợp lệ (thiếu '://'). Kiểm tra biến tham chiếu "
            "Railway có trỏ đúng tên service Postgres không."
        )
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    return url
