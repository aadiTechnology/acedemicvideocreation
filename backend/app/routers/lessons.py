"""Lessons and their language versions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app import schemas
from app.auth import CurrentUser, current_user, writer
from app.db import get_db
from app.routers.structure import _commit, owned

router = APIRouter(prefix="/lessons")


def _versions(db: Session, lesson_id: str) -> list[m.LessonVersion]:
    return list(db.scalars(select(m.LessonVersion).where(m.LessonVersion.lesson_id == lesson_id).order_by(m.LessonVersion.language)))


def _out(db: Session, lesson: m.Lesson) -> schemas.LessonOut:
    out = schemas.LessonOut.model_validate(lesson)
    out.versions = [schemas.VersionOut.model_validate(v) for v in _versions(db, lesson.id)]
    return out


@router.get("", response_model=list[schemas.LessonRow])
def list_lessons(
    class_id: str | None = None, subject_id: str | None = None, topic_id: str | None = None, language: str | None = None,
    db: Session = Depends(get_db), user: CurrentUser = Depends(current_user),
):
    q = (
        select(m.Lesson, m.Topic, m.Chapter, m.Subject, m.SchoolClass)
        .join(m.Topic, m.Lesson.topic_id == m.Topic.id)
        .join(m.Chapter, m.Topic.chapter_id == m.Chapter.id)
        .join(m.Subject, m.Chapter.subject_id == m.Subject.id)
        .join(m.SchoolClass, m.Subject.class_id == m.SchoolClass.id)
        .where(m.Lesson.tenant_id == user.tenant_id)
        .order_by(m.SchoolClass.sort_order, m.SchoolClass.name, m.Subject.name, m.Chapter.number, m.Topic.sort_order, m.Lesson.title)
    )
    if class_id:
        q = q.where(m.SchoolClass.id == class_id)
    if subject_id:
        q = q.where(m.Subject.id == subject_id)
    if topic_id:
        q = q.where(m.Lesson.topic_id == topic_id)
    if language:
        q = q.where(m.Lesson.id.in_(select(m.LessonVersion.lesson_id).where(m.LessonVersion.language == language)))
    rows = []
    for lesson, topic, chapter, subject, klass in db.execute(q):
        base = _out(db, lesson).model_dump()
        rows.append(schemas.LessonRow(**base, class_name=klass.name, subject_name=subject.name,
                                      chapter_number=chapter.number, chapter_title=chapter.title, topic_title=topic.title))
    return rows


@router.post("", status_code=201, response_model=schemas.LessonOut)
def create_lesson(body: schemas.LessonCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(writer)):
    owned(db, m.Topic, body.topic_id, user)
    data = body.model_dump(exclude={"languages"})
    lesson = m.Lesson(tenant_id=user.tenant_id, created_by=user.user_id, **data)
    db.add(lesson)
    db.flush()
    for language in dict.fromkeys(body.languages):
        db.add(m.LessonVersion(tenant_id=user.tenant_id, lesson_id=lesson.id, language=language))
    _commit(db)
    return _out(db, lesson)


@router.get("/{lesson_id}", response_model=schemas.LessonOut)
def get_lesson(lesson_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    return _out(db, owned(db, m.Lesson, lesson_id, user))


@router.patch("/{lesson_id}", response_model=schemas.LessonOut)
def update_lesson(lesson_id: str, body: schemas.LessonUpdate, db: Session = Depends(get_db), user: CurrentUser = Depends(writer)):
    lesson = owned(db, m.Lesson, lesson_id, user)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(lesson, key, value)
    _commit(db)
    return _out(db, lesson)


@router.delete("/{lesson_id}", status_code=204)
def delete_lesson(lesson_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(writer)):
    lesson = owned(db, m.Lesson, lesson_id, user)
    versions = _versions(db, lesson_id)
    if any(v.review_status != "draft" for v in versions):
        raise HTTPException(409, "A lesson with reviewed language versions cannot be deleted.")
    for v in versions:
        db.delete(v)
    db.flush()  # versions first: no ORM relationship orders these deletes
    db.delete(lesson)
    _commit(db)


@router.post("/{lesson_id}/versions", status_code=201, response_model=schemas.VersionOut)
def add_version(lesson_id: str, body: schemas.VersionCreate, db: Session = Depends(get_db), user: CurrentUser = Depends(writer)):
    owned(db, m.Lesson, lesson_id, user)
    version = m.LessonVersion(tenant_id=user.tenant_id, lesson_id=lesson_id, language=body.language)
    db.add(version)
    try:
        _commit(db)
    except HTTPException as exc:
        raise HTTPException(409, f"This lesson already has a {body.language} version.") from exc
    return version
