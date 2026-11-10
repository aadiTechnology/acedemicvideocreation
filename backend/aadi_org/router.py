"""The organisation API, the same in every product: /org/me, /org/catalog, /org/users, /org/departments, /org/roles, /org/matrix, /org/audit.

A product mounts it with ``create_org_router(get_db=..., principal=..., M=..., catalog=...)``:
  * ``principal`` is the product's dependency that returns who is signed in (a ``Principal``): user id, company id, email, name;
  * the router resolves the person's member record and role, and every endpoint checks a capability.
Hooks let a product react to changes (for example to enrol a new person in Aadi Identity)."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from aadi_org.caps import Access, PermissionDenied
from aadi_org.catalog import ProductCatalog
from aadi_org.service import OrgError, OrgService


@dataclass
class Principal:
    user_id: str
    tenant_id: str
    email: str = ""
    name: str = ""
    identity_id: str | None = None


@dataclass
class Ctx:
    svc: OrgService
    db: Session
    principal: Principal
    member: Any
    access: Access

    def need(self, cap: str) -> None:
        self.access.require(cap)

    @property
    def actor(self) -> str:
        return self.principal.email or self.principal.user_id


class OrgHooks:
    """Override in a product. Called after the change is saved; an exception never undoes it."""

    def member_created(self, member: dict, principal: Principal) -> dict | None: ...  # a returned dict is sent back as "integration"
    def member_status_changed(self, member: dict, principal: Principal) -> dict | None: ...


class UserIn(BaseModel):
    email: str
    name: str = ""
    title: str = ""
    role_id: str | int | None = None
    department_id: str | int | None = None
    manager_id: str | int | None = None


class UserPatch(BaseModel):
    model_config = {"extra": "forbid"}
    name: str | None = None
    title: str | None = None
    role_id: str | int | None = None
    department_id: str | int | None = None
    manager_id: str | int | None = None


class DeptIn(BaseModel):
    name: str
    parent_id: str | int | None = None
    head_member_id: str | int | None = None


class DeptPatch(BaseModel):
    model_config = {"extra": "forbid"}
    name: str | None = None
    parent_id: str | int | None = None
    head_member_id: str | int | None = None


class RoleIn(BaseModel):
    key: str
    name: str
    description: str = ""
    caps: list[str] = Field(default_factory=list)


class RolePatch(BaseModel):
    model_config = {"extra": "forbid"}
    name: str | None = None
    description: str | None = None
    caps: list[str] | None = None


def create_org_router(*, get_db: Callable, principal: Callable, M, catalog: ProductCatalog, hooks: OrgHooks | None = None, prefix: str = "/org") -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["organization"])
    hooks = hooks or OrgHooks()

    @contextmanager
    def handled(db: Session):
        try:
            yield
        except OrgError as e:
            db.rollback()
            raise HTTPException(e.status, e.message) from None
        except PermissionDenied as e:
            db.rollback()
            raise HTTPException(403, e.message) from None

    def ctx(p: Principal = Depends(principal), db: Session = Depends(get_db)) -> Ctx:
        svc = OrgService(db, M, catalog)
        with handled(db):
            member = svc.resolve(p.tenant_id, p.user_id, p.email, p.name, p.identity_id)
            if member is None:
                raise OrgError(403, "NO_ACCOUNT", "You do not have an account in this product. Ask your administrator to add you.")
            db.commit()
            return Ctx(svc, db, p, member, svc.access_for(member))

    @router.get("/me")
    def me(c: Ctx = Depends(ctx)):
        return {"member": c.svc.member_out(c.member), "caps": sorted(c.access.caps), "product": catalog.product}

    @router.get("/catalog")
    def get_catalog(c: Ctx = Depends(ctx)):
        return catalog.describe()

    # ---- people --------------------------------------------------------------------------------------------------
    @router.get("/users")
    def users(status: str | None = None, department_id: str | None = None, q: str = "", c: Ctx = Depends(ctx)):
        with handled(c.db):
            c.need("org.users.view")
            return c.svc.list_members(c.principal.tenant_id, status, department_id, q)

    @router.post("/users", status_code=201)
    def add_user(b: UserIn, c: Ctx = Depends(ctx)):
        with handled(c.db):
            c.need("org.users.manage")
            out = c.svc.create_member(c.principal.tenant_id, c.actor, b.email, b.name, b.role_id, b.title, b.department_id, b.manager_id)
            c.db.commit()
        note = _call(hooks.member_created, out, c.principal)
        return {**out, "integration": note} if isinstance(note, dict) else out

    @router.patch("/users/{member_id}")
    def patch_user(member_id: str, b: UserPatch, c: Ctx = Depends(ctx)):
        with handled(c.db):
            c.need("org.users.manage")
            out = c.svc.update_member(c.principal.tenant_id, c.actor, member_id, b.model_dump(exclude_unset=True))
            c.db.commit()
            return out

    def _status(member_id: str, status: str, c: Ctx):
        with handled(c.db):
            c.need("org.users.manage")
            out = c.svc.set_status(c.principal.tenant_id, c.actor, member_id, status)
            c.db.commit()
        note = _call(hooks.member_status_changed, out, c.principal)
        return {**out, "integration": note} if isinstance(note, dict) else out

    @router.post("/users/{member_id}/suspend")
    def suspend(member_id: str, c: Ctx = Depends(ctx)):
        return _status(member_id, "suspended", c)

    @router.post("/users/{member_id}/reactivate")
    def reactivate(member_id: str, c: Ctx = Depends(ctx)):
        return _status(member_id, "active", c)

    # ---- departments ---------------------------------------------------------------------------------------------
    @router.get("/departments")
    def departments(c: Ctx = Depends(ctx)):
        with handled(c.db):
            c.need("org.users.view")
            return c.svc.list_departments(c.principal.tenant_id)

    @router.post("/departments", status_code=201)
    def add_department(b: DeptIn, c: Ctx = Depends(ctx)):
        with handled(c.db):
            c.need("org.departments.manage")
            out = c.svc.create_department(c.principal.tenant_id, c.actor, b.name, b.parent_id, b.head_member_id)
            c.db.commit()
            return out

    @router.patch("/departments/{dept_id}")
    def patch_department(dept_id: str, b: DeptPatch, c: Ctx = Depends(ctx)):
        with handled(c.db):
            c.need("org.departments.manage")
            out = c.svc.update_department(c.principal.tenant_id, c.actor, dept_id, b.model_dump(exclude_unset=True))
            c.db.commit()
            return out

    @router.delete("/departments/{dept_id}", status_code=204)
    def remove_department(dept_id: str, c: Ctx = Depends(ctx)):
        with handled(c.db):
            c.need("org.departments.manage")
            c.svc.delete_department(c.principal.tenant_id, c.actor, dept_id)
            c.db.commit()

    # ---- roles and features --------------------------------------------------------------------------------------
    @router.get("/roles")
    def roles(c: Ctx = Depends(ctx)):
        with handled(c.db):
            c.need("org.users.view")
            return c.svc.list_roles(c.principal.tenant_id)

    @router.post("/roles", status_code=201)
    def add_role(b: RoleIn, c: Ctx = Depends(ctx)):
        with handled(c.db):
            c.need("org.roles.manage")
            out = c.svc.create_role(c.principal.tenant_id, c.actor, b.key, b.name, b.caps, b.description)
            c.db.commit()
            return out

    @router.put("/roles/{role_id}")
    def change_role(role_id: str, b: RolePatch, c: Ctx = Depends(ctx)):
        with handled(c.db):
            c.need("org.roles.manage")
            out = c.svc.update_role(c.principal.tenant_id, c.actor, role_id, b.name, b.caps, b.description)
            c.db.commit()
            return out

    @router.delete("/roles/{role_id}", status_code=204)
    def remove_role(role_id: str, c: Ctx = Depends(ctx)):
        with handled(c.db):
            c.need("org.roles.manage")
            c.svc.delete_role(c.principal.tenant_id, c.actor, role_id)
            c.db.commit()

    @router.get("/matrix")
    def matrix(c: Ctx = Depends(ctx)):
        with handled(c.db):
            c.need("org.users.view")
            return c.svc.matrix(c.principal.tenant_id)

    @router.get("/audit")
    def audit(limit: int = 50, offset: int = 0, action: str = "", c: Ctx = Depends(ctx)):
        with handled(c.db):
            c.need("audit.view")
            return c.svc.list_audit(c.principal.tenant_id, limit, offset, action)

    return router


def _call(fn: Callable, *args):
    """Run a hook after the change is saved. A dict it returns is passed to the caller as "integration" (e.g. an enrolment outcome)."""
    try:
        return fn(*args)
    except Exception:  # noqa: BLE001 - a hook must never undo or fail a saved change
        import logging
        logging.getLogger("aadi_org").exception("organization hook failed")
        return {"ok": False, "message": "The follow-up step failed; the change itself was saved."}
