"""Approved lesson to engine to downloadable video, with failures, duplicates and restarts."""

import hashlib
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import as_tenant, make_settings
from tests.fake_engine import FakeEngine
from tests.test_versions_review import CSV, do_import, setup

OP = {"X-Dev-Roles": "content_operator"}
REVIEWER = {"X-Dev-Roles": "reviewer"}
PROD = {"X-Dev-Roles": "production_operator"}


@pytest.fixture()
def engine():
    return FakeEngine()


def make_client(engine, **over):
    settings = make_settings(video_engine_url="http://engine.test", video_engine_api_key=FakeEngine.KEY, **over)
    return TestClient(create_app(settings, engine_http=engine.http))


@pytest.fixture()
def client(engine):
    with make_client(engine) as c:
        yield c


def approved_version(client, headers=None, languages=("en-IN",)):
    h = headers or {}
    _, vid = setup(client, h, languages=languages)
    assert do_import(client, vid, [("lesson.csv", CSV, "text/csv")], headers={**h, **OP}).status_code == 200
    client.post(f"/api/lesson-versions/{vid}/review", json={"action": "submit"}, headers={**h, **OP})
    client.post(f"/api/lesson-versions/{vid}/review", json={"action": "approve"}, headers={**h, **REVIEWER})
    return vid


def gen(client, vid, headers=None, **body):
    return client.post(f"/api/lesson-versions/{vid}/video", json={"provider": "azure", **body}, headers={**(headers or {}), **PROD})


def test_only_approved_content_with_a_package_can_be_generated(client, engine):
    _, vid = setup(client)
    assert gen(client, vid).status_code == 409  # no content
    do_import(client, vid, [("lesson.csv", CSV, "text/csv")])
    r = gen(client, vid)
    assert r.status_code == 409 and "approved" in r.json()["detail"]
    client.post(f"/api/lesson-versions/{vid}/review", json={"action": "submit"})
    assert gen(client, vid).status_code == 409  # in review
    assert engine.submits == 0
    assert client.get(f"/api/lesson-versions/{vid}/video").json()["can_generate"] is False


def test_role_and_input_checks(client):
    vid = approved_version(client)
    assert client.post(f"/api/lesson-versions/{vid}/video", json={"provider": "azure"}, headers=REVIEWER).status_code == 403
    assert gen(client, vid, profile="4k").status_code == 422
    assert gen(client, vid, provider="nope").status_code == 422
    assert gen(client, vid, provider="azure", mode="manual").status_code == 422


def test_full_flow_submit_progress_copy_and_download(client, engine):
    vid = approved_version(client)
    r = gen(client, vid, profile="720p24", subtitles=False)
    assert r.status_code == 202 and r.json()["job"]["state"] == "queued" and r.json()["idempotent_replay"] is False
    jid = engine.only_job()
    m = engine.jobs[jid]["manifest"]
    assert (m["contract_version"], m["caller"]["application_id"], m["caller"]["external_ref"], m["language"]) == ("1.1", "aadi-academic", vid, "en-IN")
    assert (m["caller"]["tenant_ref"], m["render"]["profile"], m["render"]["subtitles"]["enabled"]) == ("dev-tenant", "720p24", False)
    assert zipfile.ZipFile(io.BytesIO(engine.jobs[jid]["package"])).read("lesson.csv") == CSV  # the stored package, byte for byte
    assert all(h.get("x-engine-key") == FakeEngine.KEY and h.get("x-correlation-id") for h in engine.seen_headers)

    engine.set(jid, "rendering", 60)
    s = client.get(f"/api/lesson-versions/{vid}/video").json()
    assert (s["job"]["state"], s["job"]["percent"], s["assets"]) == ("rendering", 60, [])
    engine.set(jid, "succeeded", 100)
    s = client.get(f"/api/lesson-versions/{vid}/video").json()
    assert s["job"]["state"] == "succeeded" and {a["kind"] for a in s["assets"]} == {"video", "render_config"}
    video = next(a for a in s["assets"] if a["kind"] == "video")
    assert (video["width"], video["height"], video["duration_seconds"]) == (1920, 1080, 12.5)
    dl = client.get(f"/api/video-jobs/{s['job']['id']}/download")
    assert dl.status_code == 200 and dl.content == FakeEngine.VIDEO
    assert hashlib.sha256(dl.content).hexdigest() == video["sha256"]
    assert client.get(f"/api/video-jobs/{s['job']['id']}/assets/{video['id']}").content == FakeEngine.VIDEO
    assert client.get(f"/api/lesson-versions/{vid}").json()["review_status"] == "approved"  # approval is independent of rendering


