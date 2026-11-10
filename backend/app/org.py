"""Academic Video Creation's use of the organization kit (aadi-org-kit): its capabilities, default roles and tables.

Capabilities are what code checks; roles are data per company, seeded from ROLES below and editable by an administrator.
The four older role names (admin, content_operator, reviewer, production_operator) are still derived from capabilities
so the screens and API consumers that read ``roles`` keep working."""
from __future__ import annotations

from aadi_org.catalog import Capability, ProductCatalog, RoleDef
from aadi_org.models import build_models
from aadi_org.service import OrgService

from app.models import Base

M = build_models(Base)

CAPABILITIES = [
    Capability("lessons.manage", "Create lessons, import and edit content, send for review", (), "content"),
    Capability("structure.manage", "Add and change classes, courses, subjects, chapters and topics", (), "content"),
    Capability("review.decide", "Approve, request changes or reject a lesson version", (), "review"),
    Capability("video.generate", "Make, retry and cancel videos", (), "video"),
]
ROLES = [
    RoleDef("admin", "Administrator", description="Everything, including people, departments and roles"),
    RoleDef("content_operator", "Content operator", ("lessons.manage", "structure.manage"), "Creates lessons, imports and edits content, sends for review"),
    RoleDef("reviewer", "Reviewer", ("review.decide",), "Approves, requests changes or rejects"),
    RoleDef("production_operator", "Production operator", ("video.generate",), "Makes the videos"),
    RoleDef("viewer", "Viewer", (), "Can look at lessons and videos, changes nothing"),
]
CATALOG = ProductCatalog("academics", CAPABILITIES, ROLES, admin_role="admin", default_role="viewer",
                         features={"content": "Lessons and structure", "review": "Review", "video": "Videos"})

# the older role names, derived from capabilities (an administrator holds them all)
LEGACY_ROLES = ("admin", "content_operator", "reviewer", "production_operator")
_LEGACY_CAP = {"admin": "org.users.manage", "content_operator": "lessons.manage", "reviewer": "review.decide", "production_operator": "video.generate"}
_LEGACY_ROLE_CAPS = {r.key: r.caps for r in ROLES}


def legacy_roles(caps) -> tuple[str, ...]:
    held = {c.split(":")[0] for c in caps}
    if _LEGACY_CAP["admin"] in held:  # an administrator is just "admin" (they pass every check)
        return ("admin",)
    return tuple(r for r in LEGACY_ROLES if _LEGACY_CAP[r] in held)


def role_for_legacy(svc: OrgService, tenant: str, roles) -> object:
    """The kit role that equals a set of older roles: admin; none -> viewer; one -> that role; several -> a custom combined role."""
    wanted = [r for r in LEGACY_ROLES if r in set(roles)]
    svc.ensure_roles(tenant)
    if "admin" in wanted:
        key = "admin"
    elif not wanted:
        key = "viewer"
    elif len(wanted) == 1:
        key = wanted[0]
    else:
        caps = sorted({c for r in wanted for c in _LEGACY_ROLE_CAPS[r]})
        names = [next(x.name for x in ROLES if x.key == r) for r in wanted]
        return svc.ensure_role(tenant, "combo_" + "_".join(wanted), " + ".join(names), caps, "Combined role created from the older role list")
    from sqlalchemy import select
    return svc.db.scalar(select(M.Role).where(M.Role.tenant_id == tenant, M.Role.key == key))
