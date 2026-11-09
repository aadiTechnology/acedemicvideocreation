"""Slide editor: save validates like an import, resets approval, and preview/recommend go through the engine."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from tests.fake_engine import FakeEngine
from tests.test_video import OP, REVIEWER, approved_version, make_client
from tests.test_versions_review import CSV, do_import, setup

GOOD = {"headline": "How it works", "bullets": ["Light enters", "It bends"], "layout": "flow", "diagram": {"steps": ["Light", "Glass", "Bends"]}}


@pytest.fixture()
def engine():
    return FakeEngine()


@pytest.fixture()
def client(engine):
    with make_client(engine) as c:
        yield c


def package_plan(client, vid):
    raw = client.get(f"/api/lesson-versions/{vid}/package").content
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        return json.loads(zf.read("lesson_plan.json"))


def test_save_changes_the_layout_and_the_stored_package(client):
    vid = approved_version(client)
    before = client.get(f"/api/lesson-versions/{vid}").json()["package_sha256"]
    r = client.put(f"/api/lesson-versions/{vid}/slides/1", json=GOOD, headers=OP)
    assert r.status_code == 200, r.text
    entry = next(s for s in package_plan(client, vid)["slides"] if s["slide"] == 1)
    assert (entry["layout"], entry["diagram"]["steps"]) == ("flow", ["Light", "Glass", "Bends"])
    assert r.json()["package_sha256"] != before
    got = client.get(f"/api/lesson-versions/{vid}/slides/1").json()
    assert got["plan"]["layout"] == "flow" and got["row"]["slide"] == 1


def test_editing_an_approved_version_cancels_the_approval(client):
    vid = approved_version(client)
    assert client.get(f"/api/lesson-versions/{vid}").json()["review_status"] == "approved"
    r = client.put(f"/api/lesson-versions/{vid}/slides/1", json=GOOD, headers=OP)
    assert r.json()["review_status"] == "draft"
    assert client.get(f"/api/lesson-versions/{vid}").json()["events"][-1]["action"] == "content_changed"


def test_invalid_edits_are_rejected_and_change_nothing(client):
    vid = approved_version(client)
    before = client.get(f"/api/lesson-versions/{vid}").json()["package_sha256"]
    for bad in ({**GOOD, "diagram": {"steps": ["only one"]}}, {**GOOD, "layout": "spiral"}, {**GOOD, "headline": ""},
                {"headline": "H", "layout": "recap", "bullets": ["one"]}):
        r = client.put(f"/api/lesson-versions/{vid}/slides/1", json=bad, headers=OP)
        assert r.status_code == 422, (bad, r.text)
    assert client.get(f"/api/lesson-versions/{vid}").json()["package_sha256"] == before


def test_only_content_operators_can_save_and_unknown_slides_are_404(client):
    vid = approved_version(client)
    assert client.put(f"/api/lesson-versions/{vid}/slides/1", json=GOOD, headers=REVIEWER).status_code == 403
    assert client.put(f"/api/lesson-versions/{vid}/slides/99", json=GOOD, headers=OP).status_code == 404
    assert client.put(f"/api/lesson-versions/{vid}/slides/1", json=GOOD, headers={"X-Dev-Tenant": "other", **OP}).status_code == 404


def test_other_tenants_cannot_read_or_preview(client):
    vid = approved_version(client)
    other = {"X-Dev-Tenant": "other"}
    assert client.get(f"/api/lesson-versions/{vid}/slides/1", headers=other).status_code == 404
    assert client.post(f"/api/lesson-versions/{vid}/slides/1/preview", json={}, headers=other).status_code == 404


def test_preview_sends_the_draft_to_the_engine_and_returns_a_png(client, engine):
    vid = approved_version(client)
    r = client.post(f"/api/lesson-versions/{vid}/slides/1/preview", json={"plan": GOOD, "at": 0.5, "profile": "480p24"})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content.startswith(b"\x89PNG")
    sent = engine.previews[-1]
    assert (sent["plan"]["layout"], sent["at"], sent["profile"], sent["language"], sent["slide"]["Slide"]) == ("flow", 0.5, "480p24", "en-IN", 1)
    assert sent["slide"]["voice_text"].startswith("Plants make food")


def test_preview_of_an_invalid_draft_is_refused_before_the_engine(client, engine):
    vid = approved_version(client)
    r = client.post(f"/api/lesson-versions/{vid}/slides/1/preview", json={"plan": {**GOOD, "diagram": {"steps": ["x"]}}})
    assert r.status_code == 422 and not engine.previews


def test_preview_without_a_draft_uses_the_saved_slide(client, engine):
    vid = approved_version(client)
    assert client.post(f"/api/lesson-versions/{vid}/slides/2/preview", json={}).status_code == 200
    assert engine.previews[-1]["slide"]["Module"] == "Process"


def test_engine_down_gives_a_friendly_error(client, engine):
    vid = approved_version(client)
    engine.down = True
    r = client.post(f"/api/lesson-versions/{vid}/slides/1/preview", json={})
    assert r.status_code == 503 and "not reachable" in r.json()["detail"]


def test_recommendation_carries_the_lesson_context(client, engine):
    vid = approved_version(client)
    r = client.post(f"/api/lesson-versions/{vid}/slides/1/recommend")
    assert r.json()["recommendations"][0]["layout"] == "flow"
    ctx = engine.recommends[-1]
    assert (ctx["class_name"], ctx["subject"]) == ("Class 7", "Science") and "Explain photosynthesis" in ctx["objective"]


def test_layout_list_is_served(client):
    assert [l["name"] for l in client.get("/api/layouts").json()["layouts"]] == ["bullets", "timeline"]
