from app.connectors.meta import MetaAdsConnector
from app.db import SessionLocal
from app.services.meta_risk import scan_account_risks
from app.services.telegram_bot import get_configured_telegram_connector


def meta_risk_job():
    with SessionLocal() as db, MetaAdsConnector() as connector:
        result = scan_account_risks(db, connector, get_configured_telegram_connector(db))
        db.commit()
        return result
