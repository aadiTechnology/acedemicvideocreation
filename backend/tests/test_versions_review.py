import io
import json
import os
import zipfile

from tests.conftest import as_tenant

HEADER = "Slide,Module,voice_text,subtitle_text,visual_instruction\n"
CSV = (HEADER + "1,Intro,Plants make food using sunlight and water.,Plants make food.,Show a leaf\n"
       "2,Process,Chlorophyll captures light energy in the leaf.,Chlorophyll captures light.,Show a chloroplast\n").encode()
OP = {"X-Dev-Roles": "content_operator"}
REVIEWER = {"X-Dev-Roles": "reviewer", "X-Dev-User": "rev-1"}


def post(client, path, body, headers=None):
    r = client.post(path, json=body, headers=headers or {})
    assert r.status_code == 201, r.text
    return r.json()


def setup(client, headers=None, languages=("en-IN",)):
    c = post(client, "/api/classes", {"name": "Class 7"}, headers)
    s = post(client, "/api/subjects", {"class_id": c["id"], "name": "Science"}, headers)
    ch = post(client, "/api/chapters", {"subject_id": s["id"], "number": 1, "title": "Nutrition in Plants"}, headers)
    t = post(client, "/api/topics", {"chapter_id": ch["id"], "title": "Photosynthesis"}, headers)
    lesson = post(client, "/api/lessons", {"topic_id": t["id"], "title": "How plants make food", "expected_duration_minutes": 1,
                                           "learning_objectives": ["Explain photosynthesis"], "languages": list(languages)}, headers)
    return lesson, lesson["versions"][0]["id"]


def zip_of(entries: dict) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for k, v in entries.items():
            zf.writestr(k, v)
    return out.getvalue()


def do_import(client, vid, files, headers=None, params=None):
    return client.post(f"/api/lesson-versions/{vid}/import", files=[("files", f) for f in files], headers=headers or {}, params=params or {})


def test_import_stores_package_and_normalized_slides(client):
    _, vid = setup(client)
    r = do_import(client, vid, [("lesson.csv", CSV, "text/csv"), ("lesson_plan.json", json.dumps({"quiz": [{"question": "Why?"}]}), "application/json")])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slides"] == 2 and body["review_status"] == "draft" and len(body["package_sha256"]) == 64
    d = client.get(f"/api/lesson-versions/{vid}").json()
    assert d["has_content"] and [s["module"] for s in d["slides"]] == ["Intro", "Process"] and d["quiz"][0]["question"] == "Why?"
    pkg = client.get(f"/api/lesson-versions/{vid}/package")
    with zipfile.ZipFile(io.BytesIO(pkg.content)) as zf:
        assert zf.read("lesson.csv") == CSV


def test_invalid_import_changes_nothing_and_lists_issues(client):
    _, vid = setup(client)
    assert do_import(client, vid, [("lesson.csv", CSV, "text/csv")]).status_code == 200
    bad = HEADER + ",Intro,v,s,vi\n"
    r = do_import(client, vid, [("lesson.csv", bad.encode(), "text/csv")])
    assert r.status_code == 422
    issues = r.json()["detail"]["issues"]
    assert issues[0]["code"] == "empty_slide_id" and issues[0]["row"] == 2
    assert len(client.get(f"/api/lesson-versions/{vid}").json()["slides"]) == 2  # previous content kept


def test_dry_run_does_not_store(client):
    _, vid = setup(client)
    r = do_import(client, vid, [("lesson.csv", CSV, "text/csv")], params={"dry_run": "true"})
    assert r.json()["dry_run"] is True and r.json()["slides"] == 2
    assert client.get(f"/api/lesson-versions/{vid}").json()["has_content"] is False


def test_zip_with_traversal_is_rejected_via_api(client):
    _, vid = setup(client)
    r = do_import(client, vid, [("p.zip", zip_of({"lesson.csv": CSV, "../x": b"x"}), "application/zip")])
    assert r.status_code == 422 and "unsafe_path" in [i["code"] for i in r.json()["detail"]["issues"]]


def test_full_review_flow_with_events(client):
    _, vid = setup(client)
    do_import(client, vid, [("lesson.csv", CSV, "text/csv")])
    assert client.post(f"/api/lesson-versions/{vid}/review", json={"action": "submit"}, headers=OP).json()["review_status"] == "in_review"
    r = client.post(f"/api/lesson-versions/{vid}/review", json={"action": "request_changes", "note": "Fix slide 2"}, headers=REVIEWER).json()
    assert (r["review_status"], r["review_note"], r["reviewed_by"]) == ("changes_required", "Fix slide 2", "rev-1") and r["reviewed_at"]
    client.post(f"/api/lesson-versions/{vid}/review", json={"action": "submit"}, headers=OP)
    r = client.post(f"/api/lesson-versions/{vid}/review", json={"action": "approve", "note": "Good"}, headers=REVIEWER).json()
    assert r["review_status"] == "approved"
    assert [e["to"] for e in r["events"]] == ["in_review", "changes_required", "in_review", "approved"]


