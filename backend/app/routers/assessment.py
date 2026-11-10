"""Assessment questions for a lesson version (E11): author, approve, practise with immediate feedback, export a practice page.

Authors (lessons.manage) write and change questions; a reviewer (review.decide) approves them. Changing an approved question makes it a draft again.
Learners and other signed-in people see approved questions only and never the answers before they answer."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import assessment as A
from app import models as m
from app.auth import CurrentUser, current_user, require_cap
from app.db import get_db
from app.routers.structure import owned

router = APIRouter(prefix="/lesson-versions")
writer = require_cap("lessons.manage")
approver = require_cap("review.decide")


class QuestionIn(BaseModel):
    kind: str
    prompt: str
    explanation: str
    options: list[str] | None = None
    answer_index: int | None = None
    model_answer: str | None = None
    image_file: str | None = None
    slide: int | None = None


class AnswerIn(BaseModel):
    choice: int | None = None
    text: str | None = None


def _questions(db: Session, version_id: str) -> list[m.AssessmentQuestion]:
    return list(db.scalars(select(m.AssessmentQuestion).where(m.AssessmentQuestion.version_id == version_id).order_by(m.AssessmentQuestion.position, m.AssessmentQuestion.created_at)))


def _question(db: Session, v: m.LessonVersion, qid: str) -> m.AssessmentQuestion:
    q = db.get(m.AssessmentQuestion, qid)
    if q is None or q.version_id != v.id or q.tenant_id != v.tenant_id:
        raise HTTPException(404, "Question not found.")
    return q


def _can_author(user: CurrentUser) -> bool:
    return "lessons.manage" in user.caps or "review.decide" in user.caps


def _clean(v: m.LessonVersion, body: QuestionIn) -> dict:
    slides = {s["slide"] for s in v.slides or []}
    try:
        return A.clean(body.model_dump(), A.media_files(v.package_path), slides)
    except A.QuestionProblem as exc:
        raise HTTPException(422, exc.message) from None


def _renumber(db: Session, version_id: str) -> None:
    for i, q in enumerate(_questions(db, version_id), 1):
        q.position = i


@router.get("/{version_id}/assessment")
def list_questions(version_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    v = owned(db, m.LessonVersion, version_id, user)
    qs = _questions(db, v.id)
    author = _can_author(user)
    shown = qs if author else [q for q in qs if q.status == "approved"]
    return {"questions": [A.out(q, include_answer=author) for q in shown], "summary": A.summary(qs), "can_edit": "lessons.manage" in user.caps, "can_approve": "review.decide" in user.caps,
            "pictures": sorted(A.media_files(v.package_path))}


@router.post("/{version_id}/assessment", status_code=201)
def add_question(version_id: str, body: QuestionIn, db: Session = Depends(get_db), user: CurrentUser = Depends(writer)):
    v = owned(db, m.LessonVersion, version_id, user)
    if len(_questions(db, v.id)) >= A.MAX_QUESTIONS:
        raise HTTPException(409, f"A lesson version holds at most {A.MAX_QUESTIONS} questions. Remove one first.")
    q = m.AssessmentQuestion(tenant_id=v.tenant_id, version_id=v.id, created_by=user.user_id, position=len(_questions(db, v.id)) + 1, **_clean(v, body))
    db.add(q)
    db.commit()
    return A.out(q)


@router.put("/{version_id}/assessment/{qid}")
def change_question(version_id: str, qid: str, body: QuestionIn, db: Session = Depends(get_db), user: CurrentUser = Depends(writer)):
    v = owned(db, m.LessonVersion, version_id, user)
    q = _question(db, v, qid)
    for k, val in _clean(v, body).items():
        setattr(q, k, val)
    q.status, q.approved_by, q.approved_at = "draft", None, None  # a changed question must be approved again
    db.commit()
    return A.out(q)


@router.delete("/{version_id}/assessment/{qid}", status_code=204)
def remove_question(version_id: str, qid: str, db: Session = Depends(get_db), user: CurrentUser = Depends(writer)):
    v = owned(db, m.LessonVersion, version_id, user)
    db.delete(_question(db, v, qid))
    db.flush()
    _renumber(db, v.id)
    db.commit()


@router.post("/{version_id}/assessment/{qid}/approve")
def approve_question(version_id: str, qid: str, db: Session = Depends(get_db), user: CurrentUser = Depends(approver)):
    v = owned(db, m.LessonVersion, version_id, user)
    q = _question(db, v, qid)
    q.status, q.approved_by, q.approved_at = "approved", user.user_id, m.utcnow()
    db.commit()
    return A.out(q)


@router.post("/{version_id}/assessment/{qid}/unapprove")
def unapprove_question(version_id: str, qid: str, db: Session = Depends(get_db), user: CurrentUser = Depends(approver)):
    v = owned(db, m.LessonVersion, version_id, user)
    q = _question(db, v, qid)
    q.status, q.approved_by, q.approved_at = "draft", None, None
    db.commit()
    return A.out(q)


@router.post("/{version_id}/assessment/from-plan")
def questions_from_plan(version_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(writer)):
    """Turn the ``quiz`` ChatGPT wrote in lesson_plan.json into draft questions (only while there is room; existing questions are kept)."""
    v = owned(db, m.LessonVersion, version_id, user)
    have = len(_questions(db, v.id))
    made, skipped = [], []
    for item in A.from_plan_quiz((v.lesson_plan or {}).get("quiz", [])):
        if "skipped" in item:
            skipped.append(item["skipped"])
            continue
        if have + len(made) >= A.MAX_QUESTIONS:
            skipped.append("Not added: a version holds at most 5 questions.")
            continue
        try:
            fields = A.clean(item["draft"], A.media_files(v.package_path), {s["slide"] for s in v.slides or []})
        except A.QuestionProblem as exc:
            skipped.append(f"{item['draft']['prompt'][:50]}: {exc.message}")
            continue
        q = m.AssessmentQuestion(tenant_id=v.tenant_id, version_id=v.id, created_by=user.user_id, position=have + len(made) + 1, **fields)
        db.add(q)
        made.append(q)
    db.commit()
    return {"created": [A.out(q) for q in made], "skipped": skipped}


@router.post("/{version_id}/assessment/{qid}/answer")
def answer_question(version_id: str, qid: str, body: AnswerIn, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    """Practice: mark an answer and give the explanation at once. Nothing is stored. Learners can only practise approved questions."""
    v = owned(db, m.LessonVersion, version_id, user)
    q = _question(db, v, qid)
    if q.status != "approved" and not _can_author(user):
        raise HTTPException(404, "Question not found.")
    try:
        return A.check(q, body.choice, body.text)
    except A.QuestionProblem as exc:
        raise HTTPException(422, exc.message) from None


@router.get("/{version_id}/assessment/picture/{name}")
def question_picture(version_id: str, name: str, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    from fastapi.responses import Response
    v = owned(db, m.LessonVersion, version_id, user)
    pic = A.picture(v.package_path, f"media/{name}")
    if pic is None or not any(q.image_file == f"media/{name}" and (q.status == "approved" or _can_author(user)) for q in _questions(db, v.id)):
        raise HTTPException(404, "Picture not found.")
    return Response(pic[0], media_type=pic[1], headers={"Cache-Control": "private, max-age=300"})


@router.get("/{version_id}/assessment/export.html", response_class=HTMLResponse)
def export_questions(version_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    v = owned(db, m.LessonVersion, version_id, user)
    approved = [q for q in _questions(db, v.id) if q.status == "approved"]
    if not approved:
        raise HTTPException(409, "There are no approved questions to export yet.")
    lesson = db.get(m.Lesson, v.lesson_id)
    return HTMLResponse(A.export_html(lesson.title, v.language, approved, v.package_path),
                        headers={"Content-Disposition": f'attachment; filename="practice-{v.language}.html"'})
