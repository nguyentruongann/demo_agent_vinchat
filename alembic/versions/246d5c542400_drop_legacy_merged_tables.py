"""drop legacy merged tables

Revision ID: 246d5c542400
Revises: aa3d04a68965
Create Date: 2026-08-10 15:18:04.218552

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '246d5c542400'
down_revision: Union[str, Sequence[str], None] = 'aa3d04a68965'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("promotion_step", schema="public")
    op.drop_table("promotion_tag", schema="public")
    op.drop_table("attraction_itinerary_day", schema="public")
    op.drop_table("golf_course_map", schema="public")
    op.drop_table("room_amenity", schema="public")


def downgrade() -> None:
    """Downgrade schema."""
    pass