def test_duplicate_click_creates_one_job(client, engine):
    vid = approved_version(client)
    first, second = gen(client, vid), gen(client, vid)
    assert first.json()["job"]["id"] == second.json()["job"]["id"]
    assert second.json()["idempotent_replay"] is True and engine.submits == 1


def test_engine_down_at_submit_then_retry(client, engine):
    vid = approved_version(client)
    engine.down = True
    r = gen(client, vid)
    job = r.json()["job"]
    assert (job["state"], job["error_code"], job["retryable"]) == ("failed", "engine_unavailable", True)
    assert "not reachable" in job["error_message"] and "engine.test" not in json.dumps(r.json())
    engine.down = False
    r = client.post(f"/api/video-jobs/{job['id']}/retry", headers=PROD)
    assert r.json()["job"]["state"] == "queued" and engine.submits == 1


def test_engine_rejects_the_package(client, engine):
    vid = approved_version(client)
    engine.reject = (422, "invalid_package", "lesson.csv has invalid rows.")
    job = gen(client, vid).json()["job"]
    assert (job["state"], job["error_code"], job["retryable"]) == ("failed", "invalid_package", False)
    assert client.post(f"/api/video-jobs/{job['id']}/retry", headers=PROD).status_code == 409


def test_engine_failure_is_shown_and_retried(client, engine):
    vid = approved_version(client)
    gen(client, vid)
    jid = engine.only_job()
    engine.set(jid, "failed", 30, retryable=True, error={"code": "tts_unavailable", "message": "Azure Speech service is temporarily unavailable."})
    job = client.get(f"/api/lesson-versions/{vid}/video").json()["job"]
    assert (job["state"], job["error_code"], job["retryable"]) == ("failed", "tts_unavailable", True)
    assert "voice service" in job["error_message"]
    r = client.post(f"/api/video-jobs/{job['id']}/retry", headers=PROD)
    assert r.json()["job"]["state"] == "queued" and engine.jobs[jid]["state"] == "queued"


def test_corrupted_download_fails_integrity_then_recovers(client, engine):
    vid = approved_version(client)
    gen(client, vid)
    jid = engine.only_job()
    engine.corrupt_download = True
    engine.set(jid, "succeeded", 100)
    job = client.get(f"/api/lesson-versions/{vid}/video").json()["job"]
    assert (job["state"], job["error_code"]) == ("failed", "asset_corrupt")
    assert client.get(f"/api/video-jobs/{job['id']}/download").status_code == 404
    engine.corrupt_download = False
    r = client.post(f"/api/video-jobs/{job['id']}/retry", headers=PROD)
    assert r.json()["job"]["state"] == "succeeded" and len(r.json()["assets"]) == 2


def test_engine_outage_while_polling_keeps_the_job(client, engine):
    vid = approved_version(client)
    gen(client, vid)
    engine.set(engine.only_job(), "rendering", 40)
    client.get(f"/api/lesson-versions/{vid}/video")
    engine.down = True
    job = client.get(f"/api/lesson-versions/{vid}/video").json()["job"]
    assert (job["state"], job["percent"]) == ("rendering", 40)


def test_cancel(client, engine):
    vid = approved_version(client)
    job = gen(client, vid).json()["job"]
    r = client.post(f"/api/video-jobs/{job['id']}/cancel", headers=PROD)
    assert r.json()["job"]["state"] == "cancelled" and r.json()["can_generate"] is True
    assert client.post(f"/api/video-jobs/{job['id']}/cancel", headers=PROD).status_code == 409


