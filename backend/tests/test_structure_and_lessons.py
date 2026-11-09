import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import as_tenant, make_settings


def mk(client, path, body, headers=None):
    r = client.post(path, json=body, headers=headers or {})
    assert r.status_code == 201, r.text
    return r.json()


def tree(client, headers=None, cname="Class 7"):
    c = mk(client, "/api/classes", {"name": cname}, headers)
    s = mk(client, "/api/subjects", {"class_id": c["id"], "name": "Science"}, headers)
    ch = mk(client, "/api/chapters", {"subject_id": s["id"], "number": 1, "title": "Nutrition in Plants"}, headers)
    t = mk(client, "/api/topics", {"chapter_id": ch["id"], "title": "Photosynthesis"}, headers)
    return c, s, ch, t


def test_health_ready(client):
    assert client.get("/health").status_code == 200
    assert client.get("/ready").json() == {"status": "ready"}


def test_create_lesson_with_three_language_versions(client):
    _, _, _, t = tree(client)
    r = client.post("/api/lessons", json={
        "topic_id": t["id"], "title": "How plants make food", "learning_objectives": ["Explain photosynthesis"],
        "expected_duration_minutes": 5, "languages": ["en-IN", "hi-IN", "mr-IN", "en-IN"]})
    assert r.status_code == 201, r.text
    lesson = r.json()
    assert [v["language"] for v in lesson["versions"]] == ["en-IN", "hi-IN", "mr-IN"]
    assert all(v["review_status"] == "draft" and v["publication_status"] is None for v in lesson["versions"])
    ids = {lesson["id"], *[v["id"] for v in lesson["versions"]]}
    assert len(ids) == 4 and all(len(i) == 36 for i in ids)  # stable UUIDs


def test_lesson_list_shows_academic_path_and_filters(client):
    _, s, _, t = tree(client)
    mk(client, "/api/lessons", {"topic_id": t["id"], "title": "L1", "languages": ["hi-IN"]})
    mk(client, "/api/lessons", {"topic_id": t["id"], "title": "L2", "languages": ["en-IN"]})
    rows = client.get("/api/lessons").json()
    assert [r["title"] for r in rows] == ["L1", "L2"]
    assert rows[0]["class_name"] == "Class 7" and rows[0]["chapter_number"] == 1 and rows[0]["topic_title"] == "Photosynthesis"
    assert [r["title"] for r in client.get("/api/lessons", params={"language": "hi-IN"}).json()] == ["L1"]
    assert len(client.get("/api/lessons", params={"subject_id": s["id"]}).json()) == 2


def test_add_version_and_duplicate_language(client):
    _, _, _, t = tree(client)
    lesson = mk(client, "/api/lessons", {"topic_id": t["id"], "title": "L", "languages": ["en-IN"]})
    assert client.post(f"/api/lessons/{lesson['id']}/versions", json={"language": "mr-IN"}).status_code == 201
    dup = client.post(f"/api/lessons/{lesson['id']}/versions", json={"language": "mr-IN"})
    assert dup.status_code == 409
    assert client.post(f"/api/lessons/{lesson['id']}/versions", json={"language": "fr-FR"}).status_code == 422


def test_update_and_delete_lesson(client):
    _, _, _, t = tree(client)
    lesson = mk(client, "/api/lessons", {"topic_id": t["id"], "title": "Old", "languages": ["en-IN"]})
    r = client.patch(f"/api/lessons/{lesson['id']}", json={"title": "New", "expected_duration_minutes": 8})
    assert (r.json()["title"], r.json()["expected_duration_minutes"]) == ("New", 8)
    assert client.delete(f"/api/lessons/{lesson['id']}").status_code == 204
    assert client.get(f"/api/lessons/{lesson['id']}").status_code == 404


def test_structure_uniqueness_and_children_block_delete(client):
    c, s, ch, t = tree(client)
    assert client.post("/api/classes", json={"name": "Class 7"}).status_code == 409
    assert client.post("/api/chapters", json={"subject_id": s["id"], "number": 1, "title": "Dup"}).status_code == 409
    r = client.delete(f"/api/classes/{c['id']}")
    assert r.status_code == 409 and "below it" in r.json()["detail"]


def test_parent_must_exist(client):
    r = client.post("/api/subjects", json={"class_id": "00000000-0000-4000-8000-000000000000", "name": "X"})
    assert r.status_code == 404


def test_validation_errors(client):
    assert client.post("/api/classes", json={"name": ""}).status_code == 422
    _, _, _, t = tree(client)
    assert client.post("/api/lessons", json={"topic_id": t["id"], "title": "x", "expected_duration_minutes": 0}).status_code == 422


def test_tenants_are_isolated(client):
    a, b = as_tenant("tenant-a"), as_tenant("tenant-b")
    _, _, _, ta = tree(client, a)
    lesson = mk(client, "/api/lessons", {"topic_id": ta["id"], "title": "A lesson", "languages": ["en-IN"]}, a)
    assert client.get("/api/lessons", headers=b).json() == []
    assert client.get(f"/api/lessons/{lesson['id']}", headers=b).status_code == 404
    assert client.patch(f"/api/lessons/{lesson['id']}", json={"title": "x"}, headers=b).status_code == 404
    assert client.delete(f"/api/lessons/{lesson['id']}", headers=b).status_code == 404
    assert client.post(f"/api/lessons/{lesson['id']}/versions", json={"language": "hi-IN"}, headers=b).status_code == 404
    assert client.post("/api/lessons", json={"topic_id": ta["id"], "title": "x"}, headers=b).status_code == 404  # parent of another tenant
    assert client.get("/api/classes", headers=b).json() == []
    tree(client, b)  # tenant B can reuse the same class name


def test_dev_auth_refused_in_production():
    from app.config import load_settings
    with pytest.raises(RuntimeError):
        load_settings({"APP_ENV": "production", "AUTH_MODE": "dev"})


def test_not_signed_in_without_dev_mode():
    with TestClient(create_app(make_settings(auth_mode="oidc"))) as c:
        assert c.get("/api/lessons").status_code == 401
