from app.db import SessionLocal
from app.services.meta_risk import scan_account_risks
from app.services.meta_tokens import NO_META_TOKEN_STATUS, build_job_connector, mock_blocked
from app.services.telegram_bot import get_configured_telegram_connector


def meta_risk_job():
    with SessionLocal() as db:
        with build_job_connector(db) as connector:
            if mock_blocked(connector):
                # Ngoài local, chưa có token thật → không quét rủi ro bằng dữ liệu giả lập.
                return {"status": NO_META_TOKEN_STATUS}
            result = scan_account_risks(db, connector, get_configured_telegram_connector(db))
            db.commit()
            return result
