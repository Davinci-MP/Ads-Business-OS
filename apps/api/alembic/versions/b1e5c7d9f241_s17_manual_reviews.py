"""S17: bảng manual_reviews — đối chiếu thủ công bằng mắt (không cần Meta token, D-041). Reversible."""
from alembic import op
import sqlalchemy as sa

from app.models.types import UTCDateTime

revision = "b1e5c7d9f241"
down_revision = "a4f7c9e21b83"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manual_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("ad_account_meta_id", sa.String(length=64), nullable=False),
        sa.Column("campaign_meta_id", sa.String(length=64), nullable=True),
        sa.Column("campaign_name", sa.Text(), nullable=True),
        sa.Column("observed_spend", sa.Numeric(16, 2), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("sheet_spend", sa.Numeric(16, 2), nullable=True),
        sa.Column("delta", sa.Numeric(16, 2), nullable=True),
        sa.Column("review_kind", sa.String(32), nullable=False, server_default="MANUAL_REVIEWED"),
        sa.Column("match_status", sa.String(32), nullable=False, server_default="REVIEWED"),
        sa.Column("sheet_key", sa.String(128), nullable=True),
        sa.Column("sheet_name", sa.String(128), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(64), nullable=False, server_default="owner"),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.UniqueConstraint(
            "customer_id", "business_date", "ad_account_meta_id", "campaign_meta_id", "review_kind",
            name="uq_manual_review",
        ),
    )
    op.create_index("ix_manual_reviews_customer_date", "manual_reviews", ["customer_id", "business_date"])


def downgrade() -> None:
    op.drop_index("ix_manual_reviews_customer_date", table_name="manual_reviews")
    op.drop_table("manual_reviews")
