"""Videos in object storage (Backblaze B2): upload after verification, signed links, failures, mixed old and new files."""
import hashlib
import os

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.storage import B2Store, StorageError
from tests.conftest import make_settings
from tests.fake_engine import FakeEngine
from tests.test_video import PROD, approved_version


class FakeStore:
    """What the app needs from a store, held in memory."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.fail_put = False

    def put_file(self, key, path, content_type):
        if self.fail_put:
            raise StorageError("down")
        self.objects[key] = open(path, "rb").read()

    def url(self, key, filename, content_type, download):
        return f"https://b2.example/{key}?name={filename}&dl={int(download)}&sig=abc"

    def exists(self, key):
        return key in self.objects

    def delete(self, key):
        self.objects.pop(key, None)


@pytest.fixture()
def engine():
    return FakeEngine()


@pytest.fixture()
def store():
    return FakeStore()


def make_client(engine, store):
    settings = make_settings(video_engine_url="http://engine.test", video_engine_api_key=FakeEngine.KEY)
    return TestClient(create_app(settings, engine_http=engine.http, object_store=store), follow_redirects=False)


def run_to_success(client, engine, vid):
    assert client.post(f"/api/lesson-versions/{vid}/video", json={"provider": "azure", "subtitles": False}, headers=PROD).status_code == 202
    engine.set(engine.only_job(), "succeeded", 100)
    return client.get(f"/api/lesson-versions/{vid}/video").json()


def test_video_is_uploaded_local_copy_removed_and_served_by_signed_link(engine, store):
    with make_client(engine, store) as client:
        vid = approved_version(client)
        s = run_to_success(client, engine, vid)
        assert s["job"]["state"] == "succeeded"
        video = next(a for a in s["assets"] if a["kind"] == "video")
        key = f"videos/{vid}/{s['job']['id']}/video-final_video.mp4"
        assert store.objects[key] == FakeEngine.VIDEO
        assert hashlib.sha256(store.objects[key]).hexdigest() == video["sha256"]
        root = client.app.state.settings.storage_dir
        leftovers = [f for _, _, files in os.walk(os.path.join(root, "videos")) for f in files] if os.path.isdir(os.path.join(root, "videos")) else []
        assert leftovers == []  # nothing is kept on the local volume
        r = client.get(f"/api/video-jobs/{s['job']['id']}/download")
        assert r.status_code == 302 and r.headers["location"].startswith("https://b2.example/videos/") and "dl=0" in r.headers["location"]
        assert r.headers["cache-control"] == "no-store"
        r2 = client.get(f"/api/video-jobs/{s['job']['id']}/assets/{video['id']}")
        assert r2.status_code == 302 and "dl=1" in r2.headers["location"]


def test_upload_failure_fails_the_job_retryably_and_a_retry_recovers(engine, store):
    with make_client(engine, store) as client:
        vid = approved_version(client)
        store.fail_put = True
        s = run_to_success(client, engine, vid)
        assert (s["job"]["state"], s["job"]["error_code"], s["job"]["retryable"]) == ("failed", "storage_unavailable", True)
        assert "not reachable" in s["job"]["error_message"]
        assert client.get(f"/api/video-jobs/{s['job']['id']}/download").status_code == 404
        store.fail_put = False
        r = client.post(f"/api/video-jobs/{s['job']['id']}/retry", json={}, headers=PROD)
        assert r.json()["job"]["state"] == "succeeded" and len(r.json()["assets"]) == 2 and len(store.objects) == 2
        assert engine.submits == 1  # collecting again did not render again


def test_missing_object_is_not_available(engine, store):
    with make_client(engine, store) as client:
        vid = approved_version(client)
        s = run_to_success(client, engine, vid)
        store.objects.clear()
        assert client.get(f"/api/video-jobs/{s['job']['id']}/download").status_code == 404


def test_other_tenants_cannot_use_signed_links(engine, store):
    with make_client(engine, store) as client:
        vid = approved_version(client)
        s = run_to_success(client, engine, vid)
        assert client.get(f"/api/video-jobs/{s['job']['id']}/download", headers={"X-Dev-Tenant": "other"}).status_code == 404


def test_without_a_store_files_stay_local(engine):
    settings = make_settings(video_engine_url="http://engine.test", video_engine_api_key=FakeEngine.KEY)
    with TestClient(create_app(settings, engine_http=engine.http)) as client:
        vid = approved_version(client)
        s = run_to_success(client, engine, vid)
        assert client.get(f"/api/video-jobs/{s['job']['id']}/download").content == FakeEngine.VIDEO


def test_b2_store_calls_the_s3_api_correctly(tmp_path):
    calls = []

    class Client:
        def upload_file(self, *a, **k):
            calls.append(("upload", a, k))

        def generate_presigned_url(self, op, **k):
            calls.append((op, k))
            return "https://signed"

        def head_object(self, **k):
            if k["Key"] == "missing":
                raise RuntimeError("404")

        def delete_object(self, **k):
            calls.append(("delete", k))

    st = B2Store("bkt", 600, Client())
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x")
    st.put_file("videos/a/b/video-v.mp4", f, "video/mp4")
    assert calls[0][1] == (str(f), "bkt", "videos/a/b/video-v.mp4") and calls[0][2]["ExtraArgs"] == {"ContentType": "video/mp4"}
    assert st.url("k", "my.mp4", "video/mp4", True) == "https://signed"
    p = calls[1][1]
    assert p["ExpiresIn"] == 600 and p["Params"]["Bucket"] == "bkt" and p["Params"]["ResponseContentDisposition"].startswith("attachment")
    assert st.exists("k") and not st.exists("missing")
    st.delete("k")
    assert calls[-1] == ("delete", {"Bucket": "bkt", "Key": "k"})

    class Boom(Client):
        def upload_file(self, *a, **k):
            raise RuntimeError("secret-key-leak")

    with pytest.raises(StorageError) as ei:
        B2Store("bkt", 1, Boom()).put_file("k", f, "video/mp4")
    assert "secret" not in str(ei.value)


def test_settings_validate_the_provider():
    from app.config import load_settings
    base = {"APP_ENV": "development", "AUTH_MODE": "dev", "DATABASE_URL": "postgresql://x/y"}
    assert load_settings({**base}).storage_provider == "local"
    with pytest.raises(RuntimeError):
        load_settings({**base, "STORAGE_PROVIDER": "ftp"})
    with pytest.raises(RuntimeError):
        load_settings({**base, "STORAGE_PROVIDER": "b2", "B2_BUCKET": "only"})
    ok = load_settings({**base, "STORAGE_PROVIDER": "b2", "B2_ENDPOINT": "s3.us-west-004.backblazeb2.com", "B2_KEY_ID": "k", "B2_APPLICATION_KEY": "s", "B2_BUCKET": "b"})
    assert ok.storage_provider == "b2" and ok.b2_url_expiry == 900


def test_existing_local_videos_can_be_moved_and_the_move_is_repeatable(engine, store):
    from app import db as database
    from app.tools.move_to_b2 import move
    settings = make_settings(video_engine_url="http://engine.test", video_engine_api_key=FakeEngine.KEY)
    with TestClient(create_app(settings, engine_http=engine.http), follow_redirects=False) as client:  # a store-less app: files stay local
        vid = approved_version(client)
        s = run_to_success(client, engine, vid)
        jid = s["job"]["id"]
        assert client.get(f"/api/video-jobs/{jid}/download").status_code == 200
        gen = database.get_db()
        session = next(gen)
        dry = move(store, session, dry_run=True)
        assert (dry["moved"], store.objects) == (2, {}) and dry["bytes"] > 0
        done = move(store, session)
        assert (done["moved"], done["failed"], len(store.objects)) == (2, 0, 2)
        again = move(store, session)
        assert (again["moved"], again["skipped_remote"]) == (0, 2)
        gen.close()
        client.app.state.store = store  # the same app, now with the bucket configured
        r = client.get(f"/api/video-jobs/{jid}/download")
        assert r.status_code == 302 and "b2.example" in r.headers["location"]
