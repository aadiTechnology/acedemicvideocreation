"""Administrators see what their own school's videos used; nobody else does."""

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import as_tenant, make_settings
from tests.fake_engine import FakeEngine


def make(engine):
    return TestClient(create_app(make_settings(video_engine_url="http://engine.test", video_engine_api_key=FakeEngine.KEY), engine_http=engine.http))


def event(tenant, meter, quantity, unit):
    return {"event_id": meter + tenant, "ts": "2026-11-12T10:00:00+00:00", "tenant_id": tenant, "client_id": "aadi-academic", "meter": meter,
            "quantity": quantity, "unit": unit, "dimension": None, "job_id": "j1"}


def test_an_administrator_sees_only_their_own_school(monkeypatch):
    engine = FakeEngine()
    engine.usage_events = [event("tenant-a", "video.slides_rendered", 8, "slide"), event("tenant-a", "video.minutes_rendered", 1.05, "minute"),
                           event("tenant-b", "video.slides_rendered", 99, "slide")]
    with make(engine) as c:
        r = c.get("/api/video/usage", headers={**as_tenant("tenant-a"), "X-Dev-Roles": "admin"})
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 2 and body["totals"] == {"video.slides_rendered": 8, "video.minutes_rendered": 1.05}
        assert {e["tenant_id"] for e in body["events"]} == {"tenant-a"}


def test_other_roles_cannot_read_usage_and_an_engine_outage_is_a_plain_message():
    engine = FakeEngine()
    with make(engine) as c:
        assert c.get("/api/video/usage", headers={**as_tenant("tenant-a"), "X-Dev-Roles": "reviewer"}).status_code == 403
        engine.down = True
        r = c.get("/api/video/usage", headers={**as_tenant("tenant-a"), "X-Dev-Roles": "admin"})
        assert r.status_code == 503 and "not reachable" in r.json()["detail"]
