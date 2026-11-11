"""Video production for approved language versions, through the Video Engine API."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app import models as m
from app.auth import CurrentUser, current_user, require_cap
from app.db import get_db
from app.storage import PREFIX, StorageError, is_remote, key_of
from app.engine_client import APPLICATION_ID, CONTRACT_VERSION, EngineClient, EngineRejected, EngineUnavailable
from app.routers.structure import owned

logger = logging.getLogger("academic.video")
router = APIRouter()
operator = require_cap("video.generate")

PROFILES = ("1080p24", "720p24", "480p24")
SPEEDS = {"slow": "-15%", "normal": "0%", "fast": "+15%"}  # narration speed presets -> Azure prosody rate
MAX_AUDIO_BYTES = 200 * 1024 * 1024
FRIENDLY = {
    "engine_unavailable": "The video service is not reachable right now. Try again in a minute.",
    "invalid_package": "The video service did not accept the lesson package.",
    "unsupported_environment": "The video service cannot render this language yet.",
    "tts_unavailable": "The voice service is not available. Try again, or choose another voice option.",
    "storage_unavailable": "The file storage is not reachable right now. Try again in a minute.",
    "render_failed": "The video could not be rendered. Try again.",
    "worker_interrupted": "The video service restarted while rendering. Try again.",
    "asset_corrupt": "The finished video did not pass the integrity check. Try again.",
}


THEMES = ("dark", "high_contrast")


class RemakeIn(BaseModel):
    profile: str = "720p24"
    theme: str = "dark"
    subtitles: bool = True


class GenerateIn(BaseModel):
    provider: str = "azure"
    mode: str | None = None
    voice: str | None = None
    profile: str = "480p24"
    subtitles: bool = True
    style: str = "animated"  # animated slides (layouts, diagrams, highlighting) or plain
    speed: str = "normal"  # narration speed: slow, normal or fast
    rerender: bool = False


def client_of(request: Request) -> EngineClient:
    return request.app.state.engine


def cid_of(request: Request) -> str:
    return getattr(request.state, "correlation_id", "")


def _storage(request: Request) -> Path:
    root = Path(request.app.state.settings.storage_dir or "./storage").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _job_out(job: m.VideoJob) -> dict:
    return {"id": job.id, "version_id": job.version_id, "state": job.state, "stage": job.stage, "percent": job.percent,
            "error_code": job.error_code, "error_message": job.error_message, "retryable": job.retryable,
            "settings": job.settings, "created_at": job.created_at, "updated_at": job.updated_at, "finished_at": job.finished_at,
            "awaiting_audio": job.state == "awaiting_audio"}


def _summary(db: Session, version: m.LessonVersion) -> dict:
    jobs = db.scalars(select(m.VideoJob).where(m.VideoJob.version_id == version.id).order_by(m.VideoJob.created_at.desc()).limit(10)).all()
    latest = jobs[0] if jobs else None
    assets = []
    if latest and latest.state == "succeeded":
        assets = [{"id": a.id, "kind": a.kind, "filename": a.filename, "size_bytes": a.size_bytes, "sha256": a.sha256, **(a.meta or {})}
                  for a in db.scalars(select(m.VideoAsset).where(m.VideoAsset.job_id == latest.id).order_by(m.VideoAsset.kind))]
    active = any(j.state in m.ACTIVE_JOB_STATES for j in jobs)
    reason = None
    if version.review_status != "approved":
        reason = "Only approved content can be sent to video production."
    elif not version.package_path:
        reason = "Import the lesson content first."
    elif active:
        reason = "A video is already being made for this version."
    return {"job": _job_out(latest) if latest else None, "assets": assets, "history": [_job_out(j) for j in jobs[1:]],
            "can_generate": reason is None, "blocked_reason": reason}


def _manifest(version: m.LessonVersion, user: CurrentUser, key: str, s: dict, target_minutes: float | None = None) -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "caller": {"application_id": APPLICATION_ID, "tenant_ref": user.tenant_id, "external_ref": version.id},
        "idempotency_key": key, "language": version.language,
        "tts": {"provider": s["provider"], "mode": s["mode"], "rate": SPEEDS.get(s.get("speed", "normal"), "0%"), **({"voice": s["voice"]} if s.get("voice") else {})},
        "render": {"profile": s["profile"], "style": s.get("style", "plain"), "subtitles": {"enabled": s["subtitles"]}, **({"theme": s["theme"]} if s.get("theme", "dark") != "dark" else {})},
        **({"quality": {"target_minutes": float(target_minutes)}} if target_minutes else {}),  # the quality check compares the video with the planned length
    }


def _fail(job: m.VideoJob, code: str, message: str | None = None, retryable: bool = False) -> None:
    job.state, job.error_code, job.retryable = "failed", code, retryable
    job.error_message = message or FRIENDLY.get(code, "The video could not be made.")
    job.finished_at = m.utcnow()


def _bundle_bytes(db: Session, request: Request, source_job_id: str) -> bytes:
    """The lesson bundle of a finished video, from Academic's storage (local folder or object storage)."""
    asset = db.scalar(select(m.VideoAsset).where(m.VideoAsset.job_id == source_job_id, m.VideoAsset.kind == "lesson_bundle"))
    if asset is None:
        raise OSError("The lesson bundle of that video is not available.")
    if is_remote(asset.local_path):
        store = request.app.state.store
        raw = store.read_bytes(key_of(asset.local_path)) if store is not None else None
        if raw is None:
            raise OSError("The lesson bundle of that video is not available.")
        return raw
    return Path(asset.local_path).read_bytes()


