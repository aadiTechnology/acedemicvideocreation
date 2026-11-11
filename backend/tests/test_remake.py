"""Making a finished video again in another size or theme from its lesson bundle (the re-render screen's API)."""
import pytest

from tests.fake_engine import FakeEngine
from tests.test_video import PROD, approved_version, gen, make_client

BUNDLE = b"PK-fake-lesson-bundle"


@pytest.fixture()
def engine():
    e = FakeEngine()
    e.bundle = BUNDLE
    return e


@pytest.fixture()
def client(engine):
    with make_client(engine) as c:
        yield c


def finished(client, engine, vid):
    assert gen(client, vid, profile="480p24").status_code == 202
    engine.set(engine.only_job(), "succeeded", 100)
    summary = client.get(f"/api/lesson-versions/{vid}/video").json()
    assert summary["job"]["state"] == "succeeded"
    return summary["job"]["id"], summary


def remake(client, job_id, headers=PROD, **body):
    return client.post(f"/api/video-jobs/{job_id}/remake", json=body, headers=headers)


def test_the_bundle_is_collected_with_the_video_and_listed(client, engine):
    vid = approved_version(client)
    _, summary = finished(client, engine, vid)
    assert "lesson_bundle" in {a["kind"] for a in summary["assets"]}


def test_a_video_can_be_made_again_from_its_bundle_in_another_size_and_theme(client, engine):
    vid = approved_version(client)
    job_id, _ = finished(client, engine, vid)
    r = remake(client, job_id, profile="720p24", theme="high_contrast", subtitles=False)
    assert r.status_code == 202, r.text
    assert len(engine.jobs) == 2 and engine.submits == 2
    new = [j for k, j in engine.jobs.items() if j["key"].startswith("lv-remake-")][0]
    assert new["package"] == BUNDLE  # the bundle is what is sent, not the lesson package
    assert new["manifest"]["render"] == {"profile": "720p24", "style": "animated", "subtitles": {"enabled": False}, "theme": "high_contrast"}
    assert r.json()["job"]["settings"]["from_job"] == job_id and r.json()["job"]["state"] in ("queued", "submitting")


def test_the_dark_theme_is_not_sent_so_an_older_engine_still_accepts_it(client, engine):
    vid = approved_version(client)
    job_id, _ = finished(client, engine, vid)
    remake(client, job_id, profile="1080p24")
    new = [j for j in engine.jobs.values() if j["key"].startswith("lv-remake-")][0]
    assert "theme" not in new["manifest"]["render"]


def test_the_voice_of_the_original_is_kept(client, engine):
    vid = approved_version(client)
    job_id, _ = finished(client, engine, vid)
    remake(client, job_id, theme="high_contrast")
    new = [j for j in engine.jobs.values() if j["key"].startswith("lv-remake-")][0]
    assert new["manifest"]["tts"]["provider"] == "azure"


def test_unknown_choices_are_refused(client, engine):
    vid = approved_version(client)
    job_id, _ = finished(client, engine, vid)
    assert remake(client, job_id, profile="8k").status_code == 422
    assert remake(client, job_id, theme="neon").status_code == 422
    assert engine.submits == 1


def test_a_video_made_before_bundles_existed_cannot_be_made_again(client, engine):
    engine.bundle = None
    vid = approved_version(client)
    job_id, _ = finished(client, engine, vid)
    r = remake(client, job_id)
    assert r.status_code == 409 and "no lesson bundle" in r.json()["detail"]


def test_only_a_finished_video_and_one_at_a_time(client, engine):
    vid = approved_version(client)
    assert gen(client, vid, profile="480p24").status_code == 202
    running = client.get(f"/api/lesson-versions/{vid}/video").json()["job"]["id"]
    assert remake(client, running).status_code == 409  # still being made
    engine.set(engine.only_job(), "succeeded", 100)
    client.get(f"/api/lesson-versions/{vid}/video")
    assert remake(client, running).status_code == 202
    assert remake(client, running).status_code == 409  # the first remake is still running


def test_other_companies_and_people_without_the_permission_cannot_remake(client, engine):
    vid = approved_version(client)
    job_id, _ = finished(client, engine, vid)
    assert remake(client, job_id, headers={"X-Dev-Roles": "viewer"}).status_code == 403
    assert remake(client, job_id, headers={"X-Dev-Tenant": "other", **PROD}).status_code == 404


def test_the_engine_refusing_the_bundle_is_reported(client, engine):
    vid = approved_version(client)
    job_id, _ = finished(client, engine, vid)
    engine.reject = (422, "invalid_package", "The bundle is missing narration audio.")
    r = remake(client, job_id)
    assert r.status_code == 202 and r.json()["job"]["state"] == "failed" and "did not accept" in r.json()["job"]["error_message"]
