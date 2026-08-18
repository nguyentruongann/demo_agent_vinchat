"""drop source_file from denormalized booking_product

Revision ID: 8c41e2f6a0bd
Revises: 7f3c2a9d8b10
Create Date: 2026-08-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c41e2f6a0bd"
down_revision: Union[str, Sequence[str], None] = "7f3c2a9d8b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("booking_product", "source_file", schema="core")


def downgrade() -> None:
    op.add_column(
        "booking_product",
        sa.Column("source_file", sa.Text(), nullable=True),
        schema="core",
    )
