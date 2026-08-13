"""enforce normalized unique user contacts

Revision ID: 5b7e9c1d2a44
Revises: 246d5c542400
Create Date: 2026-08-13

Email already has a case-sensitive UNIQUE constraint.  Add a functional
UNIQUE index so case/whitespace variants (for example A@x.com vs a@x.com)
are also rejected at the database layer.  Phone already has a UNIQUE
constraint and is normalized by the auth service before writes.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "5b7e9c1d2a44"
down_revision: Union[str, Sequence[str], None] = "246d5c542400"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX uq_app_user_email_normalized
        ON app.app_user (LOWER(BTRIM(email)))
        WHERE email IS NOT NULL AND BTRIM(email) <> ''
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS app.uq_app_user_email_normalized")
