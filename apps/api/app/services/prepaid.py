"""Chỉ ghi ngân sách sau phê duyệt; không suy diễn tỷ giá hoặc phí thuê."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html import escape
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.customer import Customer, utcnow
from app.models.finance import AuditLog, LedgerEntry, TelegramOutbox
from app.models.prepaid import ClientBalance, LedgerTransaction


def writable():
    if settings.app_env != "local":
        raise ValueError("Ghi ngân sách chỉ khả dụng trong môi trường local; môi trường thật cần luồng phê duyệt và sao lưu riêng.")


def money(value, currency):
    try:
        number = Decimal(str(value))
        if currency not in {"VND", "USD", "USDT", "EUR", "GBP"} or not number.is_finite() or abs(number) >= Decimal("100000000000000"):
            raise ValueError("Tiền tệ hoặc số tiền không hợp lệ hoặc vượt giới hạn lưu trữ.")
        result = number.quantize(Decimal("1") if currency == "VND" else Decimal("0.000001"), rounding=ROUND_HALF_UP)
        if abs(result) >= Decimal("100000000000000"):
            raise ValueError("Số tiền vượt giới hạn lưu trữ.")
        return result
    except (InvalidOperation, TypeError):
        raise ValueError("Số tiền không hợp lệ hoặc vượt giới hạn lưu trữ.") from None


def balance_for(db, customer_id, currency):
    if not db.get(Customer, customer_id):
        raise ValueError("Không tìm thấy khách hàng.")
    row = db.scalar(select(ClientBalance).where(ClientBalance.customer_id == customer_id, ClientBalance.currency == currency))
    if row is None:
        row = ClientBalance(customer_id=customer_id, currency=currency, amount=Decimal("0"))
        db.add(row)
        db.flush()
    return row


def request_transaction(db: Session, *, customer_id, currency, amount, kind, idempotency_key, evidence, actor, source_ledger_id=None):
    writable()
    amount = money(amount, currency)
    if amount <= 0 or kind not in {"DEPOSIT", "ACTUAL_SPEND", "SERVICE_FEE", "ACCOUNT_FEE", "CARD_FEE"} or not evidence.strip() or not actor.strip():
        raise ValueError("Cần số tiền dương, loại khoản hợp lệ, bằng chứng và người đề nghị.")
    existing = db.scalar(select(LedgerTransaction).where(LedgerTransaction.idempotency_key == idempotency_key))
    if existing:
        if (existing.customer_id, existing.currency, existing.amount, existing.kind, existing.source_ledger_id, existing.evidence) != (customer_id, currency, amount, kind, source_ledger_id, evidence):
            raise ValueError("Mã chống trùng đã được dùng cho nội dung khác.")
        return existing
    balance_for(db, customer_id, currency)
    if kind != "DEPOSIT":
        source = db.get(LedgerEntry, source_ledger_id) if source_ledger_id else None
        if not source or source.state != "FINAL" or source.customer_id != customer_id or source.currency != currency or source.amount != amount or source.entry_kind != kind:
            raise ValueError("Khoản trừ phải khớp chính xác một khoản đã chốt, cùng khách và tiền tệ.")
        if currency != "VND":
            raise ValueError("NEEDS_CONFIRMATION: ngân sách chi tiêu cần khoản VND đã xác nhận theo đúng kỳ tỷ giá.")
        if db.scalar(select(LedgerTransaction).where(LedgerTransaction.source_ledger_id == source_ledger_id)):
            raise ValueError("Khoản nguồn đã có đề nghị ghi sổ.")
    elif source_ledger_id is not None:
        raise ValueError("Khoản nạp cần bằng chứng nhận tiền riêng, không dùng nguồn chi tiêu.")
    tx = LedgerTransaction(customer_id=customer_id, currency=currency, amount=amount, kind=kind, idempotency_key=idempotency_key, evidence=evidence, requested_by=actor, source_ledger_id=source_ledger_id)
    db.add(tx)
    db.flush()
    audit(db, tx, actor, "PREPAID_REQUESTED")
    return tx


def audit(db, tx, actor, action):
    db.add(AuditLog(actor=actor, action=action, entity_type="ledger_transaction", entity_id=str(tx.id), detail={"kind": tx.kind, "currency": tx.currency}))


def approve_transaction(db, tx_id, actor):
    writable()
    tx = db.get(LedgerTransaction, tx_id)
    if not tx or not actor.strip():
        raise ValueError("Không tìm thấy đề nghị hoặc thiếu người duyệt.")
    if tx.status == "CREATED":
        tx.status = "APPROVED"
        tx.approved_by = actor
        audit(db, tx, actor, "PREPAID_APPROVED")
    return tx


def reject_transaction(db, tx_id, actor):
    writable()
    tx = db.get(LedgerTransaction, tx_id)
    if not tx or not actor.strip():
        raise ValueError("Không tìm thấy đề nghị hoặc thiếu người thao tác.")
    if tx.status in ("CREATED", "APPROVED"):
        tx.status = "REJECTED"
        tx.approved_by = actor
        audit(db, tx, actor, "PREPAID_REJECTED")
    return tx


def check_low_balance(db, row):
    low = row.low_threshold is not None and row.amount < row.low_threshold
    if low and not row.low_alert_active:
        customer = db.get(Customer, row.customer_id)
        info = row.deposit_info or "Chưa cấu hình thông tin nạp tiền; liên hệ quản trị viên. VietQR chưa được cấu hình."
        db.add(TelegramOutbox(message=f"⚠️ Số dư thấp: {escape(customer.name)}\nSố dư: {row.amount} {row.currency}\n{escape(info)}"))
    row.low_alert_active = low


def process_approved_transactions(db: Session):
    if settings.app_env != "local":
        return 0
    count = 0
    for tx in db.scalars(select(LedgerTransaction).where(LedgerTransaction.status == "APPROVED").order_by(LedgerTransaction.id)).all():
        if tx.kind != "DEPOSIT":
            source = db.get(LedgerEntry, tx.source_ledger_id, populate_existing=True) if tx.source_ledger_id else None
            if not source or (source.state, source.customer_id, source.currency, source.amount, source.entry_kind) != ("FINAL", tx.customer_id, tx.currency, tx.amount, tx.kind) or tx.currency != "VND":
                tx.status = "NEEDS_CONFIRMATION"
                audit(db, tx, "hệ thống", "PREPAID_SOURCE_CHANGED")
                continue
        row = balance_for(db, tx.customer_id, tx.currency)
        delta = tx.amount if tx.kind == "DEPOSIT" else -tx.amount
        try:
            money(row.amount + delta, tx.currency)
        except ValueError:
            tx.status = "NEEDS_CONFIRMATION"
            audit(db, tx, "hệ thống", "PREPAID_BALANCE_LIMIT")
            continue
        # Compare-and-set prevents two workers from applying the same approved row.
        claimed = db.execute(update(LedgerTransaction).where(LedgerTransaction.id == tx.id, LedgerTransaction.status == "APPROVED").values(status="EXECUTED", executed_at=utcnow()).execution_options(synchronize_session=False))
        if claimed.rowcount != 1:
            continue
        db.execute(update(ClientBalance).where(ClientBalance.id == row.id).values(amount=ClientBalance.amount + delta, updated_at=utcnow()).execution_options(synchronize_session=False))
        db.refresh(row)
        db.refresh(tx)
        audit(db, tx, tx.approved_by, "PREPAID_EXECUTED")
        check_low_balance(db, row)
        count += 1
    db.flush()
    return count
