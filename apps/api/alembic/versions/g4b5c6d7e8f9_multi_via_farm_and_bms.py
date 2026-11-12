"""Tạo bảng via_profiles, synced_bms và cập nhật client_bm_preferences (Multi-VIA Farm & BM Routing).

Reversible migration:
- upgrade:
  - tạo bảng via_profiles (UID, profile_dir, user_agent, encrypted_credentials, proxy, live/token status, counts)
  - tạo bảng synced_bms (bm_id, via_profile_id, is_primary_rental, asset counts)
  - thêm cột via_profile_id vào bảng client_bm_preferences
- downgrade:
  - xóa cột via_profile_id khỏi client_bm_preferences
  - drop bảng synced_bms
  - drop bảng via_profiles
"""

from alembic import op
import sqlalchemy as sa

revision = "g4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Bảng via_profiles
    op.create_table(
        "via_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uid", sa.String(64), nullable=False),
        sa.Column("profile_name", sa.String(255), nullable=False),
        sa.Column("profile_dir", sa.String(255), nullable=False),
        sa.Column("user_agent", sa.String(500), nullable=False),
        sa.Column("encrypted_credentials", sa.Text(), nullable=False),
        sa.Column("proxy_config", sa.Text(), nullable=True),
        sa.Column("proxy_status", sa.String(32), nullable=False, server_default="UNKNOWN"),
        sa.Column("uid_live_status", sa.String(32), nullable=False, server_default="UNKNOWN"),
        sa.Column("token_status", sa.String(32), nullable=False, server_default="NONE"),
        sa.Column("bm_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ad_account_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_live_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_via_profiles_uid", "via_profiles", ["uid"], unique=True)
    op.create_index("ix_via_profiles_uid_live_status", "via_profiles", ["uid_live_status"])
    op.create_index("ix_via_profiles_token_status", "via_profiles", ["token_status"])

    # 2. Bảng synced_bms
    op.create_table(
        "synced_bms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bm_id", sa.String(64), nullable=False),
        sa.Column("via_profile_id", sa.Integer(), sa.ForeignKey("via_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_primary_rental", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("ad_account_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_synced_bms_bm_id", "synced_bms", ["bm_id"])
    op.create_index("ix_synced_bms_via_profile_id", "synced_bms", ["via_profile_id"])
    op.create_index("ix_synced_bms_is_primary_rental", "synced_bms", ["is_primary_rental"])

    # 3. Thêm via_profile_id vào client_bm_preferences qua batch mode
    with op.batch_alter_table("client_bm_preferences") as batch_op:
        batch_op.add_column(sa.Column("via_profile_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_client_bm_pref_via_profile",
            "via_profiles",
            ["via_profile_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    with op.batch_alter_table("client_bm_preferences") as batch_op:
        batch_op.drop_constraint("fk_client_bm_pref_via_profile", type_="foreignkey")
        batch_op.drop_column("via_profile_id")

    op.drop_index("ix_synced_bms_is_primary_rental", table_name="synced_bms")
    op.drop_index("ix_synced_bms_via_profile_id", table_name="synced_bms")
    op.drop_index("ix_synced_bms_bm_id", table_name="synced_bms")
    op.drop_table("synced_bms")

    op.drop_index("ix_via_profiles_token_status", table_name="via_profiles")
    op.drop_index("ix_via_profiles_uid_live_status", table_name="via_profiles")
    op.drop_index("ix_via_profiles_uid", table_name="via_profiles")
    op.drop_table("via_profiles")
