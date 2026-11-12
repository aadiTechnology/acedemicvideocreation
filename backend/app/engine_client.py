"""The only module that talks to the Video Engine. It uses the engine's versioned HTTP API (contract 1.x) and nothing else:
no engine imports, no engine database. URL and key come from the environment and never reach the browser."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from pathlib import Path

import httpx

from app.config import Settings

logger = logging.getLogger("academic.engine")

CONTRACT_VERSION = "1.3"
TOKEN_SCOPE = "video:create video:read video:cancel"
RENEW_BEFORE_SECONDS = 60
APPLICATION_ID = "aadi-academic"


class EngineUnavailable(Exception):
    """Timeout, connection failure or a 5xx from the engine. Safe to retry."""


class EngineRejected(Exception):
    """The engine answered 4xx. ``code`` is the engine's error code."""

    def __init__(self, status: int, code: str, message: str, details: list | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details or []


class EngineClient:
    """Calls the Video Engine. Authentication is VIDEO_ENGINE_AUTH: ``key`` (the shared X-Engine-Key), ``token`` (a short-lived Aadi Identity
    service token for the caller's company, cached and renewed before it expires) or ``auto`` (token, and the key if Identity cannot give one)."""

    def __init__(self, settings: Settings, http: httpx.Client | None = None, identity_http: httpx.Client | None = None) -> None:
        self.s = settings
        self.http = http or httpx.Client(base_url=settings.video_engine_url, timeout=settings.video_engine_timeout)
        self.identity_http = identity_http or httpx.Client(timeout=10)
        self._tokens: dict[str, tuple[str, float]] = {}  # company -> (token, monotonic expiry)
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        if not self.s.video_engine_url:
            return False
        has_key = bool(self.s.video_engine_api_key)
        has_token = bool(self.s.video_engine_client_id and self.s.video_engine_client_secret and self.s.identity_issuer_url)
        mode = self.s.video_engine_auth
        return has_key if mode == "key" else has_token if mode == "token" else (has_token or has_key)

    def _token(self, tenant: str) -> str:
        with self._lock:
            got = self._tokens.get(tenant)
            if got and got[1] - time.monotonic() > RENEW_BEFORE_SECONDS:
                return got[0]
            try:
                r = self.identity_http.post(f"{self.s.identity_issuer_url}/token", data={
                    "grant_type": "client_credentials", "client_id": self.s.video_engine_client_id, "client_secret": self.s.video_engine_client_secret,
                    "audience": "video-engine", "scope": TOKEN_SCOPE, "tenant_id": tenant})
            except httpx.HTTPError as exc:
                raise EngineUnavailable("Aadi Identity could not be reached for a Video Engine token.") from exc
            if r.status_code != 200:
                logger.warning("Identity refused a Video Engine token for the company: %s %s", r.status_code, r.text[:200])
                raise EngineUnavailable("Aadi Identity did not issue a Video Engine token.")
            body = r.json()
            self._tokens[tenant] = (body["access_token"], time.monotonic() + int(body.get("expires_in", 600)))
            return body["access_token"]

    def _forget_token(self, tenant: str | None) -> None:
        with self._lock:
            self._tokens.pop(tenant or "", None)

    def _headers(self, correlation_id: str | None, tenant: str | None = None) -> dict:
        h = {"X-Correlation-Id": correlation_id or uuid.uuid4().hex}
        mode = self.s.video_engine_auth
        if tenant:  # who is asking: the engine only shows this company's jobs (isolation, engine contract 1.3+)
            h["X-Caller-App"], h["X-Tenant-Id"] = APPLICATION_ID, tenant
        if mode != "key":
            try:
                if not tenant:
                    raise EngineUnavailable("A company is needed to get a Video Engine token.")
                h["Authorization"] = "Bearer " + self._token(tenant)
                return h
            except EngineUnavailable:
                if mode == "token" or not self.s.video_engine_api_key:
                    raise
                logger.warning("falling back to the shared engine key (VIDEO_ENGINE_AUTH=auto)")
        h["X-Engine-Key"] = self.s.video_engine_api_key
        return h

    def _request(self, method: str, path: str, correlation_id: str | None = None, tenant: str | None = None, **kw) -> httpx.Response:
        if not self.configured:
            raise EngineUnavailable("The Video Engine is not configured.")
        extra = kw.pop("headers", {})
        try:
            headers = self._headers(correlation_id, tenant)
            resp = self.http.request(method, path, headers={**headers, **extra}, **kw)
            if resp.status_code == 401 and "Authorization" in headers:  # expired or rotated: ask again once
                self._forget_token(tenant)
                resp = self.http.request(method, path, headers={**self._headers(correlation_id, tenant), **extra}, **kw)
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
    def capabilities(self, cid: str | None = None, tenant: str | None = None) -> dict:
        return self._request("GET", "/api/v1/capabilities", cid, tenant).json()

    def submit(self, manifest: dict, package: bytes, idempotency_key: str, cid: str | None = None, tenant: str | None = None) -> dict:
        resp = self._request("POST", "/api/v1/video-jobs", cid, tenant, headers={"Idempotency-Key": idempotency_key},
                             data={"manifest": json.dumps(manifest)}, files={"package": ("package.zip", package, "application/zip")})
        return resp.json()

    def status(self, job_id: str, cid: str | None = None, tenant: str | None = None) -> dict:
        return self._request("GET", f"/api/v1/video-jobs/{job_id}", cid, tenant).json()

    def retry(self, job_id: str, cid: str | None = None, tenant: str | None = None) -> dict:
        return self._request("POST", f"/api/v1/video-jobs/{job_id}/retry", cid, tenant).json()

    def cancel(self, job_id: str, cid: str | None = None, tenant: str | None = None) -> dict:
        return self._request("POST", f"/api/v1/video-jobs/{job_id}/cancel", cid, tenant).json()

    def assets(self, job_id: str, cid: str | None = None, tenant: str | None = None) -> list[dict]:
        return self._request("GET", f"/api/v1/video-jobs/{job_id}/assets", cid, tenant).json()["assets"]

    def narration_batch(self, job_id: str, cid: str | None = None, tenant: str | None = None) -> dict:
        return self._request("GET", f"/api/v1/video-jobs/{job_id}/narration-batch", cid, tenant).json()

    def upload_audio(self, job_id: str, data: bytes, cid: str | None = None, tenant: str | None = None) -> dict:
        return self._request("POST", f"/api/v1/video-jobs/{job_id}/audio", cid, tenant, files={"audio": ("audio.zip", data, "application/zip")}).json()

    def preview(self, payload: dict, cid: str | None = None, tenant: str | None = None) -> bytes:
        return self._request("POST", "/api/v1/previews", cid, tenant, json=payload).content

    def layouts(self, cid: str | None = None, tenant: str | None = None) -> dict:
        return self._request("GET", "/api/v1/layouts", cid, tenant).json()

    def recommend(self, payload: dict, cid: str | None = None, tenant: str | None = None) -> dict:
        return self._request("POST", "/api/v1/layouts/recommend", cid, tenant, json=payload).json()

    def download_asset(self, job_id: str, asset_id: str, target: Path, cid: str | None = None, tenant: str | None = None) -> None:
        """Stream an asset to ``target`` (a temporary file is renamed on success)."""
        if not self.configured:
            raise EngineUnavailable("The Video Engine is not configured.")
        tmp = target.with_suffix(target.suffix + ".part")
        try:
            with self.http.stream("GET", f"/api/v1/video-jobs/{job_id}/assets/{asset_id}/content", headers=self._headers(cid, tenant)) as resp:
                if resp.status_code == 401:
                    self._forget_token(tenant)  # the next attempt asks Identity for a fresh token
                if resp.status_code >= 400:
                    raise EngineUnavailable("The video file could not be fetched from the Video Engine.")
                with tmp.open("wb") as out:
                    for chunk in resp.iter_bytes(1024 * 1024):
                        out.write(chunk)
        except httpx.HTTPError as exc:
            tmp.unlink(missing_ok=True)
            raise EngineUnavailable("The video file could not be fetched from the Video Engine.") from exc
        tmp.replace(target)
