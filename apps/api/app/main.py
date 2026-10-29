from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.meta_sync import router as meta_sync_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.sheets import router as sheets_router
from app.api.v1.sheet_report_sources import router as sheet_report_sources_router
from app.api.v1.reviews import router as reviews_router
from app.api.v1.reports import router as reports_router
from app.api.v1.usdt import router as usdt_router
from app.api.v1.wallets import router as wallets_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    # S4: scheduler hằng giờ + checkpoint 09:00 VN (chỉ khi bật; tắt bằng ADSOS_SCHEDULER_ENABLED=0)
    from app.jobs.scheduler import start_scheduler, stop_scheduler
    from app.jobs.sheet_reports import start_sheet_scheduler, stop_sheet_scheduler
    from app.jobs.usdt_wallet import start_usdt_scheduler, stop_usdt_scheduler
    from app.jobs.exchange_wallets import start_exchange_scheduler, stop_exchange_scheduler

    start_scheduler()
    start_sheet_scheduler()
    start_usdt_scheduler()
    start_exchange_scheduler()
    try:
        yield
    finally:
        stop_exchange_scheduler()
        stop_usdt_scheduler()
        stop_sheet_scheduler()
        stop_scheduler()


app = FastAPI(title="Ads Business OS API", lifespan=lifespan)

@app.exception_handler(RequestValidationError)
async def safe_validation(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/api/v1/exchange/"):
        return JSONResponse(status_code=422, content={"detail": "Thông tin kết nối không hợp lệ; kiểm tra các trường bắt buộc."})
    return await request_validation_exception_handler(request, exc)


# Dashboard S5 chạy localhost (:3000) đọc API trực tiếp — chỉ dev/localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(set(["http://localhost:3000", "http://127.0.0.1:3000"] + settings.exchange_ui_origins.split(","))),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app_env": settings.app_env}


app.include_router(meta_sync_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(sheets_router, prefix="/api/v1")
app.include_router(sheet_report_sources_router, prefix="/api/v1")
app.include_router(reviews_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(usdt_router, prefix="/api/v1")
app.include_router(wallets_router, prefix="/api/v1")
