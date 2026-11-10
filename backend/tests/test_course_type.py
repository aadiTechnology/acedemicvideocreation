"""Technical courses next to school classes: course type, labels in the prompt, the code layout, recommendation context."""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings
from tests.fake_engine import FakeEngine
from tests.test_package_validation import ROW, codes, csv_bytes, ok
from tests.test_versions_review import CSV, OP, do_import, post

TECH = {"X-Dev-Roles": "admin"}


@pytest.fixture()
def engine():
    return FakeEngine()


@pytest.fixture()
def client(engine):
    settings = make_settings(video_engine_url="http://engine.test", video_engine_api_key=FakeEngine.KEY)
    with TestClient(create_app(settings, engine_http=engine.http)) as c:
        yield c


def course_lesson(client, course_type="technical", name="Python for Beginners"):
    c = post(client, "/api/classes", {"name": name, "course_type": course_type})
    s = post(client, "/api/subjects", {"class_id": c["id"], "name": "Python Basics"})
    ch = post(client, "/api/chapters", {"subject_id": s["id"], "number": 2, "title": "Loops"})
    t = post(client, "/api/topics", {"chapter_id": ch["id"], "title": "The for loop"})
    lesson = post(client, "/api/lessons", {"topic_id": t["id"], "title": "Looping over a list", "expected_duration_minutes": 4,
                                           "learning_objectives": ["Write a for loop"], "languages": ["en-IN"]})
    return c, lesson, lesson["versions"][0]["id"]


def test_course_type_defaults_to_school_and_is_stored_and_listed(client):
    school = post(client, "/api/classes", {"name": "Class 7"})
    assert school["course_type"] == "school"
    course, lesson, _ = course_lesson(client)
    assert course["course_type"] == "technical"
    assert {c["name"]: c["course_type"] for c in client.get("/api/classes").json()} == {"Class 7": "school", "Python for Beginners": "technical"}
    row = client.get("/api/lessons").json()[0]
    assert (row["class_name"], row["course_type"]) == ("Python for Beginners", "technical")
    assert client.post("/api/classes", json={"name": "X", "course_type": "robotics"}).status_code == 422


def test_the_prompt_speaks_to_a_technical_course_and_a_school_class_differently(client):
    _, _, vid = course_lesson(client)
    p = client.get(f"/api/lesson-versions/{vid}/prompt-spec").text
    assert "technical course video" in p and "Course: Python for Beginners" in p and "Module 2: Loops" in p
    assert "complete, runnable and idiomatic" in p and 'explain code with the "code" layout' in p
    assert "Class: " not in p and "Scientifically correct" not in p
    _, _, svid = course_lesson(client, "school", "Class 8")
    sp = client.get(f"/api/lesson-versions/{svid}/prompt-spec").text
    assert "teaching video for Class 8 students" in sp and "Scientifically correct" in sp and "technical course" not in sp
    for text in (p, sp):  # both explain the code layout and ask for fully quoted CSV cells
        assert '"layout": "code"' in text and "Put EVERY text cell in double quotes" in text


def code_slide(**over):
    d = {"language": "python", "code": "total = 0\nfor n in [1, 2, 3]:\n    total += n\nprint(total)",
         "steps": [{"lines": [1], "vars": {"total": "0"}}, {"lines": [2, 3], "vars": {"n": "1", "total": "1"}}, {"lines": [4], "output": "6"}]}
    d.update(over)
    return ("lesson_plan.json", json.dumps({"slides": [{"slide": 1, "headline": "A loop", "layout": "code", "diagram": d}]}).encode())


def test_the_code_layout_is_validated():
    base = [("lesson.csv", csv_bytes([ROW]))]
    assert ok(base + [code_slide()]).lesson_plan["slides"][0]["layout"] == "code"
    plain = json.dumps({"slides": [{"slide": 1, "headline": "A", "layout": "code", "diagram": {"code": "x = 1"}}]}).encode()
    assert ok(base + [("lesson_plan.json", plain)])  # steps are optional
    bad = [{"code": ""}, {"code": "x\n" * 19}, {"code": "x" * 81}, {"language": "cobol"}, {"steps": []}, {"steps": [{"lines": [99]}]},
           {"steps": [{"lines": [1], "output": "y" * 201}]}, {"steps": [{"lines": [1], "vars": {f"v{i}": 1 for i in range(7)}}]}, {"steps": ["no"]},
           {"steps": [{"lines": [1]}] * 13}]
    for diagram_change in bad:
        assert "plan_diagram" in codes(base + [code_slide(**diagram_change)]), diagram_change


def test_recommendation_carries_the_course_type(client, engine):
    _, lesson, vid = course_lesson(client)
    assert do_import(client, vid, [("lesson.csv", CSV, "text/csv")], headers=OP).status_code == 200
    client.post(f"/api/lesson-versions/{vid}/slides/1/recommend")
    assert engine.recommends[-1]["course_type"] == "technical"
    assert engine.recommends[-1]["class_name"] == "Python for Beginners"


def test_existing_classes_become_school_in_the_migration():
    from sqlalchemy import create_engine, text

    from tests.conftest import TEST_URL
    eng = create_engine(TEST_URL)
    with eng.connect() as c:
        col = c.execute(text("SELECT column_default, is_nullable FROM information_schema.columns WHERE table_name='school_classes' AND column_name='course_type'")).one()
    assert "school" in col[0] and col[1] == "NO"
