"""The rules every product shares: roles seeded from the catalog, validated role changes, departments, members, first admin,
linking a person on first sign-in, last-administrator protection, manager and department cycles, and the activity log.

All methods are scoped to one company (``tenant_id``). The service never commits: the caller (the router) does."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aadi_org.caps import Access
from aadi_org.catalog import ProductCatalog

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ROLE_KEY = re.compile(r"^[a-z][a-z0-9_]{1,38}$")
STATUSES = ("invited", "active", "suspended")


class OrgError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class OrgService:
    def __init__(self, db: Session, M, catalog: ProductCatalog) -> None:
        self.db, self.M, self.catalog = db, M, catalog

    # ---- helpers -------------------------------------------------------------------------------------------------
    def cast(self, value):
        """An id from a URL, in the product's id type."""
        if self.M.text_ids:
            return str(value)
        try:
            return int(value)
        except (TypeError, ValueError):
            raise OrgError(404, "NOT_FOUND", "Not found.") from None

    def audit(self, tenant: str, actor: str, action: str, entity: str = "", entity_id="", **detail) -> None:
        self.db.add(self.M.Audit(tenant_id=tenant, actor=actor or "", action=action, entity=entity, entity_id=str(entity_id), detail=detail))

    def _get(self, model, tenant: str, obj_id, what: str):
        row = self.db.get(model, self.cast(obj_id))
        if row is None or row.tenant_id != tenant:  # another company's row looks exactly like a missing one
            raise OrgError(404, "NOT_FOUND", f"{what} not found.")
        return row

    # ---- roles ---------------------------------------------------------------------------------------------------
    def ensure_role(self, tenant: str, key: str, name: str, caps: list[str], description: str = ""):
        """Find a role by key, or create it as a custom (non built-in) role. For a product to map its own legacy roles."""
        r = self.db.scalar(select(self.M.Role).where(self.M.Role.tenant_id == tenant, self.M.Role.key == key))
        if r is None:
            r = self.M.Role(tenant_id=tenant, key=key, name=name, description=description, caps=self._check_caps(caps, key), is_system=False)
            self.db.add(r)
            self.db.flush()
        return r

    def ensure_roles(self, tenant: str) -> None:
        """Create any default role the company does not have yet. Roles an administrator edited are never overwritten."""
        have = {r.key for r in self.db.scalars(select(self.M.Role).where(self.M.Role.tenant_id == tenant))}
        added = False
        for rd in self.catalog.roles:
            if rd.key not in have:
                self.db.add(self.M.Role(tenant_id=tenant, key=rd.key, name=rd.name, description=rd.description, caps=self.catalog.role_caps(rd), is_system=True))
                added = True
        if added:
            self.db.flush()

    def role_out(self, r) -> dict:
        n = self.db.scalar(select(func.count()).select_from(self.M.Member).where(self.M.Member.role_id == r.id)) or 0
        return {"id": r.id, "key": r.key, "name": r.name, "description": r.description, "caps": list(r.caps or []), "is_system": r.is_system, "members": n}

    def list_roles(self, tenant: str) -> list[dict]:
        rows = self.db.scalars(select(self.M.Role).where(self.M.Role.tenant_id == tenant).order_by(self.M.Role.is_system.desc(), self.M.Role.name)).all()
        return [self.role_out(r) for r in rows]

    def _check_caps(self, caps: list[str], role_key: str) -> list[str]:
        caps = sorted(set(caps))
        problems = self.catalog.problems(caps)
        if problems:
            raise OrgError(422, "INVALID_CAPABILITY", "; ".join(problems))
        if role_key == self.catalog.admin_role:
            need = {"org.users.manage", "org.roles.manage"}
            if not need <= {c.split(":")[0] for c in caps}:
                raise OrgError(422, "ADMIN_ROLE", "The administrator role must keep the permissions to manage people and roles.")
        return caps

    def create_role(self, tenant: str, actor: str, key: str, name: str, caps: list[str], description: str = "") -> dict:
        key = key.strip().lower()
        if not ROLE_KEY.match(key):
            raise OrgError(422, "INVALID_KEY", "A role key is 2 to 39 lowercase letters, digits or underscores, starting with a letter.")
        if not name.strip():
            raise OrgError(422, "INVALID_NAME", "A role needs a name.")
        if self.db.scalar(select(self.M.Role).where(self.M.Role.tenant_id == tenant, self.M.Role.key == key)):
            raise OrgError(409, "DUPLICATE", "A role with this key already exists.")
        r = self.M.Role(tenant_id=tenant, key=key, name=name.strip(), description=description.strip(), caps=self._check_caps(caps, key), is_system=False)
        self.db.add(r)
        self.db.flush()
        self.audit(tenant, actor, "role.created", "role", r.id, key=key)
        return self.role_out(r)

    def update_role(self, tenant: str, actor: str, role_id, name: str | None = None, caps: list[str] | None = None, description: str | None = None) -> dict:
        r = self._get(self.M.Role, tenant, role_id, "Role")
        before = list(r.caps or [])
        if name is not None:
            if not name.strip():
                raise OrgError(422, "INVALID_NAME", "A role needs a name.")
            r.name = name.strip()
        if description is not None:
            r.description = description.strip()
        if caps is not None:
            r.caps = self._check_caps(caps, r.key)
            if not self._admin_left(tenant):
                raise OrgError(409, "LAST_ADMIN", "This change would leave no active administrator.")
        self.db.flush()
        added, removed = sorted(set(r.caps or []) - set(before)), sorted(set(before) - set(r.caps or []))
        self.audit(tenant, actor, "role.updated", "role", r.id, key=r.key, added=added, removed=removed)
        return self.role_out(r)

    def delete_role(self, tenant: str, actor: str, role_id) -> None:
        r = self._get(self.M.Role, tenant, role_id, "Role")
        if r.is_system:
            raise OrgError(409, "SYSTEM_ROLE", "A built-in role cannot be deleted.")
        if self.db.scalar(select(func.count()).select_from(self.M.Member).where(self.M.Member.role_id == r.id)):
            raise OrgError(409, "IN_USE", "People still have this role. Move them to another role first.")
        self.audit(tenant, actor, "role.deleted", "role", r.id, key=r.key)
        self.db.delete(r)
        self.db.flush()

    # ---- departments ---------------------------------------------------------------------------------------------
    def dept_out(self, d) -> dict:
        n = self.db.scalar(select(func.count()).select_from(self.M.Member).where(self.M.Member.department_id == d.id)) or 0
        return {"id": d.id, "name": d.name, "parent_id": d.parent_id, "head_member_id": d.head_member_id, "members": n}

    def list_departments(self, tenant: str) -> list[dict]:
        rows = self.db.scalars(select(self.M.Department).where(self.M.Department.tenant_id == tenant).order_by(self.M.Department.name)).all()
        return [self.dept_out(d) for d in rows]

    def _dept_cycle(self, tenant: str, dept_id, parent_id) -> bool:
        seen = set()
        cur = parent_id
        while cur is not None and cur not in seen:
            if cur == dept_id:
                return True
            seen.add(cur)
            row = self.db.get(self.M.Department, cur)
            cur = row.parent_id if row else None
        return False

    def create_department(self, tenant: str, actor: str, name: str, parent_id=None, head_member_id=None) -> dict:
        name = name.strip()
        if not name:
            raise OrgError(422, "INVALID_NAME", "A department needs a name.")
        if self.db.scalar(select(self.M.Department).where(self.M.Department.tenant_id == tenant, self.M.Department.name == name)):
            raise OrgError(409, "DUPLICATE", "A department with this name already exists.")
        parent = self._get(self.M.Department, tenant, parent_id, "Parent department").id if parent_id not in (None, "") else None
        head = self._get(self.M.Member, tenant, head_member_id, "Head of department").id if head_member_id not in (None, "") else None
        d = self.M.Department(tenant_id=tenant, name=name, parent_id=parent, head_member_id=head)
        self.db.add(d)
        self.db.flush()
        self.audit(tenant, actor, "department.created", "department", d.id, name=name)
        return self.dept_out(d)

    def update_department(self, tenant: str, actor: str, dept_id, fields: dict) -> dict:
        d = self._get(self.M.Department, tenant, dept_id, "Department")
        if "name" in fields and fields["name"] is not None:
            name = fields["name"].strip()
            if not name:
                raise OrgError(422, "INVALID_NAME", "A department needs a name.")
            if name != d.name and self.db.scalar(select(self.M.Department).where(self.M.Department.tenant_id == tenant, self.M.Department.name == name)):
                raise OrgError(409, "DUPLICATE", "A department with this name already exists.")
            d.name = name
        if "parent_id" in fields:
            pid = fields["parent_id"]
            parent = self._get(self.M.Department, tenant, pid, "Parent department").id if pid not in (None, "") else None
            if parent is not None and (parent == d.id or self._dept_cycle(tenant, d.id, parent)):
                raise OrgError(422, "CYCLE", "A department cannot sit under itself or one of its own sub-departments.")
            d.parent_id = parent
        if "head_member_id" in fields:
            hid = fields["head_member_id"]
            d.head_member_id = self._get(self.M.Member, tenant, hid, "Head of department").id if hid not in (None, "") else None
        self.db.flush()
        self.audit(tenant, actor, "department.updated", "department", d.id, name=d.name)
        return self.dept_out(d)

    def delete_department(self, tenant: str, actor: str, dept_id) -> None:
        d = self._get(self.M.Department, tenant, dept_id, "Department")
        if self.db.scalar(select(func.count()).select_from(self.M.Member).where(self.M.Member.department_id == d.id)):
            raise OrgError(409, "IN_USE", "People are still in this department. Move them first.")
        if self.db.scalar(select(func.count()).select_from(self.M.Department).where(self.M.Department.parent_id == d.id)):
            raise OrgError(409, "IN_USE", "This department has sub-departments. Move or delete them first.")
        self.audit(tenant, actor, "department.deleted", "department", d.id, name=d.name)
        self.db.delete(d)
        self.db.flush()

    # ---- members -------------------------------------------------------------------------------------------------
    def member_out(self, m) -> dict:
        role = self.db.get(self.M.Role, m.role_id)
        dept = self.db.get(self.M.Department, m.department_id) if m.department_id is not None else None
        mgr = self.db.get(self.M.Member, m.manager_id) if m.manager_id is not None else None
        return {"id": m.id, "user_id": m.user_id, "email": m.email, "name": m.name, "title": m.title, "status": m.status,
                "role_id": m.role_id, "role": role.key if role else None, "role_name": role.name if role else None,
                "department_id": m.department_id, "department": dept.name if dept else None,
                "manager_id": m.manager_id, "manager": (mgr.name or mgr.email) if mgr else None, "created_at": m.created_at.isoformat() if m.created_at else None}

    def list_members(self, tenant: str, status: str | None = None, department_id=None, q: str = "") -> list[dict]:
        stmt = select(self.M.Member).where(self.M.Member.tenant_id == tenant)
        if status:
            stmt = stmt.where(self.M.Member.status == status)
        if department_id not in (None, ""):
            stmt = stmt.where(self.M.Member.department_id == self.cast(department_id))
        rows = self.db.scalars(stmt.order_by(self.M.Member.name, self.M.Member.email)).all()
        if q:
            ql = q.lower()
            rows = [m for m in rows if ql in (m.name or "").lower() or ql in m.email.lower()]
        return [self.member_out(m) for m in rows]

    def _manager_cycle(self, tenant: str, member_id, manager_id) -> bool:
        seen, cur = set(), manager_id
        while cur is not None and cur not in seen:
            if cur == member_id:
                return True
            seen.add(cur)
            row = self.db.get(self.M.Member, cur)
            cur = row.manager_id if row else None
        return False

    def _role_is_admin(self, role) -> bool:
        return any(c.split(":")[0] == "org.users.manage" for c in (role.caps or []))

    def _admin_members(self, tenant: str, exclude=None):
        rows = self.db.execute(select(self.M.Member, self.M.Role).join(self.M.Role, self.M.Role.id == self.M.Member.role_id)
                               .where(self.M.Member.tenant_id == tenant, self.M.Member.status == "active")).all()
        return [m for m, r in rows if self._role_is_admin(r) and (exclude is None or m.id != exclude)]

    def _admin_left(self, tenant: str) -> bool:
        """True when at least one active member can still manage people. Skipped for a company with no members yet."""
        has_members = self.db.scalar(select(func.count()).select_from(self.M.Member).where(self.M.Member.tenant_id == tenant))
        return (not has_members) or bool(self._admin_members(tenant))

    def create_member(self, tenant: str, actor: str, email: str, name: str = "", role_id=None, title: str = "", department_id=None, manager_id=None) -> dict:
        email = email.strip().lower()
        if not EMAIL.match(email):
            raise OrgError(422, "INVALID_EMAIL", "Enter a valid email address.")
        if self.db.scalar(select(self.M.Member).where(self.M.Member.tenant_id == tenant, self.M.Member.email == email)):
            raise OrgError(409, "DUPLICATE", "This person is already in the list.")
        role = self._get(self.M.Role, tenant, role_id, "Role") if role_id not in (None, "") else self._default_role(tenant)
        dept = self._get(self.M.Department, tenant, department_id, "Department").id if department_id not in (None, "") else None
        mgr = self._get(self.M.Member, tenant, manager_id, "Manager").id if manager_id not in (None, "") else None
        m = self.M.Member(tenant_id=tenant, email=email, name=name.strip(), title=title.strip(), role_id=role.id, department_id=dept, manager_id=mgr, status="invited")
        self.db.add(m)
        self.db.flush()
        self.audit(tenant, actor, "member.created", "member", m.id, email=email, role=role.key)
        return self.member_out(m)

    def _default_role(self, tenant: str):
        """The catalog's default role (the least powerful one) for a person added without a role."""
        keys = [self.catalog.default_role] if self.catalog.default_role else []
        keys += [rd.key for rd in reversed(self.catalog.roles) if rd.key != self.catalog.admin_role] + [self.catalog.admin_role]
        for key in keys:
            r = self.db.scalar(select(self.M.Role).where(self.M.Role.tenant_id == tenant, self.M.Role.key == key))
            if r:
                return r

    def update_member(self, tenant: str, actor: str, member_id, fields: dict) -> dict:
        m = self._get(self.M.Member, tenant, member_id, "Person")
        changes = {}
        if "name" in fields and fields["name"] is not None:
            m.name = fields["name"].strip()
            changes["name"] = m.name
        if "title" in fields and fields["title"] is not None:
            m.title = fields["title"].strip()
            changes["title"] = m.title
        if "department_id" in fields:
            did = fields["department_id"]
            m.department_id = self._get(self.M.Department, tenant, did, "Department").id if did not in (None, "") else None
            changes["department_id"] = m.department_id
        if "manager_id" in fields:
            mid = fields["manager_id"]
            mgr = self._get(self.M.Member, tenant, mid, "Manager").id if mid not in (None, "") else None
            if mgr is not None and (mgr == m.id or self._manager_cycle(tenant, m.id, mgr)):
                raise OrgError(422, "CYCLE", "A person cannot report to themselves or to someone who reports to them.")
            m.manager_id = mgr
            changes["manager_id"] = m.manager_id
        if "role_id" in fields and fields["role_id"] not in (None, ""):
            role = self._get(self.M.Role, tenant, fields["role_id"], "Role")
            if role.id != m.role_id:
                m.role_id = role.id
                self.db.flush()
                if not self._admin_left(tenant):
                    raise OrgError(409, "LAST_ADMIN", "That would leave no active administrator.")
                changes["role"] = role.key
        self.db.flush()
        self.audit(tenant, actor, "member.updated", "member", m.id, email=m.email, **{k: (v if v is None or isinstance(v, (str, int)) else str(v)) for k, v in changes.items()})
        return self.member_out(m)

    def set_status(self, tenant: str, actor: str, member_id, status: str) -> dict:
        if status not in ("active", "suspended"):
            raise OrgError(422, "INVALID_STATUS", "Status is active or suspended.")
        m = self._get(self.M.Member, tenant, member_id, "Person")
        if status == "active" and m.status == "invited" and not m.user_id:
            return self.member_out(m)  # an invited person becomes active on first sign-in, not by a click
        old, m.status = m.status, status
        self.db.flush()
        if status == "suspended" and not self._admin_left(tenant):
            m.status = old
            raise OrgError(409, "LAST_ADMIN", "That would leave no active administrator.")
        self.audit(tenant, actor, "member.suspended" if status == "suspended" else "member.reactivated", "member", m.id, email=m.email)
        return self.member_out(m)

    # ---- sign-in -------------------------------------------------------------------------------------------------
    def member_for(self, tenant: str, user_id: str):
        return self.db.scalar(select(self.M.Member).where(self.M.Member.tenant_id == tenant, self.M.Member.user_id == str(user_id)))

    def resolve(self, tenant: str, user_id: str, email: str = "", name: str = "", identity_id: str | None = None):
        """The person's member record when they sign in. Order: known user id; a person an administrator added by email (linked now);
        the first person of a company (becomes its administrator); otherwise None (no account). A suspended person is refused."""
        self.ensure_roles(tenant)
        m = self.member_for(tenant, user_id)
        if m is None and email:
            m = self.db.scalar(select(self.M.Member).where(self.M.Member.tenant_id == tenant, self.M.Member.email == email.strip().lower(), self.M.Member.user_id.is_(None)))
            if m is not None:
                m.user_id, m.status = str(user_id), ("suspended" if m.status == "suspended" else "active")
                m.identity_id = identity_id or m.identity_id
                if name and not m.name:
                    m.name = name
                self.db.flush()
                self.audit(tenant, email, "member.linked", "member", m.id, email=m.email)
        if m is None and not self.db.scalar(select(func.count()).select_from(self.M.Member).where(self.M.Member.tenant_id == tenant)):
            admin = self.db.scalar(select(self.M.Role).where(self.M.Role.tenant_id == tenant, self.M.Role.key == self.catalog.admin_role))
            m = self.M.Member(tenant_id=tenant, user_id=str(user_id), identity_id=identity_id, email=(email or f"{user_id}").strip().lower(), name=name or "",
                              role_id=admin.id, status="active")
            self.db.add(m)
            self.db.flush()
            self.audit(tenant, email or str(user_id), "member.first_admin", "member", m.id, email=m.email)
        if m is not None and m.status == "suspended":
            raise OrgError(403, "SUSPENDED", "Your account in this product is suspended. Ask your administrator.")
        return m

    def access_for(self, member) -> Access:
        role = self.db.get(self.M.Role, member.role_id)
        return Access(role.caps or []) if role else Access([])

    # ---- reports -------------------------------------------------------------------------------------------------
    def matrix(self, tenant: str) -> dict:
        info = self.catalog.describe()
        roles = self.db.scalars(select(self.M.Role).where(self.M.Role.tenant_id == tenant).order_by(self.M.Role.is_system.desc(), self.M.Role.name)).all()
        out = []
        for r in roles:
            access = Access(r.caps or [])
            out.append({"id": r.id, "key": r.key, "name": r.name, "is_system": r.is_system, "grants": {c["key"]: access.scope(c["key"]) for c in info["capabilities"] if access.has(c["key"])}})
        return {**info, "roles": out}

    def list_audit(self, tenant: str, limit: int = 50, offset: int = 0, action: str = "") -> dict:
        stmt = select(self.M.Audit).where(self.M.Audit.tenant_id == tenant)
        if action:
            stmt = stmt.where(self.M.Audit.action.like(f"{action}%"))
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.scalars(stmt.order_by(self.M.Audit.id.desc()).limit(min(max(limit, 1), 200)).offset(max(offset, 0))).all()
        return {"total": total, "items": [{"id": a.id, "actor": a.actor, "action": a.action, "entity": a.entity, "entity_id": a.entity_id, "detail": a.detail,
                                           "at": a.at.astimezone(timezone.utc).isoformat() if isinstance(a.at, datetime) else None} for a in rows]}