def _send(db: Session, request: Request, job: m.VideoJob, version: m.LessonVersion, user: CurrentUser) -> None:
    """Submit to the engine. The engine de-duplicates on the idempotency key, so repeating this is safe."""
    try:
        package = _bundle_bytes(db, request, job.settings["from_job"]) if job.settings.get("from_job") else Path(version.package_path).read_bytes()
        target = (db.get(m.Lesson, version.lesson_id).expected_duration_minutes if version.lesson_id else None)
        resp = client_of(request).submit(_manifest(version, user, job.idempotency_key, job.settings, target), package, job.idempotency_key, cid_of(request))
        job.engine_job_id, job.state = resp["job_id"], resp["state"]
        job.error_code = job.error_message = None
        job.retryable, job.finished_at = False, None
    except EngineUnavailable:
        _fail(job, "engine_unavailable", retryable=True)
    except EngineRejected as exc:
        _fail(job, exc.code, f"{FRIENDLY.get(exc.code, exc.message)}" + (f" ({'; '.join(map(str, exc.details[:3]))})" if exc.details else ""), retryable=False)
    except OSError:
        _fail(job, "package_missing", "The stored lesson package could not be read.", retryable=False)
    db.commit()


def _collect_assets(db: Session, request: Request, job: m.VideoJob) -> None:
    """Copy the outputs into Academic storage and verify size and SHA-256 before the job counts as done."""
    client = client_of(request)
    folder = _storage(request) / "videos" / job.version_id / job.id
    folder.mkdir(parents=True, exist_ok=True)
    listed = client.assets(job.engine_job_id, cid_of(request))
    if not any(a["kind"] == "video" for a in listed):
        _fail(job, "render_failed", "The video service finished without a video file.", retryable=False)
        return
    db.execute(delete(m.VideoAsset).where(m.VideoAsset.job_id == job.id))  # a retry collects from scratch
    for a in listed:
        target = folder / f"{a['kind']}-{a['filename']}"
        client.download_asset(job.engine_job_id, a["asset_id"], target, cid_of(request))
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != a["sha256"] or target.stat().st_size != a["size_bytes"]:
            target.unlink(missing_ok=True)
            _fail(job, "asset_corrupt", retryable=True)
            return
        stored = str(target)
        store = request.app.state.store
        if store is not None:  # the verified file moves to object storage; only the key is kept here
            key = f"videos/{job.version_id}/{job.id}/{a['kind']}-{a['filename']}"
            try:
                store.put_file(key, target, a["content_type"])
            except StorageError:
                _fail(job, "storage_unavailable", retryable=True)
                return
            target.unlink(missing_ok=True)
            stored = PREFIX + key
        meta = {k: a[k] for k in ("duration_seconds", "width", "height", "fps") if a.get(k) is not None}
        db.add(m.VideoAsset(tenant_id=job.tenant_id, job_id=job.id, version_id=job.version_id, engine_asset_id=a["asset_id"], kind=a["kind"],
                            filename=a["filename"], content_type=a["content_type"], size_bytes=a["size_bytes"], sha256=digest,
                            local_path=stored, meta=meta))
    job.state, job.percent, job.stage = "succeeded", 100, "done"
    job.error_code = job.error_message = None
    job.finished_at = m.utcnow()


