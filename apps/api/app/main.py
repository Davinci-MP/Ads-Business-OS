from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.meta_sync import router as meta_sync_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.sheets import router as sheets_router
from app.api.v1.sheet_report_sources import router as sheet_report_sources_router
from app.api.v1.reviews import router as reviews_router
from app.api.v1.reports import router as reports_router
from app.api.v1.usdt import router as usdt_router
from app.api.v1.wallets import router as wallets_router
from app.api.v1.meta_mgmt import router as meta_mgmt_router
from app.api.v1.telegram_bot import router as telegram_bot_router
from app.api.v1.meta_risk import router as meta_risk_router
from app.api.v1.prepaid import router as prepaid_router
from app.api.v1.inventory import router as inventory_router
from app.api.v1.portal import router as portal_router
from app.api.v1.unified import router as unified_router
from app.api.v1.clients import router as clients_router
from app.api.v1.vias import router as vias_router
from app.api.v1.oauth import router as oauth_router
from app.api.v1.remote_commands import router as remote_commands_router
from app.api.v1.vcc_risk import router as vcc_risk_router
from app.api.v1.control_hub import router as control_hub_router
from app.api.v1.ads_check import router as ads_check_router
from app.api.v1.auth_staff import auth_router as auth_staff_router, staff_router
from app.api.v1.copilot import router as copilot_router
from app.api.v1.metaos_extension import router as metaos_extension_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    # S4: scheduler hằng giờ + checkpoint 09:00 VN (chỉ khi bật; tắt bằng ADSOS_SCHEDULER_ENABLED=0)
    from app.jobs.scheduler import start_scheduler, stop_scheduler
    from app.jobs.sheet_reports import start_sheet_scheduler, stop_sheet_scheduler
    from app.jobs.usdt_wallet import start_usdt_scheduler, stop_usdt_scheduler
    from app.jobs.exchange_wallets import start_exchange_scheduler, stop_exchange_scheduler
    from app.jobs.telegram_polling import start_telegram_polling, stop_telegram_polling

    from app.core.security import seed_default_owner

    seed_default_owner()
    start_scheduler()
    start_sheet_scheduler()
    start_usdt_scheduler()
    start_exchange_scheduler()
    start_telegram_polling()
    try:
        yield
    finally:
        stop_telegram_polling()
        stop_exchange_scheduler()
        stop_usdt_scheduler()
        stop_sheet_scheduler()
        stop_scheduler()


app = FastAPI(title="Ads Business OS API", lifespan=lifespan)
app.mount(
    "/metaos-assets",
    StaticFiles(directory=Path(__file__).resolve().parent / "static" / "metaos"),
    name="metaos-assets",
)

@app.exception_handler(RequestValidationError)
async def safe_validation(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/api/v1/exchange/"):
        return JSONResponse(status_code=422, content={"detail": "Thông tin kết nối không hợp lệ; kiểm tra các trường bắt buộc."})
    if request.url.path.startswith(("/api/v1/prepaid", "/api/v1/meta-risk", "/api/v1/meta/")):
        return JSONResponse(status_code=422, content={"detail": "Dữ liệu không hợp lệ; kiểm tra các trường bắt buộc, số tiền và mã tài khoản."})
    return await request_validation_exception_handler(request, exc)


# Dashboard chạy localhost/127.0.0.1 (mọi cổng dev :3000, :3001...) đọc API trực tiếp
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(set(["http://localhost:3000", "http://127.0.0.1:3000"] + [o.strip() for o in settings.exchange_ui_origins.split(",") if o.strip()])),
    allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1)(:[0-9]+)?|chrome-extension://.*)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict:
    return {
        "service": "Ads Business OS API",
        "status": "online",
        "app_env": settings.app_env,
        "docs_url": "/docs",
        "health_url": "/health",
        "web_crm_url": "http://localhost:3000",
        "message": "Backend API đang hoạt động bình thường. Để truy cập giao diện Web CRM, vui lòng mở http://localhost:3000.",
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app_env": settings.app_env, "connected": True}


app.include_router(meta_sync_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(sheets_router, prefix="/api/v1")
app.include_router(sheet_report_sources_router, prefix="/api/v1")
app.include_router(reviews_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(usdt_router, prefix="/api/v1")
app.include_router(wallets_router, prefix="/api/v1")
app.include_router(meta_mgmt_router, prefix="/api/v1")
app.include_router(telegram_bot_router, prefix="/api/v1")
app.include_router(meta_risk_router, prefix="/api/v1")
app.include_router(prepaid_router, prefix="/api/v1")
app.include_router(inventory_router, prefix="/api/v1")
app.include_router(portal_router, prefix="/api/v1")
app.include_router(unified_router, prefix="/api/v1")
app.include_router(clients_router, prefix="/api/v1")
app.include_router(vias_router, prefix="/api/v1")
app.include_router(oauth_router, prefix="/api/v1")
app.include_router(remote_commands_router, prefix="/api/v1")
app.include_router(vcc_risk_router, prefix="/api/v1/vcc-risk", tags=["VCC Risk"])
app.include_router(control_hub_router, prefix="/api/v1")
app.include_router(ads_check_router, prefix="/api/v1")
app.include_router(auth_staff_router, prefix="/api/v1")
app.include_router(staff_router, prefix="/api/v1")
app.include_router(copilot_router, prefix="/api/v1")
app.include_router(metaos_extension_router)
