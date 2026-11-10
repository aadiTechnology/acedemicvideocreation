"""Class, subject, chapter and topic CRUD. Every query is scoped to the signed-in user's tenant."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import CurrentUser, current_user, require_cap

writer = require_cap("structure.manage")
from app.db import get_db


def owned(db: Session, model, obj_id: str, user: CurrentUser):
    """Fetch a row of this tenant or raise 404 (a row of another tenant looks the same as a missing one)."""
    obj = db.get(model, obj_id)
    if obj is None or obj.tenant_id != user.tenant_id:
        raise HTTPException(404, f"{model.__tablename__[:-1]} not found.")
    return obj


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        text = str(exc.orig).lower()
        if "foreign key" in text and "delete" in text:
            raise HTTPException(409, "This item still has items below it. Remove those first.") from exc
        raise HTTPException(409, "An item with the same name or number already exists here.") from exc


def build(prefix: str, model, in_schema, out_schema, parent: tuple[str, type] | None, order):
    router = APIRouter(prefix=prefix)

    @router.get("", response_model=list[out_schema])
    def list_items(parent_id: str | None = None, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
        q = select(model).where(model.tenant_id == user.tenant_id)
        if parent and parent_id:
            q = q.where(getattr(model, parent[0]) == parent_id)
        return db.scalars(q.order_by(*order)).all()

    @router.post("", status_code=201, response_model=out_schema)
    def create(body: in_schema, db: Session = Depends(get_db), user: CurrentUser = Depends(writer)):
        if parent:
            owned(db, parent[1], getattr(body, parent[0]), user)
        obj = model(tenant_id=user.tenant_id, **body.model_dump())
        db.add(obj)
        _commit(db)
        return obj

    @router.get("/{item_id}", response_model=out_schema)
    def read(item_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
        return owned(db, model, item_id, user)

    @router.put("/{item_id}", response_model=out_schema)
    def update(item_id: str, body: in_schema, db: Session = Depends(get_db), user: CurrentUser = Depends(writer)):
        obj = owned(db, model, item_id, user)
        if parent:
            owned(db, parent[1], getattr(body, parent[0]), user)
        for key, value in body.model_dump().items():
            setattr(obj, key, value)
        _commit(db)
        return obj

    @router.delete("/{item_id}", status_code=204)
    def delete(item_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(writer)):
        db.delete(owned(db, model, item_id, user))
        _commit(db)

    return router


M = models
routers = [
    build("/classes", M.SchoolClass, schemas.ClassIn, schemas.ClassOut, None, (M.SchoolClass.sort_order, M.SchoolClass.name)),
    build("/subjects", M.Subject, schemas.SubjectIn, schemas.SubjectOut, ("class_id", M.SchoolClass), (M.Subject.name,)),
    build("/chapters", M.Chapter, schemas.ChapterIn, schemas.ChapterOut, ("subject_id", M.Subject), (M.Chapter.number,)),
    build("/topics", M.Topic, schemas.TopicIn, schemas.TopicOut, ("chapter_id", M.Chapter), (M.Topic.sort_order, M.Topic.title)),
]
