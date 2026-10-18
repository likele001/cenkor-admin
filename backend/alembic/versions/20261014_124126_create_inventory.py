"""create inventory tables

Revision ID: 20261014_124126_gen_inventory
Revises: 20261007_0029_product_commerce
Create Date: 2026-10-14 12:41:26.873410

"""
from alembic import op
import sqlalchemy as sa

revision = "20261014_124126_gen_inventory"
down_revision = "20261018_0034_upgrade_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inventory_warehouse",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("type", sa.String(length=24), nullable=True),
        sa.Column("enable", sa.Boolean(), nullable=True, server_default=sa.text('true')),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("creator_id", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_inventory_warehouse_creator_id", "inventory_warehouse", ["creator_id"])
    op.create_index("uq_inventory_warehouse_code", "inventory_warehouse", ["code"], unique=True)

    op.create_table(
        "inventory_location",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=True),
        sa.Column("capacity", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("creator_id", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_inventory_location_creator_id", "inventory_location", ["creator_id"])
    op.create_index("uq_inventory_location_code", "inventory_location", ["code"], unique=True)
    op.create_index("ix_inventory_location_warehouse_id", "inventory_location", ["warehouse_id"])


def downgrade() -> None:
    op.drop_index("uq_inventory_location_code", table_name="inventory_location")
    op.drop_index("ix_inventory_location_warehouse_id", table_name="inventory_location")
    op.drop_index("ix_inventory_location_creator_id", table_name="inventory_location")
    op.drop_table("inventory_location")
    op.drop_index("uq_inventory_warehouse_code", table_name="inventory_warehouse")
    op.drop_index("ix_inventory_warehouse_creator_id", table_name="inventory_warehouse")
    op.drop_table("inventory_warehouse")
