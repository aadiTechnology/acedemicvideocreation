"""The only module that talks to the Video Engine. It uses the engine's versioned HTTP API (contract 1.x) and nothing else:
no engine imports, no engine database. URL and key come from the environment and never reach the browser."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx

from app.config import Settings

CONTRACT_VERSION = "1.1"
APPLICATION_ID = "aadi-academic"


class EngineUnavailable(Exception):
    """Timeout, connection failure or a 5xx from the engine. Safe to retry."""


class EngineRejected(Exception):
    """The engine answered 4xx. ``code`` is the engine's error code."""

    def __init__(self, status: int, code: str, message: str, details: list | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details or []


class EngineClient:
    def __init__(self, settings: Settings, http: httpx.Client | None = None) -> None:
        self.s = settings
        self.http = http or httpx.Client(base_url=settings.video_engine_url, timeout=settings.video_engine_timeout)

    @property
    def configured(self) -> bool:
        return bool(self.s.video_engine_url and self.s.video_engine_api_key)

    def _headers(self, correlation_id: str | None) -> dict:
        return {"X-Engine-Key": self.s.video_engine_api_key, "X-Correlation-Id": correlation_id or uuid.uuid4().hex}

    def _request(self, method: str, path: str, correlation_id: str | None = None, **kw) -> httpx.Response:
        if not self.configured:
            raise EngineUnavailable("The Video Engine is not configured.")
        try:
            resp = self.http.request(method, path, headers={**self._headers(correlation_id), **kw.pop("headers", {})}, **kw)
        except httpx.HTTPError as exc:  # timeouts, refused connections, DNS
            raise EngineUnavailable("The Video Engine could not be reached.") from exc
        if resp.status_code >= 500:
            raise EngineUnavailable("The Video Engine had a problem.")
        if resp.status_code >= 400:
            try:
                err = resp.json()["error"]
            except (ValueError, KeyError, TypeError):
                err = {"code": "engine_error", "message": "The Video Engine refused the request."}
            raise EngineRejected(resp.status_code, err.get("code", "engine_error"), err.get("message", ""), err.get("details"))
        return resp

    # ---- API v1 -------------------------------------------------------------------------------------
    def capabilities(self, cid: str | None = None) -> dict:
        return self._request("GET", "/api/v1/capabilities", cid).json()

    def submit(self, manifest: dict, package: bytes, idempotency_key: str, cid: str | None = None) -> dict:
        resp = self._request("POST", "/api/v1/video-jobs", cid, headers={"Idempotency-Key": idempotency_key},
                             data={"manifest": json.dumps(manifest)}, files={"package": ("package.zip", package, "application/zip")})
        return resp.json()

    def status(self, job_id: str, cid: str | None = None) -> dict:
        return self._request("GET", f"/api/v1/video-jobs/{job_id}", cid).json()

    def retry(self, job_id: str, cid: str | None = None) -> dict:
        return self._request("POST", f"/api/v1/video-jobs/{job_id}/retry", cid).json()

    def cancel(self, job_id: str, cid: str | None = None) -> dict:
        return self._request("POST", f"/api/v1/video-jobs/{job_id}/cancel", cid).json()

    def assets(self, job_id: str, cid: str | None = None) -> list[dict]:
        return self._request("GET", f"/api/v1/video-jobs/{job_id}/assets", cid).json()["assets"]

    def narration_batch(self, job_id: str, cid: str | None = None) -> dict:
        return self._request("GET", f"/api/v1/video-jobs/{job_id}/narration-batch", cid).json()

    def upload_audio(self, job_id: str, data: bytes, cid: str | None = None) -> dict:
        return self._request("POST", f"/api/v1/video-jobs/{job_id}/audio", cid, files={"audio": ("audio.zip", data, "application/zip")}).json()

    def download_asset(self, job_id: str, asset_id: str, target: Path, cid: str | None = None) -> None:
        """Stream an asset to ``target`` (a temporary file is renamed on success)."""
        if not self.configured:
            raise EngineUnavailable("The Video Engine is not configured.")
        tmp = target.with_suffix(target.suffix + ".part")
        try:
            with self.http.stream("GET", f"/api/v1/video-jobs/{job_id}/assets/{asset_id}/content", headers=self._headers(cid)) as resp:
                if resp.status_code >= 400:
                    raise EngineUnavailable("The video file could not be fetched from the Video Engine.")
                with tmp.open("wb") as out:
                    for chunk in resp.iter_bytes(1024 * 1024):
                        out.write(chunk)
        except httpx.HTTPError as exc:
            tmp.unlink(missing_ok=True)
            raise EngineUnavailable("The video file could not be fetched from the Video Engine.") from exc
        tmp.replace(target)
