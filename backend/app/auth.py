"""Current user and role checks.

Production: the signed session cookie set by the Identity sign-in (app.oidc). Roles are this product's own
(admin, content_operator, reviewer, production_operator); a signed-in person with no role is a read-only viewer.
AUTH_MODE=dev is for local development and tests only and is refused when APP_ENV=production.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from app import db as database
from app.models import UserRole

ROLES = ("admin", "content_operator", "reviewer", "production_operator")


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    tenant_id: str
    email: str = ""
    name: str = ""
    roles: tuple[str, ...] = field(default_factory=tuple)

    def has(self, *wanted: str) -> bool:
        return "admin" in self.roles or any(r in self.roles for r in wanted)


def current_user(request: Request) -> CurrentUser:
    settings = request.app.state.settings
    if settings.auth_mode == "dev":
        h = request.headers
        roles = tuple(r for r in h.get("x-dev-roles", ",".join(ROLES)).split(",") if r)
        return CurrentUser(user_id=h.get("x-dev-user", "dev-user"), tenant_id=h.get("x-dev-tenant", "dev-tenant"),
                           email="dev@example.test", name="Developer", roles=roles)
    from app.oidc import read_session
    session = read_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Not signed in.")
    with database.session() as db:
        roles = tuple(db.scalars(select(UserRole.role).where(UserRole.tenant_id == session["tid"], UserRole.user_id == session["sub"])))
    return CurrentUser(user_id=session["sub"], tenant_id=session["tid"], email=session.get("email", ""), name=session.get("name", ""), roles=roles)


def require_roles(*wanted: str):
    """Dependency: the user needs one of these roles (admin always passes)."""

    def check(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if not user.has(*wanted):
            raise HTTPException(status_code=403, detail="Your role does not allow this action.")
        return user

    return check


writer = require_roles("content_operator")
admin_only = require_roles()
