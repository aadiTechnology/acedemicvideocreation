"""People and roles of the signed-in company. Admin only."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models as m
from app.auth import ROLES, CurrentUser, admin_only
from app.db import get_db

router = APIRouter(prefix="/admin")


class RolesIn(BaseModel):
    roles: list[str]


@router.get("/users")
def list_users(db: Session = Depends(get_db), user: CurrentUser = Depends(admin_only)):
    people = db.scalars(select(m.AppUser).where(m.AppUser.tenant_id == user.tenant_id).order_by(m.AppUser.email)).all()
    roles = db.execute(select(m.UserRole.user_id, m.UserRole.role).where(m.UserRole.tenant_id == user.tenant_id)).all()
    by_user: dict[str, list[str]] = {}
    for uid, role in roles:
        by_user.setdefault(uid, []).append(role)
    return [{"user_id": p.user_id, "email": p.email, "name": p.name, "roles": sorted(by_user.get(p.user_id, []))} for p in people]


@router.put("/users/{user_id}/roles")
def set_roles(user_id: str, body: RolesIn, db: Session = Depends(get_db), user: CurrentUser = Depends(admin_only)):
    bad = [r for r in body.roles if r not in ROLES]
    if bad:
        raise HTTPException(422, f"Unknown roles: {', '.join(bad)}.")
    person = db.scalar(select(m.AppUser).where(m.AppUser.tenant_id == user.tenant_id, m.AppUser.user_id == user_id))
    if person is None:
        raise HTTPException(404, "That person has not signed in to this company yet.")
    if user_id == user.user_id and "admin" not in body.roles:
        raise HTTPException(409, "You cannot remove your own admin role.")
    db.execute(delete(m.UserRole).where(m.UserRole.tenant_id == user.tenant_id, m.UserRole.user_id == user_id))
    for role in dict.fromkeys(body.roles):
        db.add(m.UserRole(tenant_id=user.tenant_id, user_id=user_id, role=role))
    db.commit()
    return {"user_id": user_id, "roles": sorted(set(body.roles))}
