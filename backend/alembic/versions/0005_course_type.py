"""course type on the top-level container

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("school_classes", sa.Column("course_type", sa.String(length=16), nullable=False, server_default="school"))


def downgrade() -> None:
    op.drop_column("school_classes", "course_type")
