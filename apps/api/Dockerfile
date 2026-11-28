FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /code

# Production dùng PostgreSQL (psycopg) — ổn định, SQLAlchemy hỗ trợ chuẩn.
COPY requirements.txt requirements-postgres.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-postgres.txt

COPY . .

EXPOSE 8000

# Railway đặt biến $PORT. Chạy migration (idempotent) rồi khởi động API.
# Tiến trình thường trực nên APScheduler chạy được (không serverless).
CMD ["sh", "-c", "python -m alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