def test_cannot_submit_without_content_or_skip_states(client):
    _, vid = setup(client)
    assert client.post(f"/api/lesson-versions/{vid}/review", json={"action": "submit"}, headers=OP).status_code == 409
    assert client.post(f"/api/lesson-versions/{vid}/review", json={"action": "approve"}, headers=REVIEWER).status_code == 409
    assert client.post(f"/api/lesson-versions/{vid}/review", json={"action": "bogus"}, headers=OP).status_code == 422


def test_reject_and_request_changes_need_a_note(client):
    _, vid = setup(client)
    do_import(client, vid, [("lesson.csv", CSV, "text/csv")])
    client.post(f"/api/lesson-versions/{vid}/review", json={"action": "submit"}, headers=OP)
    assert client.post(f"/api/lesson-versions/{vid}/review", json={"action": "reject"}, headers=REVIEWER).status_code == 422
    r = client.post(f"/api/lesson-versions/{vid}/review", json={"action": "reject", "note": "Wrong topic"}, headers=REVIEWER)
    assert r.json()["review_status"] == "rejected"
    assert client.post(f"/api/lesson-versions/{vid}/review", json={"action": "reopen"}, headers=OP).json()["review_status"] == "draft"


def test_roles_are_enforced(client):
    _, vid = setup(client)
    assert do_import(client, vid, [("lesson.csv", CSV, "text/csv")], headers=REVIEWER).status_code == 403
    do_import(client, vid, [("lesson.csv", CSV, "text/csv")])
    assert client.post(f"/api/lesson-versions/{vid}/review", json={"action": "submit"}, headers=REVIEWER).status_code == 403
    client.post(f"/api/lesson-versions/{vid}/review", json={"action": "submit"}, headers=OP)
    assert client.post(f"/api/lesson-versions/{vid}/review", json={"action": "approve"}, headers=OP).status_code == 403
    assert client.post(f"/api/lesson-versions/{vid}/review", json={"action": "approve"}, headers={"X-Dev-Roles": "admin"}).status_code == 200


def test_reimport_invalidates_approval(client):
    _, vid = setup(client)
    do_import(client, vid, [("lesson.csv", CSV, "text/csv")])
    client.post(f"/api/lesson-versions/{vid}/review", json={"action": "submit"}, headers=OP)
    client.post(f"/api/lesson-versions/{vid}/review", json={"action": "approve"}, headers=REVIEWER)
    r = do_import(client, vid, [("lesson.csv", (CSV + b"3,End,Plants are producers of food.,End,Show a plant\n"), "text/csv")])
    assert r.json()["review_status"] == "draft"
    d = client.get(f"/api/lesson-versions/{vid}").json()
    assert d["review_status"] == "draft" and d["events"][-1]["action"] == "content_changed"


def test_review_queue_filter(client):
    _, vid = setup(client, languages=("en-IN", "hi-IN"))
    do_import(client, vid, [("lesson.csv", CSV, "text/csv")])
    client.post(f"/api/lesson-versions/{vid}/review", json={"action": "submit"}, headers=OP)
    queue = client.get("/api/lesson-versions", params={"status": "in_review"}).json()
    assert [q["id"] for q in queue] == [vid]


def test_prompt_spec_has_columns_language_and_duration(client):
    lesson, _ = setup(client, languages=("mr-IN",))
    vid = lesson["versions"][0]["id"]
    text = client.get(f"/api/lesson-versions/{vid}/prompt-spec").text
    assert "Slide,Module,voice_text,subtitle_text,visual_instruction" in text
    assert "Marathi" in text and "Class 7" in text and "Photosynthesis" in text and "mr-IN" in text and "130 words" in text


def test_versions_of_another_tenant_are_invisible(client):
    _, vid = setup(client, as_tenant("tenant-a"))
    b = as_tenant("tenant-b")
    assert client.get(f"/api/lesson-versions/{vid}", headers=b).status_code == 404
    assert client.get(f"/api/lesson-versions/{vid}/prompt-spec", headers=b).status_code == 404
    assert do_import(client, vid, [("lesson.csv", CSV, "text/csv")], headers=b).status_code == 404
    assert client.post(f"/api/lesson-versions/{vid}/review", json={"action": "submit"}, headers=b).status_code == 404
    assert client.get("/api/lesson-versions", headers=b).json() == []
