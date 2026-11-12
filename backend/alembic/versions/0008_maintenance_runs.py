"""maintenance_runs: remembers which one-time maintenance ids already ran (see app/seed_aadi_test.py). Additive.

Revision ID: 0008
Revises: 0007
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "maintenance_runs" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table("maintenance_runs", sa.Column("id", sa.String(80), primary_key=True), sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now()),
                    sa.Column("note", sa.Text))


def downgrade() -> None:
    op.drop_table("maintenance_runs")
