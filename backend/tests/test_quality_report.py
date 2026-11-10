"""The quality report of a finished video: sent target length, served from local storage or the bucket, tenant-safe."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings
from tests.fake_engine import FakeEngine
from tests.test_storage_b2 import REPORT, FakeStore
from tests.test_video import PROD, approved_version


@pytest.fixture()
def engine():
    e = FakeEngine()
    e.report = REPORT
    return e


def client_for(engine, store=None):
    settings = make_settings(video_engine_url="http://engine.test", video_engine_api_key=FakeEngine.KEY)
    return TestClient(create_app(settings, engine_http=engine.http, object_store=store), follow_redirects=False)


def finish(client, engine, vid):
    assert client.post(f"/api/lesson-versions/{vid}/video", json={"provider": "azure", "subtitles": True}, headers=PROD).status_code == 202
    engine.set(engine.only_job(), "succeeded", 100)
    return client.get(f"/api/lesson-versions/{vid}/video").json()


def test_the_planned_length_is_sent_to_the_engine(engine):
    with client_for(engine) as client:
        vid = approved_version(client)
        client.post(f"/api/lesson-versions/{vid}/video", json={"provider": "azure"}, headers=PROD)
        assert engine.jobs[engine.only_job()]["manifest"]["quality"] == {"target_minutes": 1.0}  # the lesson's expected minutes


def test_report_is_served_from_local_storage_and_listed_as_an_asset(engine):
    with client_for(engine) as client:
        vid = approved_version(client)
        s = finish(client, engine, vid)
        assert "quality_report" in {a["kind"] for a in s["assets"]}
        r = client.get(f"/api/video-jobs/{s['job']['id']}/quality")
        assert r.status_code == 200 and r.json()["estimate"]["score"] == 92 and r.json()["checks"][0]["id"] == "sync.order"


def test_report_is_read_from_the_bucket_when_stored_there(engine):
    store = FakeStore()
    with client_for(engine, store) as client:
        vid = approved_version(client)
        s = finish(client, engine, vid)
        assert any(k.endswith("quality_report-quality_report.json") for k in store.objects)
        assert client.get(f"/api/video-jobs/{s['job']['id']}/quality").json()["summary"]["warnings"] == 1


def test_no_report_for_older_videos(engine):
    engine.report = None
    with client_for(engine) as client:
        vid = approved_version(client)
        s = finish(client, engine, vid)
        assert client.get(f"/api/video-jobs/{s['job']['id']}/quality").status_code == 404


def test_other_tenants_are_refused(engine):
    with client_for(engine) as client:
        vid = approved_version(client)
        s = finish(client, engine, vid)
        assert client.get(f"/api/video-jobs/{s['job']['id']}/quality", headers={"X-Dev-Tenant": "other"}).status_code == 404


def test_a_missing_object_in_the_bucket_gives_a_clean_404(engine):
    store = FakeStore()
    with client_for(engine, store) as client:
        vid = approved_version(client)
        s = finish(client, engine, vid)
        store.objects.clear()
        assert client.get(f"/api/video-jobs/{s['job']['id']}/quality").status_code == 404