def _refresh(db: Session, request: Request, job: m.VideoJob) -> None:
    """Pull the engine's state for an active job into our record. Engine outages leave the job as it was."""
    if job.state not in m.ACTIVE_JOB_STATES or not job.engine_job_id:
        return
    try:
        st = client_of(request).status(job.engine_job_id, cid_of(request))
        job.stage, job.percent = st["progress"].get("stage"), st["progress"].get("percent", 0)
        if st["state"] == "succeeded":
            db.execute(m.VideoAsset.__table__.delete().where(m.VideoAsset.job_id == job.id))
            _collect_assets(db, request, job)
        elif st["state"] == "failed":
            err = st.get("error") or {}
            _fail(job, err.get("code", "render_failed"), FRIENDLY.get(err.get("code", ""), err.get("message")), bool(st.get("retryable")))
        elif st["state"] == "cancelled":
            job.state, job.finished_at = "cancelled", m.utcnow()
        else:
            job.state = st["state"]
    except EngineUnavailable:
        logger.warning("engine unreachable while refreshing job %s", job.id)
    except EngineRejected as exc:
        if exc.status == 404:
            _fail(job, "engine_job_missing", "The video service no longer knows this job.", retryable=False)
    db.commit()


def _get_job(db: Session, job_id: str, user: CurrentUser) -> m.VideoJob:
    return owned(db, m.VideoJob, job_id, user)


# ---- endpoints ------------------------------------------------------------------------------------------
@router.get("/video/capabilities")
def capabilities(request: Request, user: CurrentUser = Depends(current_user)):
    try:
        caps = client_of(request).capabilities(cid_of(request))
    except (EngineUnavailable, EngineRejected):
        raise HTTPException(503, FRIENDLY["engine_unavailable"]) from None
    return {"languages": caps["languages"], "profiles": caps["output_profiles"],
            "providers": [{"name": p["name"], "modes": p["modes"], "configured": p["configured"], "voices": p["voices"]} for p in caps["providers"]],
            "features": caps["features"]}


