from decimal import Decimal

from app.models.customer import DEFAULT_FEE_RATE


def compute_service_fee(actual_spend: Decimal, fee_rate: Decimal = DEFAULT_FEE_RATE) -> Decimal:
    return Decimal(actual_spend) * Decimal(fee_rate)


def compute_total_with_fee(actual_spend: Decimal, fee_rate: Decimal = DEFAULT_FEE_RATE) -> Decimal:
    fee = compute_service_fee(actual_spend, fee_rate)
    return Decimal(actual_spend) + fee


def compute_drift(current_spend: Decimal, checkpoint_spend: Decimal) -> Decimal:
    return Decimal(current_spend) - Decimal(checkpoint_spend)
