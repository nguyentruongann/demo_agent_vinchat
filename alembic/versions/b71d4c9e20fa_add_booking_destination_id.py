"""add destination_id to booking_product

Revision ID: b71d4c9e20fa
Revises: 8c41e2f6a0bd
Create Date: 2026-08-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b71d4c9e20fa"
down_revision: Union[str, Sequence[str], None] = "8c41e2f6a0bd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "booking_product",
        sa.Column("destination_id", sa.Text(), nullable=True),
        schema="core",
    )
    op.create_index(
        "ix_booking_product_destination_id",
        "booking_product",
        ["destination_id"],
        unique=False,
        schema="core",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_booking_product_destination_id",
        table_name="booking_product",
        schema="core",
    )
    op.drop_column("booking_product", "destination_id", schema="core")