def test_one_active_job_per_version_and_rerender(client, engine):
    vid = approved_version(client)
    first = gen(client, vid).json()["job"]
    assert gen(client, vid, profile="720p24").status_code == 409  # different settings, still busy
    engine.set(engine.only_job(), "succeeded", 100)
    client.get(f"/api/lesson-versions/{vid}/video")
    again = gen(client, vid).json()
    assert again["idempotent_replay"] is True and again["job"]["id"] == first["id"]  # same request after success: same job
    new = gen(client, vid, rerender=True).json()
    assert new["idempotent_replay"] is False and new["job"]["id"] != first["id"] and engine.submits == 2
    assert [h["id"] for h in new["history"]] == [first["id"]]


def test_colab_manual_audio_flow(client, engine):
    vid = approved_version(client)
    job = gen(client, vid, provider="colab").json()["job"]
    assert job["state"] == "awaiting_audio" and job["awaiting_audio"] is True
    batch = client.get(f"/api/video-jobs/{job['id']}/narration-batch").json()
    assert batch["slides"][0]["slide"] == 1
    up = lambda data: client.post(f"/api/video-jobs/{job['id']}/audio", files={"audio": ("a.zip", data, "application/zip")}, headers=PROD)
    bad = up(b"bad")
    assert bad.status_code == 422 and bad.json()["detail"]["issues"][0]["code"] == "invalid_audio"
    assert up(b"good").json()["job"]["state"] == "queued"
    assert up(b"good").status_code == 409


def test_job_survives_an_application_restart(client, engine):
    vid = approved_version(client)
    jid = gen(client, vid).json()["job"]["id"]
    engine.set(engine.only_job(), "rendering", 55)
    with make_client(engine) as restarted:  # a brand new application instance on the same database
        job = restarted.get(f"/api/lesson-versions/{vid}/video").json()["job"]
        assert (job["id"], job["state"], job["percent"]) == (jid, "rendering", 55)


def test_tenant_isolation(client, engine):
    a, b = as_tenant("tenant-a"), as_tenant("tenant-b")
    vid = approved_version(client, a)
    job = gen(client, vid, a).json()["job"]
    engine.set(engine.only_job(), "succeeded", 100)
    client.get(f"/api/lesson-versions/{vid}/video", headers=a)
    assert client.get(f"/api/lesson-versions/{vid}/video", headers=b).status_code == 404
    assert gen(client, vid, b).status_code == 404
    for path in ("download", "narration-batch"):
        assert client.get(f"/api/video-jobs/{job['id']}/{path}", headers=b).status_code == 404
    assert client.post(f"/api/video-jobs/{job['id']}/cancel", headers={**b, **PROD}).status_code == 404
    assert engine.jobs[engine.only_job()]["manifest"]["caller"]["tenant_ref"] == "tenant-a"


def test_engine_forgets_the_job(client, engine):
    vid = approved_version(client)
    gen(client, vid)
    engine.jobs.clear()
    job = client.get(f"/api/lesson-versions/{vid}/video").json()["job"]
    assert (job["state"], job["error_code"]) == ("failed", "engine_job_missing")


def test_capabilities_proxy_and_unconfigured_engine(client):
    caps = client.get("/api/video/capabilities").json()
    assert caps["languages"] == ["en-IN", "hi-IN", "mr-IN"] and "colab" in [p["name"] for p in caps["providers"]]
    with TestClient(create_app(make_settings())) as unconfigured:  # no engine URL or key
        assert unconfigured.get("/api/video/capabilities").status_code == 503
        vid = approved_version(unconfigured)
        job = gen(unconfigured, vid).json()["job"]
        assert (job["state"], job["error_code"]) == ("failed", "engine_unavailable")


def test_wrong_engine_key_is_not_leaked(engine):
    settings = make_settings(video_engine_url="http://engine.test", video_engine_api_key="wrong-key")
    with TestClient(create_app(settings, engine_http=engine.http)) as c:
        vid = approved_version(c)
        r = gen(c, vid)
        assert "wrong-key" not in r.text and FakeEngine.KEY not in r.text
        assert r.json()["job"]["state"] == "failed"
