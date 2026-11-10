"""Tables: departments, roles, members and an activity log.

``build_models(Base, id_type=...)`` creates them on a product's own SQLAlchemy ``Base``, so ids follow the product's convention
(text uuids or whole numbers) and no foreign key points at a product table the kit does not know. A company is a plain
``tenant_id`` column (Academic stores Identity's company id; Project Tracker stores its own tenant id)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

_CACHE: dict = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_models(Base, *, id_type=None, prefix: str = "org_") -> SimpleNamespace:
    """Return Department, Role, Member and Audit mapped on ``Base`` (built once per Base and prefix)."""
    key = (id(Base), prefix)
    if key in _CACHE:
        return _CACHE[key]
    id_type = id_type or String(36)
    text_ids = isinstance(id_type, String)

    def pk():
        return mapped_column(id_type, primary_key=True, default=(lambda: str(uuid.uuid4())) if text_ids else None, autoincrement=not text_ids)

    class Department(Base):
        __tablename__ = f"{prefix}departments"
        __table_args__ = (UniqueConstraint("tenant_id", "name", name=f"uq_{prefix}dept_name"),)
        id: Mapped[object] = pk()
        tenant_id: Mapped[str] = mapped_column(String(64), index=True)
        name: Mapped[str] = mapped_column(String(80))
        parent_id: Mapped[object | None] = mapped_column(id_type, ForeignKey(f"{prefix}departments.id"), nullable=True)
        head_member_id: Mapped[object | None] = mapped_column(id_type, nullable=True)  # the head is a member of this company

    class Role(Base):
        __tablename__ = f"{prefix}roles"
        __table_args__ = (UniqueConstraint("tenant_id", "key", name=f"uq_{prefix}role_key"),)
        id: Mapped[object] = pk()
        tenant_id: Mapped[str] = mapped_column(String(64), index=True)
        key: Mapped[str] = mapped_column(String(40))
        name: Mapped[str] = mapped_column(String(120))
        description: Mapped[str] = mapped_column(String(300), default="")
        caps: Mapped[list] = mapped_column(JSON, default=list)
        is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    class Member(Base):
        __tablename__ = f"{prefix}members"
        __table_args__ = (UniqueConstraint("tenant_id", "user_id", name=f"uq_{prefix}member_user"),
                          UniqueConstraint("tenant_id", "email", name=f"uq_{prefix}member_email"),
                          Index(f"ix_{prefix}member_role", "tenant_id", "role_id"))
        id: Mapped[object] = pk()
        tenant_id: Mapped[str] = mapped_column(String(64), index=True)
        user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # the product's user id; empty until the person first signs in
        identity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # Aadi Identity user (sub)
        email: Mapped[str] = mapped_column(String(200))
        name: Mapped[str] = mapped_column(String(160), default="")
        title: Mapped[str] = mapped_column(String(120), default="")
        role_id: Mapped[object] = mapped_column(id_type, ForeignKey(f"{prefix}roles.id"))
        department_id: Mapped[object | None] = mapped_column(id_type, ForeignKey(f"{prefix}departments.id"), nullable=True)
        manager_id: Mapped[object | None] = mapped_column(id_type, ForeignKey(f"{prefix}members.id"), nullable=True)
        status: Mapped[str] = mapped_column(String(20), default="invited")  # invited | active | suspended
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    class Audit(Base):
        __tablename__ = f"{prefix}audit"
        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        tenant_id: Mapped[str] = mapped_column(String(64), index=True)
        actor: Mapped[str] = mapped_column(String(200), default="")  # who did it (email or user id)
        action: Mapped[str] = mapped_column(String(60))
        entity: Mapped[str] = mapped_column(String(30), default="")
        entity_id: Mapped[str] = mapped_column(String(64), default="")
        detail: Mapped[dict] = mapped_column(JSON, default=dict)
        at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    ns = SimpleNamespace(Department=Department, Role=Role, Member=Member, Audit=Audit, id_type=id_type, prefix=prefix, text_ids=text_ids)
    _CACHE[key] = ns
    return ns
