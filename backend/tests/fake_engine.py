"""A fake Video Engine that follows contract 1.2, served through httpx.MockTransport. Used to test the Academic integration."""

from __future__ import annotations

import email
import hashlib
import json
import uuid

import httpx


def _multipart(request: httpx.Request) -> dict:
    ctype = request.headers["content-type"].encode()
    msg = email.message_from_bytes(b"Content-Type: " + ctype + b"\r\n\r\n" + request.content)
    out = {}
    for part in msg.get_payload():
        out[part.get_param("name", header="content-disposition")] = part.get_payload(decode=True)
    return out


PNG = b"\x89PNG\r\n\x1a\nfake"


class FakeEngine:
    KEY = "engine-test-key"
    VIDEO = b"\x00\x00\x00\x18ftypmp42" + b"fake video bytes " * 50

    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.by_key: dict[str, str] = {}
        self.submits = 0
        self.bundle: bytes | None = None  # when set, finished jobs also list a lesson_bundle asset with this content
        self.report: dict | None = None  # when set, finished jobs also list a quality_report asset with this content
        self.previews: list[dict] = []
        self.recommends: list[dict] = []
        self.down = False
        self.reject: tuple[int, str, str] | None = None  # (status, code, message) for the next submit
        self.corrupt_download = False
        self.seen_headers: list[dict] = []
        self.http = httpx.Client(transport=httpx.MockTransport(self.handle), base_url="http://engine.test")

    # ---- test controls ----
    def set(self, job_id: str, state: str, percent: int = 0, **kw) -> None:
        self.jobs[job_id].update(state=state, percent=percent, **kw)

    def _report_bytes(self) -> bytes:
        return json.dumps(self.report).encode()

    def only_job(self) -> str:
        assert len(self.jobs) == 1, self.jobs.keys()
        return next(iter(self.jobs))

    # ---- the API ----
    @staticmethod
    def _err(status: int, code: str, message: str) -> httpx.Response:
        return httpx.Response(status, json={"error": {"code": code, "message": message, "details": []}, "correlation_id": "x"})

    def _status(self, jid: str) -> dict:
        j = self.jobs[jid]
        return {"job_id": jid, "state": j["state"], "progress": {"stage": j["state"], "percent": j["percent"]},
                "caller": j["manifest"]["caller"], "attempt": j["attempt"], "retryable": j.get("retryable", False),
                "error": j.get("error"), "created_at": "t", "updated_at": "t"}

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("engine is down")
        self.seen_headers.append(dict(request.headers))
        if request.headers.get("x-engine-key") != self.KEY:
            return self._err(401, "unauthorized", "Missing or invalid engine key.")
        path, method = request.url.path, request.method
        if path == "/api/v1/capabilities":
            return httpx.Response(200, json={"contract_version": "1.2", "languages": ["en-IN", "hi-IN", "mr-IN"], "output_profiles": ["1080p24", "720p24"],
                                             "providers": [{"name": "azure", "modes": ["api"], "configured": False, "voices": {}},
                                                           {"name": "colab", "modes": ["manual", "tunnel"], "configured": True, "voices": {"en-IN": ["default"]}}],
                                             "features": {"slide_renderer": True}, "limits": {}})
        if path == "/api/v1/previews" and method == "POST":
            self.previews.append(json.loads(request.content))
            return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
        if path == "/api/v1/layouts" and method == "GET":
            return httpx.Response(200, json={"layouts": [{"name": "bullets", "title": "Key points", "example": {}}, {"name": "timeline", "title": "Timeline", "example": {"diagram": {"events": []}}}]})
        if path == "/api/v1/layouts/recommend" and method == "POST":
            self.recommends.append(json.loads(request.content))
            return httpx.Response(200, json={"age_group": "11-13", "recommendations": [{"layout": "flow", "score": 6.0, "reason": "mentions 'process'"}]})
        if path == "/api/v1/video-jobs" and method == "POST":
            parts = _multipart(request)
            manifest = json.loads(parts["manifest"])
            key = request.headers["idempotency-key"]
            if key in self.by_key:
                jid = self.by_key[key]
                return httpx.Response(200, json={"job_id": jid, "state": self.jobs[jid]["state"], "idempotent_replay": True})
            if self.reject:
                status, code, message = self.reject
                self.reject = None
                return self._err(status, code, message)
            self.submits += 1
            jid = str(uuid.uuid4())
            awaiting = manifest["tts"]["provider"] == "colab" and manifest["tts"]["mode"] == "manual"
            self.jobs[jid] = {"state": "awaiting_audio" if awaiting else "queued", "percent": 0, "manifest": manifest, "package": parts["package"],
                              "attempt": 0, "key": key}
            self.by_key[key] = jid
            return httpx.Response(202, json={"job_id": jid, "state": self.jobs[jid]["state"], "idempotent_replay": False})
        segs = path.strip("/").split("/")  # api v1 video-jobs {id} [action [asset]]
        if segs[:3] != ["api", "v1", "video-jobs"] or len(segs) < 4 or segs[3] not in self.jobs:
            return self._err(404, "job_not_found", "No job with this id.")
        jid, rest = segs[3], segs[4:]
        job = self.jobs[jid]
        if not rest:
            return httpx.Response(200, json=self._status(jid))
        if rest == ["retry"]:
            if job["state"] != "failed" or not job.get("retryable"):
                return self._err(409, "not_retryable", "Only failed jobs with a retryable error can be retried.")
            job.update(state="queued", percent=0, error=None, retryable=False)
            return httpx.Response(200, json=self._status(jid))
        if rest == ["cancel"]:
            if job["state"] in ("succeeded", "failed", "cancelled"):
                return self._err(409, "not_cancellable", "The job has already finished.")
            job["state"] = "cancelled"
            return httpx.Response(200, json=self._status(jid))
        if rest == ["narration-batch"]:
            return httpx.Response(200, json={"job_id": jid, "language": job["manifest"]["language"], "voice": "default",
                                             "slides": [{"slide": 1, "text": "t", "text_sha256": "x"}]})
        if rest == ["audio"]:
            if job["state"] != "awaiting_audio":
                return self._err(409, "not_awaiting_audio", "This job is not waiting for narration audio.")
            parts = _multipart(request)
            if parts["audio"] == b"bad":
                return self._err(422, "invalid_audio", "The narration audio is incomplete or invalid.")
            job["state"] = "queued"
            return httpx.Response(200, json=self._status(jid))
        if rest == ["assets"]:
            return httpx.Response(200, json={"job_id": jid, "assets": [
                {"asset_id": "a-video", "kind": "video", "filename": "final_video.mp4", "content_type": "video/mp4", "size_bytes": len(self.VIDEO),
                 "sha256": hashlib.sha256(self.VIDEO).hexdigest(), "duration_seconds": 12.5, "width": 1920, "height": 1080, "fps": 24},
                {"asset_id": "a-cfg", "kind": "render_config", "filename": "render_config.json", "content_type": "application/json",
                 "size_bytes": 2, "sha256": hashlib.sha256(b"{}").hexdigest()},
                *([{"asset_id": "a-bundle", "kind": "lesson_bundle", "filename": "lesson_bundle.zip", "content_type": "application/zip",
                    "size_bytes": len(self.bundle), "sha256": hashlib.sha256(self.bundle).hexdigest()}] if self.bundle else []),
                *([{"asset_id": "a-qr", "kind": "quality_report", "filename": "quality_report.json", "content_type": "application/json",
                    "size_bytes": len(self._report_bytes()), "sha256": hashlib.sha256(self._report_bytes()).hexdigest()}] if self.report else [])]})
        if rest[0] == "assets" and rest[-1] == "content":
            body = self.VIDEO if rest[1] == "a-video" else self._report_bytes() if rest[1] == "a-qr" else self.bundle if rest[1] == "a-bundle" else b"{}"
            if self.corrupt_download and rest[1] == "a-video":
                body = body[:-1] + b"X"
            return httpx.Response(200, content=body)
        return self._err(404, "not_found", "Unknown route.")
