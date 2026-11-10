"""Slide editor: change one slide's layout and wording, preview it with the video renderer, ask for a layout suggestion.

Saving rebuilds the stored package with the new lesson_plan.json and re-validates it with the same rules as an import,
so an edit can never make a package the engine would reject. Like an import, it cancels a review or approval."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models as m
from app.auth import CurrentUser, current_user, require_cap
from app.db import get_db
from app.engine_client import EngineRejected, EngineUnavailable
from app.package import CANONICAL_COLUMNS, ImportRejected, _diagram_problem, parse_upload
from app.routers.structure import owned
from app.routers.versions import _log, _storage
from app.routers.video import client_of

router = APIRouter(prefix="/lesson-versions")
layouts_router = APIRouter(prefix="/layouts")
writer = require_cap("lessons.manage")


class SlideIn(BaseModel):
    headline: str = Field(min_length=1, max_length=100)
    bullets: list[str] = []
    layout: str = "bullets"
    diagram: dict | None = None
    key_terms: list[str] = []
    # the slide's text in lesson.csv; left out (None) means unchanged
    module: str | None = Field(default=None, max_length=120)
    voice_text: str | None = Field(default=None, max_length=6000)
    subtitle_text: str | None = Field(default=None, max_length=6000)
    visual_instruction: str | None = Field(default=None, max_length=1000)


class PreviewIn(BaseModel):
    plan: SlideIn | None = None  # an unsaved draft; the saved slide when omitted
    at: float = 0.92
    profile: str = "480p24"
    subtitles: bool = False
    voice_text: str | None = None      # drafted narration and caption text, to preview before saving
    subtitle_text: str | None = None
    module: str | None = None


def _plan_entry(slide: SlideIn, number: int) -> dict:
    entry: dict = {"slide": number, "headline": slide.headline.strip(), "bullets": [b.strip() for b in slide.bullets if b.strip()]}
    if slide.layout != "bullets":
        entry["layout"] = slide.layout
    if slide.diagram:
        entry["diagram"] = slide.diagram
    if slide.key_terms:
        entry["key_terms"] = [t.strip() for t in slide.key_terms if t.strip()]
    return entry


def _row(v: m.LessonVersion, number: int) -> dict:
    row = next((s for s in v.slides or [] if s["slide"] == number), None)
    if row is None:
        raise HTTPException(404, f"Slide {number} was not found in this version.")
    return row


def _saved_entry(v: m.LessonVersion, number: int) -> dict:
    return next((s for s in (v.lesson_plan or {}).get("slides", []) if s.get("slide") == number), {"slide": number, "headline": _row(v, number)["module"], "bullets": []})


def _engine_call(fn):
    try:
        return fn()
    except EngineUnavailable as exc:
        raise HTTPException(503, "The video service is not reachable right now. Try again in a minute.") from exc
    except EngineRejected as exc:
        raise HTTPException(422, exc.message or "The video service could not draw this slide.") from exc


@router.get("/{version_id}/slides/{number}")
def get_slide(version_id: str, number: int, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    v = owned(db, m.LessonVersion, version_id, user)
    return {"row": _row(v, number), "plan": _saved_entry(v, number)}


@router.put("/{version_id}/slides/{number}")
def save_slide(version_id: str, number: int, body: SlideIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(writer)):
    v = owned(db, m.LessonVersion, version_id, user)
    _row(v, number)
    if not v.package_path or not Path(v.package_path).is_file():
        raise HTTPException(409, "This version has no stored package to edit. Import the lesson first.")
    entry = _plan_entry(body, number)
    problem = _diagram_problem(entry)
    if problem:
        raise HTTPException(422, {"message": problem, "issues": [{"code": "plan_diagram", "message": problem}]})
    plan = json.loads(json.dumps(v.lesson_plan or {}))
    slides = [s for s in plan.get("slides", []) if s.get("slide") != number] + [entry]
    plan["slides"] = sorted(slides, key=lambda s: s["slide"])
    members: dict[str, bytes] = {}
    with zipfile.ZipFile(v.package_path) as zf:
        for info in zf.infolist():
            if not info.is_dir():
                members[info.orig_filename] = zf.read(info)
    members["lesson_plan.json"] = json.dumps(plan, ensure_ascii=False, indent=2).encode("utf-8")
    texts = {k: getattr(body, k) for k in ("module", "voice_text", "subtitle_text", "visual_instruction") if getattr(body, k) is not None}
    text_changed = any(str(v.slides and _row(v, number).get(k, "")) != val.strip() for k, val in texts.items())
    if text_changed:  # rewrite lesson.csv with the edited cells; every field is quoted so the file is always valid CSV
        empty = [k for k, val in texts.items() if not val.strip()]
        if empty:
            raise HTTPException(422, {"message": f"These cannot be empty: {', '.join(empty)}.", "issues": [{"code": "empty_cell", "message": f"{k} cannot be empty."} for k in empty]})
        buf = io.StringIO()
        w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
        cols = list(CANONICAL_COLUMNS) + (["image"] if any(s.get("image") for s in v.slides) else [])
        w.writerow(cols)
        for s in v.slides:
            vals = {"Slide": s["slide"], "Module": s["module"], "voice_text": s["voice_text"], "subtitle_text": s["subtitle_text"],
                    "visual_instruction": s["visual_instruction"], "image": s.get("image", "")}
            if s["slide"] == number:
                vals.update({"Module": texts.get("module", s["module"]).strip(), "voice_text": texts.get("voice_text", s["voice_text"]).strip(),
                             "subtitle_text": texts.get("subtitle_text", s["subtitle_text"]).strip(), "visual_instruction": texts.get("visual_instruction", s["visual_instruction"]).strip()})
            w.writerow([vals[c] for c in cols])
        members["lesson.csv"] = buf.getvalue().encode("utf-8")
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    lesson = db.get(m.Lesson, v.lesson_id)
    defaults = {"title": lesson.title, "learning_objectives": lesson.learning_objectives, "source_references": lesson.source_references,
                "expected_duration_minutes": lesson.expected_duration_minutes}
    try:
        parsed = parse_upload([("package.zip", blob.getvalue())], v.language, defaults)
    except ImportRejected as exc:
        raise HTTPException(422, {"message": "The edited slide is not valid.", "issues": [i.dict() for i in exc.issues]}) from exc
    path = _storage(request) / "lesson-versions" / v.id / f"package-{parsed.sha256[:12]}.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(parsed.zip_bytes)
    if v.review_status in ("in_review", "approved", "changes_required", "rejected"):
        _log(db, v, user, "content_changed", "draft", f"Slide {number} was edited." + (" Its text was changed." if text_changed else ""))
    v.slides, v.lesson_plan, v.package_path, v.package_sha256 = parsed.slides, parsed.lesson_plan, str(path), hashlib.sha256(parsed.zip_bytes).hexdigest()
    v.imported_at, v.imported_by = m.utcnow(), user.user_id
    db.commit()
    return {"saved": True, "slide": number, "review_status": v.review_status, "package_sha256": v.package_sha256}


@router.post("/{version_id}/slides/{number}/preview")
def preview_slide(version_id: str, number: int, body: PreviewIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    v = owned(db, m.LessonVersion, version_id, user)
    row = _row(v, number)
    entry = _plan_entry(body.plan, number) if body.plan else _saved_entry(v, number)
    if body.plan:
        problem = _diagram_problem(entry)
        if problem:
            raise HTTPException(422, problem)
    lesson = db.get(m.Lesson, v.lesson_id)
    payload = {"language": v.language, "title": (v.lesson_plan or {}).get("title") or lesson.title, "total": len(v.slides or []),
               "slide": {"Slide": number, "Module": body.module or row["module"], "voice_text": body.voice_text or row["voice_text"],
                         "subtitle_text": body.subtitle_text or row["subtitle_text"]},
               "plan": entry, "key_terms": (v.lesson_plan or {}).get("key_terms", []), "at": body.at, "profile": body.profile, "subtitles": body.subtitles}
    png = _engine_call(lambda: client_of(request).preview(payload))
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/{version_id}/slides/{number}/recommend")
def recommend_layout(version_id: str, number: int, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    v = owned(db, m.LessonVersion, version_id, user)
    row = _row(v, number)
    lesson = db.get(m.Lesson, v.lesson_id)
    topic = db.get(m.Topic, lesson.topic_id)
    subject = db.get(m.Subject, db.get(m.Chapter, topic.chapter_id).subject_id)
    klass = db.get(m.SchoolClass, subject.class_id)
    body = {"subject": subject.name, "topic": f"{topic.title} {row['module']}", "objective": " ".join(lesson.learning_objectives),
            "class_name": klass.name, "course_type": klass.course_type, "narration": row["voice_text"], "limit": 3}
    return _engine_call(lambda: client_of(request).recommend(body))


@layouts_router.get("")
def list_layouts(request: Request, user: CurrentUser = Depends(current_user)):
    return _engine_call(lambda: client_of(request).layouts())