@router.get("/lesson-versions/{version_id}/video")
def get_video(version_id: str, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    version = owned(db, m.LessonVersion, version_id, user)
    latest = db.scalar(select(m.VideoJob).where(m.VideoJob.version_id == version_id).order_by(m.VideoJob.created_at.desc()).limit(1))
    if latest and latest.state in m.ACTIVE_JOB_STATES:
        _refresh(db, request, latest)
    return _summary(db, version)


@router.post("/lesson-versions/{version_id}/video", status_code=202)
def generate(version_id: str, body: GenerateIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(operator)):
    version = owned(db, m.LessonVersion, version_id, user)
    if version.review_status != "approved":
        raise HTTPException(409, "Only approved content can be sent to video production.")
    if not version.package_path or not version.package_sha256:
        raise HTTPException(409, "Import the lesson content first.")
    if body.profile not in PROFILES:
        raise HTTPException(422, f"Unknown output profile. Use one of: {', '.join(PROFILES)}.")
    if body.style not in ("animated", "plain"):
        raise HTTPException(422, "Unknown slide style. Use animated or plain.")
    if body.speed not in SPEEDS:
        raise HTTPException(422, "Unknown narration speed. Use slow, normal or fast.")
    if body.provider not in ("colab", "azure"):
        raise HTTPException(422, "Unknown voice option. Use colab or azure.")
    mode = body.mode or ("manual" if body.provider == "colab" else "api")
    if (body.provider, mode) not in (("colab", "manual"), ("colab", "tunnel"), ("azure", "api")):
        raise HTTPException(422, "That voice option and mode do not go together.")
    settings = {"provider": body.provider, "mode": mode, "voice": body.voice, "profile": body.profile, "subtitles": body.subtitles, "style": body.style, **({"speed": body.speed} if body.speed != "normal" else {})}
    base = hashlib.sha256(json.dumps([version.id, version.package_sha256, settings], sort_keys=True).encode()).hexdigest()
    runs = db.scalar(select(func.count()).select_from(m.VideoJob).where(m.VideoJob.version_id == version.id, m.VideoJob.idempotency_key.like(f"lv-{base[:24]}-%"))) or 0
    key = f"lv-{base[:24]}-{runs if body.rerender else max(runs - 1, 0)}"
    existing = db.scalar(select(m.VideoJob).where(m.VideoJob.tenant_id == user.tenant_id, m.VideoJob.idempotency_key == key))
    if existing is not None:  # a repeated click or network retry: same request, same job
        if existing.state == "submitting" and not existing.engine_job_id:
            _send(db, request, existing, version, user)
        return {**_summary(db, version), "idempotent_replay": True}
    if any(j.state in m.ACTIVE_JOB_STATES for j in db.scalars(select(m.VideoJob).where(m.VideoJob.version_id == version.id))):
        raise HTTPException(409, "A video is already being made for this version.")
    job = m.VideoJob(tenant_id=user.tenant_id, version_id=version.id, idempotency_key=key, package_sha256=version.package_sha256,
                     settings=settings, state="submitting", created_by=user.user_id)
    db.add(job)
    try:
        db.commit()
    except IntegrityError:  # two clicks at once: the other request created it
        db.rollback()
        return {**_summary(db, version), "idempotent_replay": True}
    _send(db, request, job, version, user)
    return {**_summary(db, version), "idempotent_replay": False}


@router.post("/video-jobs/{job_id}/remake", status_code=202)
def remake(job_id: str, body: RemakeIn, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(operator)):
    """Make a finished video again in another size or theme from its lesson bundle. The narration is reused: nothing is spoken again."""
    source = _get_job(db, job_id, user)
    version = db.get(m.LessonVersion, source.version_id)
    if source.state != "succeeded":
        raise HTTPException(409, "Only a finished video can be made again.")
    if version.review_status != "approved":
        raise HTTPException(409, "Only approved content can be sent to video production.")
    if body.profile not in PROFILES:
        raise HTTPException(422, f"Unknown output profile. Use one of: {', '.join(PROFILES)}.")
    if body.theme not in THEMES:
        raise HTTPException(422, f"Unknown theme. Use one of: {', '.join(THEMES)}.")
    if not db.scalar(select(m.VideoAsset).where(m.VideoAsset.job_id == source.id, m.VideoAsset.kind == "lesson_bundle")):
        raise HTTPException(409, "This video has no lesson bundle (videos made before bundles existed cannot be made again). Make a new video instead.")
    if any(j.state in m.ACTIVE_JOB_STATES for j in db.scalars(select(m.VideoJob).where(m.VideoJob.version_id == version.id))):
        raise HTTPException(409, "A video is already being made for this version.")
    settings = {**{k: v for k, v in (source.settings or {}).items() if k != "from_job"}, "profile": body.profile, "theme": body.theme, "subtitles": body.subtitles,
                "style": "animated", "from_job": source.id}
    base = hashlib.sha256(json.dumps([source.id, settings], sort_keys=True).encode()).hexdigest()
    runs = db.scalar(select(func.count()).select_from(m.VideoJob).where(m.VideoJob.version_id == version.id, m.VideoJob.idempotency_key.like(f"lv-remake-{base[:20]}-%"))) or 0
    job = m.VideoJob(tenant_id=user.tenant_id, version_id=version.id, idempotency_key=f"lv-remake-{base[:20]}-{runs}", package_sha256=source.package_sha256,
                     settings=settings, state="submitting", created_by=user.user_id)
    db.add(job)
    db.commit()
    _send(db, request, job, version, user)
    db.commit()
    return _summary(db, version)


@router.post("/video-jobs/{job_id}/retry")
def retry(job_id: str, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(operator)):
    job = _get_job(db, job_id, user)
    version = db.get(m.LessonVersion, job.version_id)
    if job.state != "failed" or not job.retryable:
        raise HTTPException(409, "This video cannot be retried. Start a new one instead.")
    if job.error_code in ("asset_corrupt", "storage_unavailable"):  # the video exists; only collecting it failed
        job.state, job.error_code, job.error_message, job.finished_at = "finalizing", None, None, None
        db.commit()
        _refresh(db, request, job)
    elif not job.engine_job_id:
        _send(db, request, job, version, user)
    else:
        try:
            st = client_of(request).retry(job.engine_job_id, cid_of(request))
            job.state, job.error_code, job.error_message, job.retryable, job.finished_at = st["state"], None, None, False, None
            db.commit()
        except EngineUnavailable:
            raise HTTPException(503, FRIENDLY["engine_unavailable"]) from None
        except EngineRejected as exc:
            raise HTTPException(409, exc.message or "The video service could not retry this job.") from None
    return _summary(db, version)


@router.post("/video-jobs/{job_id}/cancel")
def cancel(job_id: str, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(operator)):
    job = _get_job(db, job_id, user)
    version = db.get(m.LessonVersion, job.version_id)
    if job.state not in m.ACTIVE_JOB_STATES:
        raise HTTPException(409, "This video has already finished.")
    if not job.engine_job_id:
        job.state, job.finished_at = "cancelled", m.utcnow()
    else:
        try:
            st = client_of(request).cancel(job.engine_job_id, cid_of(request))
        except EngineUnavailable:
            raise HTTPException(503, FRIENDLY["engine_unavailable"]) from None
        except EngineRejected as exc:
            raise HTTPException(409, exc.message) from None
        if st["state"] == "cancelled":
            job.state, job.finished_at = "cancelled", m.utcnow()
    db.commit()
    return _summary(db, version)


@router.get("/video-jobs/{job_id}/narration-batch")
def narration_batch(job_id: str, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    job = _get_job(db, job_id, user)
    if not job.engine_job_id:
        raise HTTPException(409, "This video has not reached the video service.")
    try:
        return client_of(request).narration_batch(job.engine_job_id, cid_of(request))
    except EngineUnavailable:
        raise HTTPException(503, FRIENDLY["engine_unavailable"]) from None
    except EngineRejected as exc:
        raise HTTPException(409, exc.message) from None


@router.post("/video-jobs/{job_id}/audio")
async def upload_audio(job_id: str, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(operator)):
    job = _get_job(db, job_id, user)
    if job.state != "awaiting_audio" or not job.engine_job_id:
        raise HTTPException(409, "This video is not waiting for narration audio.")
    form = await request.form()
    up = form.get("audio")
    if not isinstance(up, UploadFile):
        raise HTTPException(422, "Choose the narration ZIP file.")
    data = await up.read()
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "The audio file is too large.")
    try:
        st = client_of(request).upload_audio(job.engine_job_id, data, cid_of(request))
    except EngineUnavailable:
        raise HTTPException(503, FRIENDLY["engine_unavailable"]) from None
    except EngineRejected as exc:
        issues = [{"code": exc.code, "message": str(d)} for d in exc.details] or [{"code": exc.code, "message": exc.message}]
        raise HTTPException(422, {"message": exc.message, "issues": issues}) from None
    job.state = st["state"]
    db.commit()
    return _summary(db, db.get(m.LessonVersion, job.version_id))


def _available(request: Request, asset: m.VideoAsset) -> bool:
    if is_remote(asset.local_path):
        store = request.app.state.store
        return store is not None and store.exists(key_of(asset.local_path))
    return Path(asset.local_path).is_file()


def _serve(request: Request, asset: m.VideoAsset, filename: str, download: bool):
    """A local file is streamed; a stored one is a redirect to a short-lived signed link, so the video never passes through here."""
    if is_remote(asset.local_path):
        url = request.app.state.store.url(key_of(asset.local_path), filename, asset.content_type, download)
        return RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})
    return FileResponse(asset.local_path, media_type=asset.content_type, filename=filename)


