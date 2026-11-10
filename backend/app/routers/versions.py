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
from app.auth import CurrentUser, current_user, require_cap
from app.db import get_db
from app.package import CANONICAL_COLUMNS, WORDS_PER_MINUTE, ImportRejected, parse_upload
from app.routers.structure import owned

router = APIRouter(prefix="/lesson-versions")
writer = require_cap("lessons.manage")
reviewer = require_cap("review.decide")

LANGUAGE_NAMES = {"en-IN": "English", "hi-IN": "Hindi (Devanagari script)", "mr-IN": "Marathi (Devanagari script)"}

# action -> (allowed from statuses, new status, role that may do it)
TRANSITIONS = {
    "submit": ({"draft", "changes_required"}, "in_review", "lessons.manage"),
    "approve": ({"in_review"}, "approved", "review.decide"),
    "request_changes": ({"in_review"}, "changes_required", "review.decide"),
    "reject": ({"in_review"}, "rejected", "review.decide"),
    "reopen": ({"rejected", "approved"}, "draft", "lessons.manage"),
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
    if not user.can(role):
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
    technical = klass.course_type == "technical"
    intro = (f"You are an expert {subject.name} instructor creating a narrated technical course video for {klass.name} learners."
             if technical else f"You are an expert {subject.name} teacher creating a narrated teaching video for {klass.name} students.")
    path = (f"- Course: {klass.name}   Track: {subject.name}   Module {chapter.number}: {chapter.title}   Lesson topic: {topic.title}"
            if technical else f"- Class: {klass.name}   Subject: {subject.name}   Chapter {chapter.number}: {chapter.title}   Topic: {topic.title}")
    audience = lesson.target_audience or (f"{klass.name} learners; assume no prior knowledge unless the objectives say otherwise" if technical else klass.name + " students")
    rule = ("Technically correct: every code sample must be complete, runnable and idiomatic, and the output and variable values you show must be exactly what the code produces. "
            "Appropriate for the learners' level; no copyrighted course text copied word for word."
            if technical else f"Scientifically correct and appropriate for {klass.name}; no copyrighted textbook text copied word for word.")
    code_use = ("This is a technical course: explain code with the \"code\" layout on most slides that teach a concept, one small idea per slide. "
                if technical else "")
    return f"""{intro}

LESSON
{path}
- Lesson title: {lesson.title}
- Language of ALL narration, subtitles and slide text: {language}
- Target length: {lesson.expected_duration_minutes} minutes of narration, about {words} words in total
- Audience: {audience}
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
   Use 8 to 14 slides. Put EVERY text cell in double quotes, and close the quote at the end of each row (for example: 1,"Introduction","...","...","..."). Do not add other columns.
2. lesson_plan.json with this shape:
   {{"title": "...", "language": "{v.language}", "learning_objectives": ["..."], "source_references": ["textbook name and page"], "key_terms": ["3 to 8 important terms exactly as they appear in the narration"],
     "slides": [{{"slide": 1, "headline": "3 to 6 words, the slide title", "bullets": ["2 to 4 short key points, 3 to 8 words each"]}}],
     "quiz": [{{"question": "...", "options": ["...", "..."], "answer": "..."}}]}}
   "key_terms" are the important words of the lesson; they are highlighted in the captions when they appear. Use each term exactly as written in the narration.
   Give one "slides" entry for every slide. This short wording is what appears on the slide; the narration appears as captions.
   The video is animated: items appear one by one as the narrator reaches them. Add a "layout" to a slide when a picture explains it better than bullets:
   - "flow": {{"layout": "flow", "diagram": {{"steps": [{{"label": "Sunlight"}}, {{"label": "Water"}}, {{"label": "Glucose", "role": "output"}}]}}}}   (2 to 5 steps, arrows are drawn between them)
   - "equation": {{"layout": "equation", "diagram": {{"terms": ["Carbon dioxide", "+", "Water", "→", "Glucose", "+", "Oxygen"], "note": "in sunlight"}}}}
   - "cycle": {{"layout": "cycle", "diagram": {{"nodes": ["Evaporation", "Condensation", "Precipitation", "Collection"]}}}}   (3 to 6 nodes in a loop)
   - "compare": {{"layout": "compare", "diagram": {{"left": {{"title": "A", "points": ["..."]}}, "right": {{"title": "B", "points": ["..."]}}}}}}
   - "illustration": a drawn, animated science picture whose parts appear in stages as the narrator mentions them. Use it ONLY when the slide teaches exactly that topic:
       {{"layout": "illustration", "diagram": {{"template": "refraction", "params": {{"medium": "glass", "direction": "into_denser", "angle": 50}}}}}}
     templates and the order in which the narration of that slide must mention the parts (one sentence per part, in this order):
       refraction (6): the two media (air and glass/water) and the surface; the normal; the incident ray; the refracted ray; the angle of incidence; the angle of refraction.
         params: medium glass or water; direction into_denser (air to glass/water, bends towards the normal) or into_rarer (glass/water to air, bends away); angle 10 to 75.
       photosynthesis (6): sunlight; water from the roots; carbon dioxide; chlorophyll; oxygen released; glucose made.
       water_cycle (5): the sun heating the sea; evaporation; condensation (clouds); precipitation; collection (flowing back to the sea).
       leaf_section (6): upper epidermis; palisade cells; spongy cells; lower epidermis; stomata and guard cells; chloroplasts.
     The picture and its labels are drawn for you in the lesson language. Do not describe the drawing in the visual_instruction beyond naming the template.
   - "text_illustration": 1 to 5 bullets on the left and a built-in picture (same templates as "illustration") building up on the right as the bullets are spoken:
       {{"layout": "text_illustration", "bullets": ["..."], "diagram": {{"template": "refraction"}}}}
   - "timeline": events in time order, 3 to 6: {{"layout": "timeline", "diagram": {{"events": [{{"label": "1621", "sub": "Snell finds the law"}}, ...]}}}}
   - "labelled_diagram": a simple outline with labelled parts: {{"layout": "labelled_diagram", "diagram": {{"shape": "oval", "title": "Animal cell", "parts": [{{"label": "Nucleus", "x": 0.5, "y": 0.45}}, ...]}}}}   (shape oval, rect or circle; x and y are positions inside the shape, 0 to 1; 2 to 8 parts)
   - "experiment": a real-world activity: {{"layout": "experiment", "diagram": {{"aim": "...", "materials": ["..."], "procedure": ["1 to 4 short steps"], "observation": "...", "conclusion": "..."}}}}
   - "recap": the closing summary slide, 2 to 5 key points in "bullets" and an optional question: {{"layout": "recap", "bullets": ["..."], "diagram": {{"question": "..."}}}}
   Choose the layout that fits the content: a process or steps -> flow; two things compared -> compare; a repeating loop -> cycle; a formula or reaction -> equation; events over time -> timeline; naming the parts of something -> labelled_diagram; an activity or experiment -> experiment; a closing summary -> recap; otherwise bullets. Do not use the same layout for every slide.
   - "code": a code walk-through: a syntax-highlighted editor where the lines being explained are highlighted as the narrator reaches them, with an optional Output console and Variables table. Nothing is run, so write the real output and values yourself:
       {{"layout": "code", "diagram": {{"language": "python", "code": "x = 5\\nprint(x)", "steps": [{{"lines": [1], "vars": {{"x": "5"}}}}, {{"lines": [2], "output": "5"}}]}}}}
     code: up to 18 lines of up to 80 characters (a short excerpt, not a whole program). steps (up to 12) follow the order in which the narrator explains the code: "lines" are 1-based line numbers, "output" is what is printed at that step, "vars" are the variable values after that step (up to 6). Languages: python, javascript, java, c, cpp, sql, bash, html, json. Write one narrated sentence per step. {code_use}
   Without a layout, the bullets are shown one by one. Keep every label short (1 to 4 words) and in the lesson language. List the items in the order the narrator mentions them.

RULES
- {rule}
- Keep the spoken text and the subtitle text in the same language ({language}).
- Return the CSV and JSON as two separate code blocks so they can be saved as lesson.csv and lesson_plan.json.
"""
