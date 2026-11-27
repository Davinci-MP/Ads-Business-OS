FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /code

# Turso/libSQL (D-066) làm DB production. Nếu build libsql-experimental lỗi vì
# thiếu wheel, đổi base image sang python:3.12 (full, có sẵn công cụ build).
COPY requirements.txt requirements-turso.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-turso.txt

COPY . .

EXPOSE 8000

# Railway đặt biến $PORT. Chạy migration (idempotent) rồi khởi động API.
# Scheduler (APScheduler) chạy được vì đây là tiến trình thường trực, không serverless.
CMD ["sh", "-c", "python -m alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
