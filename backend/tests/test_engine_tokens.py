"""Academic gets a short-lived Identity token per company for every Video Engine call (VIDEO_ENGINE_AUTH=token|auto), key as fallback."""

import itertools

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.engine_client import EngineClient
from app.main import create_app
from tests.conftest import make_settings
from tests.fake_engine import FakeEngine
from tests.test_video import approved_version, gen

ISSUER = "https://id.test"


class FakeIdentity:
    """Answers POST /token like Aadi Identity's client_credentials grant; every call issues a new token."""

    def __init__(self, engine: FakeEngine) -> None:
        self.engine, self.calls, self.mode, self.n = engine, [], "ok", itertools.count(1)
        self.http = httpx.Client(transport=httpx.MockTransport(self.handle))

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.mode == "down":
            raise httpx.ConnectError("identity is down")
        form = dict(httpx.QueryParams(request.content.decode()))
        self.calls.append(form)
        if self.mode == "denied" or form["client_secret"] != "svc-secret":
            return httpx.Response(400, json={"error": "access_denied"})
        tok = f"tok-{next(self.n)}-{form['tenant_id']}"
        self.engine.valid_tokens.add(tok)
        return httpx.Response(200, json={"access_token": tok, "token_type": "Bearer", "expires_in": 600, "scope": form["scope"]})


def make(engine, mode, **over):
    idp = FakeIdentity(engine)
    settings = make_settings(video_engine_url="http://engine.test", video_engine_api_key=FakeEngine.KEY if mode != "token" else "", video_engine_auth=mode,
                             identity_issuer_url=ISSUER, video_engine_client_id="academic-video", video_engine_client_secret="svc-secret", **over)
    return TestClient(create_app(settings, engine_http=engine.http, identity_http=idp.http)), idp


def test_token_mode_sends_a_bearer_token_for_the_users_company_and_never_the_key():
    engine = FakeEngine()
    client, idp = make(engine, "token")
    with client as c:
        h = {"X-Dev-Tenant": "tenant-a"}
        vid = approved_version(c, h)
        assert gen(c, vid, h).status_code in (200, 201, 202)
        assert engine.submits == 1
        assert engine.seen_headers and all(x.get("authorization") and "x-engine-key" not in x for x in engine.seen_headers)
        assert idp.calls and all(call["tenant_id"] == "tenant-a" and call["audience"] == "video-engine" for call in idp.calls)
        assert all(x["x-tenant-id"] == "tenant-a" and x["x-caller-app"] == "aadi-academic" for x in engine.seen_headers if "x-tenant-id" in x)


def test_tokens_are_cached_per_company():
    engine = FakeEngine()
    client, idp = make(engine, "token")
    with client as c:
        for t in ("tenant-a", "tenant-b"):
            assert c.get("/api/video/capabilities", headers={"X-Dev-Tenant": t}).status_code == 200
            assert c.get("/api/video/capabilities", headers={"X-Dev-Tenant": t}).status_code == 200
    assert sorted(call["tenant_id"] for call in idp.calls) == ["tenant-a", "tenant-b"]  # one token each, reused


def test_a_rejected_token_is_replaced_once():
    engine = FakeEngine()
    client, idp = make(engine, "token")
    with client as c:
        h = {"X-Dev-Tenant": "tenant-a"}
        assert c.get("/api/video/capabilities", headers=h).status_code == 200
        engine.valid_tokens.clear()  # the engine no longer accepts it (expired or keys rotated)
        assert c.get("/api/video/capabilities", headers=h).status_code == 200
    assert len(idp.calls) == 2


@pytest.mark.parametrize("mode", ["denied", "down"])
def test_token_mode_fails_closed_when_identity_refuses_or_is_down(mode):
    engine = FakeEngine()
    client, idp = make(engine, "token")
    idp.mode = mode
    with client as c:
        assert c.get("/api/video/capabilities", headers={"X-Dev-Tenant": "tenant-a"}).status_code == 503
    assert engine.seen_headers == []  # nothing was sent to the engine without credentials


def test_auto_mode_uses_tokens_and_falls_back_to_the_key():
    engine = FakeEngine()
    client, idp = make(engine, "auto")
    with client as c:
        assert c.get("/api/video/capabilities", headers={"X-Dev-Tenant": "tenant-a"}).status_code == 200
        assert "authorization" in engine.seen_headers[-1] and "x-engine-key" not in engine.seen_headers[-1]
        idp.mode = "down"
        assert c.get("/api/video/capabilities", headers={"X-Dev-Tenant": "tenant-b"}).status_code == 200
        assert engine.seen_headers[-1].get("x-engine-key") == FakeEngine.KEY and "authorization" not in engine.seen_headers[-1]


def test_key_mode_is_unchanged_and_never_calls_identity():
    engine = FakeEngine()
    client, idp = make(engine, "key")
    with client as c:
        assert c.get("/api/video/capabilities", headers={"X-Dev-Tenant": "tenant-a"}).status_code == 200
    assert idp.calls == [] and engine.seen_headers[-1].get("x-engine-key") == FakeEngine.KEY


def test_configured_and_settings_validation():
    base = dict(video_engine_url="http://e", identity_issuer_url=ISSUER)
    assert EngineClient(make_settings(**base, video_engine_auth="token", video_engine_client_id="c", video_engine_client_secret="s")).configured
    assert not EngineClient(make_settings(**base, video_engine_auth="token")).configured
    assert EngineClient(make_settings(**base, video_engine_auth="key", video_engine_api_key="k")).configured
    with pytest.raises(RuntimeError):
        load_settings({"VIDEO_ENGINE_AUTH": "token", "AUTH_MODE": "dev"})
    with pytest.raises(RuntimeError):
        load_settings({"VIDEO_ENGINE_AUTH": "sometimes", "AUTH_MODE": "dev"})
    assert load_settings({"AUTH_MODE": "dev"}).video_engine_auth == "key"
