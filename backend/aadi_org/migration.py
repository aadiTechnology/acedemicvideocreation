"""Create and drop the kit's tables from a product's Alembic revision, without repeating the column definitions:

    from aadi_org import migration
    from app.org import M
    def upgrade():  migration.create_tables(op.get_bind(), M)
    def downgrade(): migration.drop_tables(op.get_bind(), M)

Idempotent: tables that already exist are left alone."""
from __future__ import annotations


def _ordered(M):
    return [M.Department, M.Role, M.Member, M.Audit]  # departments and roles before the members that point at them


def create_tables(bind, M) -> None:
    for model in _ordered(M):
        model.__table__.create(bind, checkfirst=True)


def drop_tables(bind, M) -> None:
    for model in reversed(_ordered(M)):
        model.__table__.drop(bind, checkfirst=True)