@router.get("/video-jobs/{job_id}/quality")
def quality_report(job_id: str, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    """The automated quality check of a finished video (checks, scores, what needs a person)."""
    job = _get_job(db, job_id, user)
    asset = db.scalar(select(m.VideoAsset).where(m.VideoAsset.job_id == job.id, m.VideoAsset.kind == "quality_report"))
    if asset is None:
        raise HTTPException(404, "There is no quality report for this video.")
    try:
        if is_remote(asset.local_path):
            store = request.app.state.store
            raw = store.read_bytes(key_of(asset.local_path)) if store is not None else None
        else:
            raw = Path(asset.local_path).read_bytes() if Path(asset.local_path).is_file() else None
        return json.loads(raw) if raw else _no_report()
    except (ValueError, OSError, StorageError):
        return _no_report()


def _no_report():
    raise HTTPException(404, "The quality report is not available.")


@router.get("/video-jobs/{job_id}/download")
def download(job_id: str, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    job = _get_job(db, job_id, user)
    asset = db.scalar(select(m.VideoAsset).where(m.VideoAsset.job_id == job.id, m.VideoAsset.kind == "video"))
    if job.state != "succeeded" or asset is None or not _available(request, asset):
        raise HTTPException(404, "The video is not available.")
    return _serve(request, asset, f"{asset.version_id}.mp4", download=False)


@router.get("/video-jobs/{job_id}/assets/{asset_id}")
def download_asset(job_id: str, asset_id: str, request: Request, db: Session = Depends(get_db), user: CurrentUser = Depends(current_user)):
    job = _get_job(db, job_id, user)
    asset = owned(db, m.VideoAsset, asset_id, user)
    if asset.job_id != job.id or not _available(request, asset):
        raise HTTPException(404, "The file is not available.")
    return _serve(request, asset, asset.filename, download=True)
