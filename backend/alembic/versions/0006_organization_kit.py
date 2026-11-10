"""organization kit tables, and a member for every person who already signed in

Revision ID: 0006
Revises: 0005

Creates org_departments, org_roles, org_members and org_audit (aadi-org-kit). Every row of app_users becomes an active member;
the older role names in user_roles become the equal kit role (admin; none -> viewer; one -> that role; several -> a combined
custom role), so nobody gains or loses anything. app_users and user_roles are left in place (not read any more) for rollback.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from aadi_org import migration
from aadi_org.service import OrgService
from app.org import CATALOG, M, role_for_legacy

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    migration.create_tables(bind, M)
    people = bind.execute(sa.text("SELECT tenant_id, user_id, email, name FROM app_users ORDER BY created_at")).all()
    held: dict[tuple[str, str], set[str]] = {}
    for tenant, user, role in bind.execute(sa.text("SELECT tenant_id, user_id, role FROM user_roles")).all():
        held.setdefault((tenant, user), set()).add(role)
    session = Session(bind=bind)
    svc = OrgService(session, M, CATALOG)
    seen: set[tuple[str, str]] = set()
    for tenant, user, email, name in people:
        email = (email or "").strip().lower() or f"{user}@no-email.invalid"
        if (tenant, email) in seen:  # two sign-ins sharing one email in a company: keep the first, the second signs in as a new account
            email = f"{user}@duplicate.invalid"
        seen.add((tenant, email))
        role = role_for_legacy(svc, tenant, held.get((tenant, user), set()))
        session.add(M.Member(tenant_id=tenant, user_id=user, identity_id=user, email=email, name=name or "", role_id=role.id, status="active"))
    session.flush()


def downgrade() -> None:
    migration.drop_tables(op.get_bind(), M)
