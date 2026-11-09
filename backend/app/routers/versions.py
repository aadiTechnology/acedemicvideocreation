"""Language versions: package import, academic review, and the ChatGPT prompt specification."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile  # what request.form() returns (not fastapi's subclass)

from app import models as m
from app.auth import CurrentUser, current_user, require_roles
from app.db import get_db
from app.package import CANONICAL_COLUMNS, WORDS_PER_MINUTE, ImportRejected, parse_upload
from app.routers.structure import owned

router = APIRouter(prefix="/lesson-versions")
writer = require_roles("content_operator")
reviewer = require_roles("reviewer")

LANGUAGE_NAMES = {"en-IN": "English", "hi-IN": "Hindi (Devanagari script)", "mr-IN": "Marathi (Devanagari script)"}

# action -> (allowed from statuses, new status, role that may do it)
TRANSITIONS = {
    "submit": ({"draft", "changes_required"}, "in_review", "content_operator"),
    "approve": ({"in_review"}, "approved", "reviewer"),
    "request_changes": ({"in_review"}, "changes_required", "reviewer"),
    "reject": ({"in_review"}, "rejected", "reviewer"),
    "reopen": ({"rejected", "approved"}, "draft", "content_operator"),
}


class ReviewIn(BaseModel):
    action: str
    note: str = ""


def _detail(db: Session, v: m.LessonVersion) -> dict:
    lesson = db.get(m.Lesson, v.lesson_id)
    events = db.scalars(select(m.ReviewEvent).where(m.ReviewEvent.version_id == v.id).order_by(m.ReviewEvent.created_at)).all()
    plan = v.lesson_plan or {}
    return {
        "id": v.id, "lesson_id": v.lesson_id, "lesson_title": lesson.title, "language": v.language, "review_status": v.review_status,
        "review_note": v.review_note, "reviewed_by": v.reviewed_by, "reviewed_at": v.reviewed_at,
        "publication_status": v.publication_status, "imported_at": v.imported_at, "imported_by": v.imported_by,
        "package_sha256": v.package_sha256, "has_content": bool(v.slides), "slides": v.slides or [],
        "learning_objectives": plan.get("learning_objectives", lesson.learning_objectives),
        "quiz": plan.get("quiz", []), "source_references": plan.get("source_references", lesson.source_references),
        "word_count": sum(len(s["voice_text"].split()) for s in v.slides or []),
        "events": [{"action": e.action, "from": e.from_status, "to": e.to_status, "note": e.note, "actor_id": e.actor_id, "at": e.created_at} for e in events],
    }


def _storage(request: Request) -> Path:
    root = Path(request.app.state.settings.storage_dir or "./storage").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _log(db: Session, v: m.LessonVersion, user: CurrentUser, action: str, to: str, note: str = "") -> None:
    db.add(m.ReviewEvent(tenant_id=v.tenant_id, version_id=v.id, action=action, from_status=v.review_status, to_status=to, note=note, actor_id=user.user_id))
    v.review_status = to


@router.get("")
def list_versions(status: str | None = None, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    q = select(m.LessonVersion, m.Lesson).join(m.Lesson, m.LessonVersion.lesson_id == m.Lesson.id).where(m.LessonVersion.tenant_id == user.tenant_id)
    if status:
        q = q.where(m.LessonVersion.review_status == status)
    return [{"id": v.id, "lesson_id": v.lesson_id, "lesson_title": lesson.title, "language": v.language, "review_status": v.review_status,
             "has_content": bool(v.slides)} for v, lesson in db.execute(q.order_by(m.Lesson.title, m.LessonVersion.language))]


@router.get("/{version_id}")
def get_version(version_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    return _detail(db, owned(db, m.LessonVersion, version_id, user))


@router.post("/{version_id}/import")
async def import_package(version_id: str, request: Request, dry_run: bool = False, db: Session = Depends(get_db), user: CurrentUser = Depends(writer)):
    v = owned(db, m.LessonVersion, version_id, user)
    form = await request.form()
    uploads = [(f.filename or "upload", await f.read()) for f in form.getlist("files") if isinstance(f, UploadFile)]
    lesson = db.get(m.Lesson, v.lesson_id)
    defaults = {"title": lesson.title, "learning_objectives": lesson.learning_objectives, "source_references": lesson.source_references,
                "expected_duration_minutes": lesson.expected_duration_minutes}
    try:
        parsed = parse_upload(uploads, v.language, defaults)
    except ImportRejected as exc:
        return JSONResponse({"detail": {"message": "The package has errors. Nothing was imported.", "issues": [i.dict() for i in exc.issues]}}, status_code=422)
    summary = {"ok": True, "dry_run": dry_run, "slides": len(parsed.slides), "word_count": parsed.word_count,
               "estimated_minutes": parsed.estimated_minutes, "package_sha256": parsed.sha256, "warnings": [w.dict() for w in parsed.warnings]}
    if dry_run:
        return summary
    path = _storage(request) / "lesson-versions" / v.id / f"package-{parsed.sha256[:12]}.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(parsed.zip_bytes)
    reset = v.review_status in ("in_review", "approved", "changes_required", "rejected")
    if reset:  # new content invalidates any review, including an approval
        _log(db, v, user, "content_changed", "draft", "New content was imported.")
    v.slides, v.lesson_plan = parsed.slides, parsed.lesson_plan
    v.package_path, v.package_sha256 = str(path), parsed.sha256
    v.package_filename = uploads[0][0] if uploads else None
    v.imported_at, v.imported_by = m.utcnow(), user.user_id
    db.commit()
    return {**summary, "review_status": v.review_status}


@router.post("/{version_id}/review")
def review(version_id: str, body: ReviewIn, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    v = owned(db, m.LessonVersion, version_id, user)
    rule = TRANSITIONS.get(body.action)
    if rule is None:
        raise HTTPException(422, f"Unknown action {body.action!r}. Use one of: {', '.join(TRANSITIONS)}.")
    allowed_from, to, role = rule
    if not user.has(role):
        raise HTTPException(403, "Your role does not allow this action.")
    if v.review_status not in allowed_from:
        raise HTTPException(409, f"A version that is {v.review_status.replace('_', ' ')} cannot be moved this way.")
    if body.action == "submit" and not v.slides:
        raise HTTPException(409, "Import the lesson content before sending it for review.")
    if body.action in ("request_changes", "reject") and not body.note.strip():
        raise HTTPException(422, "Please add a note explaining what needs to change.")
    _log(db, v, user, body.action, to, body.note.strip())
    if body.action in ("approve", "request_changes", "reject"):
        v.review_note, v.reviewed_by, v.reviewed_at = body.note.strip(), user.user_id, m.utcnow()
    db.commit()
    return _detail(db, v)


@router.get("/{version_id}/package")
def download_package(version_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    from fastapi.responses import FileResponse
    v = owned(db, m.LessonVersion, version_id, user)
    if not v.package_path or not Path(v.package_path).is_file():
        raise HTTPException(404, "No package has been imported for this version.")
    return FileResponse(v.package_path, media_type="application/zip", filename=f"{v.id}.zip")


@router.get("/{version_id}/prompt-spec", response_class=PlainTextResponse)
def prompt_spec(version_id: str, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    """Text to paste into ChatGPT (manual use, no automation) that asks for exactly the package this app imports."""
    v = owned(db, m.LessonVersion, version_id, user)
    lesson = db.get(m.Lesson, v.lesson_id)
    topic = db.get(m.Topic, lesson.topic_id)
    chapter = db.get(m.Chapter, topic.chapter_id)
    subject = db.get(m.Subject, chapter.subject_id)
    klass = db.get(m.SchoolClass, subject.class_id)
    language = LANGUAGE_NAMES.get(v.language, v.language)
    words = lesson.expected_duration_minutes * WORDS_PER_MINUTE
    objectives = "\n".join(f"- {o}" for o in lesson.learning_objectives) or "- (none given: derive 3 to 5 from the topic)"
    return f"""You are an expert {subject.name} teacher creating a narrated teaching video for {klass.name} students.

