"""MaxCare feature set: via_categories, VIA category/profile metadata, daily_budget on synced_ad_accounts, ad_account_snapshots and maxcare_activity_logs.

Reversible migration:
- upgrade:
  - new table via_categories
  - via_profiles: category_id (FK, nullable), device_name, friends_count, groups_count, gender, birthday, note
  - synced_ad_accounts: daily_budget, last_report_synced_at
  - new table ad_account_snapshots (append-only, unique act_id + snapshot_at)
  - new table maxcare_activity_logs (append-only)
- downgrade: drop new tables/columns in reverse order.
"""

from alembic import op
import sqlalchemy as sa


revision = "j7a8b9c0d1e2"
down_revision = "7502200ab430"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "via_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("color", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    with op.batch_alter_table("via_profiles") as batch_op:
        batch_op.add_column(sa.Column("category_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("device_name", sa.String(128), nullable=True))
        batch_op.add_column(sa.Column("friends_count", sa.Integer(), nullable=True, server_default="0"))
        batch_op.add_column(sa.Column("groups_count", sa.Integer(), nullable=True, server_default="0"))
        batch_op.add_column(sa.Column("gender", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("birthday", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("note", sa.Text(), nullable=True))
        # (tên constraint, bảng được tham chiếu, cột nguồn, cột đích) — bảng nguồn là via_profiles.
        batch_op.create_foreign_key(
            "fk_via_profiles_category_id", "via_categories", ["category_id"], ["id"]
        )
        batch_op.create_index("ix_via_profiles_category_id", ["category_id"])

    with op.batch_alter_table("synced_ad_accounts") as batch_op:
        batch_op.add_column(sa.Column("daily_budget", sa.Float(), nullable=True, server_default="0"))
        batch_op.add_column(sa.Column("last_report_synced_at", sa.DateTime(), nullable=True))

    op.create_table(
        "ad_account_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ad_account_id",
            sa.Integer(),
            sa.ForeignKey("synced_ad_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("act_id", sa.String(64), nullable=False),
        sa.Column("status_dot", sa.String(32), nullable=True),
        sa.Column("account_status", sa.Integer(), nullable=True),
        sa.Column("balance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("threshold", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ad_trust_dsl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("daily_budget", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_spend", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(16), nullable=False, server_default="VND"),
        sa.Column("snapshot_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, server_default="MAXCARE_REPORT_SYNC"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("act_id", "snapshot_at", name="uq_ad_account_snapshot"),
    )
    op.create_index("ix_ad_account_snapshots_act_id", "ad_account_snapshots", ["act_id"])
    op.create_index(
        "ix_ad_account_snapshots_ad_account_id", "ad_account_snapshots", ["ad_account_id"]
    )

    op.create_table(
        "maxcare_activity_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "via_profile_id",
            sa.Integer(),
            sa.ForeignKey("via_profiles.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_maxcare_activity_logs_via_profile_id", "maxcare_activity_logs", ["via_profile_id"]
    )
    op.create_index("ix_maxcare_activity_logs_created_at", "maxcare_activity_logs", ["created_at"])


def downgrade():
    op.drop_index("ix_maxcare_activity_logs_created_at", table_name="maxcare_activity_logs")
    op.drop_index("ix_maxcare_activity_logs_via_profile_id", table_name="maxcare_activity_logs")
    op.drop_table("maxcare_activity_logs")

    op.drop_index("ix_ad_account_snapshots_ad_account_id", table_name="ad_account_snapshots")
    op.drop_index("ix_ad_account_snapshots_act_id", table_name="ad_account_snapshots")
    op.drop_table("ad_account_snapshots")

    with op.batch_alter_table("synced_ad_accounts") as batch_op:
        batch_op.drop_column("last_report_synced_at")
        batch_op.drop_column("daily_budget")

    with op.batch_alter_table("via_profiles") as batch_op:
        batch_op.drop_index("ix_via_profiles_category_id")
        batch_op.drop_column("category_id")
        batch_op.drop_column("device_name")
        batch_op.drop_column("friends_count")
        batch_op.drop_column("groups_count")
        batch_op.drop_column("gender")
        batch_op.drop_column("birthday")
        batch_op.drop_column("note")

    op.drop_table("via_categories")
