"""assessment questions per lesson version (E11)

Revision ID: 0007
Revises: 0006
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assessment_questions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version_id", sa.String(36), sa.ForeignKey("lesson_versions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("answer_index", sa.Integer(), nullable=True),
        sa.Column("model_answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("image_file", sa.String(120), nullable=True),
        sa.Column("slide", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("assessment_questions")
