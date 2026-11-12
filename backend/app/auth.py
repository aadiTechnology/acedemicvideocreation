"""Current user and permission checks.

Production: the signed session cookie set by the Identity sign-in (app.oidc). Identity decides whether a person may enter this
product (their company has it, they are an active member); this product decides who they are inside it: every person needs an
account (a member record in the organization kit), created by an administrator or, for the first person of a company, on first
sign-in. What a person may do comes from the capabilities of their role.
AUTH_MODE=dev is for local development and tests only and is refused when APP_ENV=production; it creates accounts on the fly and
reads the older X-Dev-Roles header (default: all roles) so tests can act as any role.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, Request

from aadi_org.caps import Access
from aadi_org.router import Principal
from aadi_org.service import OrgError, OrgService
from app import db as database
from app.org import CATALOG, LEGACY_ROLES, M, legacy_roles, role_for_legacy

ROLES = LEGACY_ROLES


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    tenant_id: str
    email: str = ""
    name: str = ""
    roles: tuple[str, ...] = field(default_factory=tuple)  # the older role names, derived from capabilities
    caps: frozenset = field(default_factory=frozenset)

    def can(self, cap: str) -> bool:
        return Access(self.caps).has(cap)

    def has(self, *wanted: str) -> bool:
        """Older check by role name (an administrator passes everything)."""
        return "admin" in self.roles or any(r in self.roles for r in wanted)


def principal(request: Request) -> Principal:
    """Who is signed in, before any account check."""
    settings = request.app.state.settings
    if settings.auth_mode == "dev":
        h = request.headers
        uid = h.get("x-dev-user", "dev-user")
        return Principal(user_id=uid, tenant_id=h.get("x-dev-tenant", os.environ.get("DEV_TENANT_ID", "dev-tenant")), email=h.get("x-dev-email", "dev@example.test" if uid == "dev-user" else f"{uid}@example.test"),
                         name="Developer", identity_id=uid)
    from app.oidc import read_session
    session = read_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Not signed in.")
    return Principal(user_id=session["sub"], tenant_id=session["tid"], email=session.get("email", ""), name=session.get("name", ""), identity_id=session["sub"])


def current_user(request: Request, p: Principal = Depends(principal)) -> CurrentUser:
    dev = request.app.state.settings.auth_mode == "dev"
    with database.session() as db:
        svc = OrgService(db, M, CATALOG)
        try:
            member = svc.resolve(p.tenant_id, p.user_id, p.email, p.name, p.identity_id)
            if dev and request.headers.get("x-dev-org") != "real":  # tests and local work act as any role through X-Dev-Roles; no header means every role. X-Dev-Org: real uses the real accounts and roles
                wanted = tuple(r for r in request.headers.get("x-dev-roles", ",".join(ROLES)).split(",") if r)
                if member is None:
                    role = role_for_legacy(svc, p.tenant_id, wanted)
                    member = M.Member(tenant_id=p.tenant_id, user_id=p.user_id, identity_id=p.user_id, email=p.email.lower(), name=p.name, role_id=role.id, status="active")
                    db.add(member)
                else:
                    member.role_id = role_for_legacy(svc, p.tenant_id, wanted).id
                db.flush()
        except OrgError as e:
            raise HTTPException(e.status, e.message) from None
        if member is None:
            raise HTTPException(403, "You do not have an account in this product. Ask your administrator to add you.")
        caps = svc.access_for(member).caps
        db.commit()
    return CurrentUser(user_id=p.user_id, tenant_id=p.tenant_id, email=p.email, name=p.name or member.name, roles=legacy_roles(caps), caps=frozenset(caps))


def require_cap(cap: str):
    """Dependency: the person's role must hold this capability."""

    def check(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if not user.can(cap):
            raise HTTPException(status_code=403, detail="Your role does not allow this action.")
        return user

    return check


def require_roles(*wanted: str):
    """Older check by role name, kept for compatibility: the person needs one of these (an administrator always passes)."""

    def check(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if not user.has(*wanted):
            raise HTTPException(status_code=403, detail="Your role does not allow this action.")
        return user

    return check


writer = require_cap("lessons.manage")
admin_only = require_cap("org.users.manage")