LESSON
- Class: {klass.name}   Subject: {subject.name}   Chapter {chapter.number}: {chapter.title}   Topic: {topic.title}
- Lesson title: {lesson.title}
- Language of ALL narration, subtitles and slide text: {language}
- Target length: {lesson.expected_duration_minutes} minutes of narration, about {words} words in total
- Audience: {lesson.target_audience or klass.name + " students"}
- Learning objectives:
{objectives}

OUTPUT: produce these files and nothing else.
1. lesson.csv, UTF-8 CSV with EXACTLY this header, in this order:
   {",".join(CANONICAL_COLUMNS)}
   - Slide: 1, 2, 3 ... (whole numbers, no gaps, no repeats)
   - Module: a short section name for the slide (for example "Introduction", "How it works", "Summary")
   - voice_text: what the narrator says for this slide; natural spoken sentences, 40 to 90 words; no stage directions
   - subtitle_text: the caption text shown while the narrator speaks. Use the SAME words as voice_text (you may shorten a little).
     Captions are timed from it, so a short summary here makes the captions run out long before the narration ends.
   - visual_instruction: what the slide should show (diagram, labelled picture, animation idea); do not name image files
   Use 8 to 14 slides. Quote any cell that contains a comma. Do not add other columns.
2. lesson_plan.json with this shape:
   {{"title": "...", "language": "{v.language}", "learning_objectives": ["..."], "source_references": ["textbook name and page"],
     "slides": [{{"slide": 1, "headline": "3 to 6 words, the slide title", "bullets": ["2 to 4 short key points, 3 to 8 words each"]}}],
     "quiz": [{{"question": "...", "options": ["...", "..."], "answer": "..."}}]}}
   Give one "slides" entry for every slide. This short wording is what appears on the slide; the narration appears as captions.
   The video is animated: items appear one by one as the narrator reaches them. Add a "layout" to a slide when a picture explains it better than bullets:
   - "flow": {{"layout": "flow", "diagram": {{"steps": [{{"label": "Sunlight"}}, {{"label": "Water"}}, {{"label": "Glucose", "role": "output"}}]}}}}   (2 to 5 steps, arrows are drawn between them)
   - "equation": {{"layout": "equation", "diagram": {{"terms": ["Carbon dioxide", "+", "Water", "→", "Glucose", "+", "Oxygen"], "note": "in sunlight"}}}}
   - "cycle": {{"layout": "cycle", "diagram": {{"nodes": ["Evaporation", "Condensation", "Precipitation", "Collection"]}}}}   (3 to 6 nodes in a loop)
   - "compare": {{"layout": "compare", "diagram": {{"left": {{"title": "A", "points": ["..."]}}, "right": {{"title": "B", "points": ["..."]}}}}}}
   Without a layout, the bullets are shown one by one. Keep every label short (1 to 4 words) and in the lesson language. List the items in the order the narrator mentions them.

RULES
- Scientifically correct and appropriate for {klass.name}; no copyrighted textbook text copied word for word.
- Keep the spoken text and the subtitle text in the same language ({language}).
- Return the CSV and JSON as two separate code blocks so they can be saved as lesson.csv and lesson_plan.json.
"""
