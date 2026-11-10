"""E11 assessment: rules, authoring, approval, practice feedback, export and the quiz from lesson_plan.json."""
import io
import json
import re
import struct
import zipfile
import zlib

import pytest

from app import assessment as A
from tests.fake_engine import FakeEngine
from tests.test_media import add, png
from tests.test_video import OP, REVIEWER, approved_version, make_client

LEARNER = {"X-Dev-Roles": "viewer", "X-Dev-User": "learner-1"}
MC = {"kind": "multiple_choice", "prompt": "What do plants make using sunlight?", "options": ["Food", "Plastic", "Metal"], "answer_index": 0, "explanation": "Plants make food (glucose) by photosynthesis."}
CONCEPT = {"kind": "conceptual", "prompt": "Why do leaves look green?", "model_answer": "Chlorophyll reflects green light.", "explanation": "Chlorophyll absorbs red and blue light and reflects green."}


@pytest.fixture()
def engine():
    return FakeEngine()


@pytest.fixture()
def client(engine):
    with make_client(engine) as c:
        yield c


def base(vid):
    return f"/api/lesson-versions/{vid}/assessment"


def make(client, vid, body=MC, headers=OP):
    r = client.post(base(vid), json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# ---- the rules --------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("change,word", [({"kind": "essay"}, "kind"), ({"prompt": ""}, "question"), ({"explanation": ""}, "explanation"), ({"options": ["Only one"]}, "2 to 5"),
                                          ({"options": ["A", "B", "C", "D", "E", "F"]}, "2 to 5"), ({"options": ["Same", "same"]}, "same"), ({"answer_index": 9}, "correct"),
                                          ({"answer_index": None}, "correct"), ({"prompt": "x" * 401}, "400"),
                                          ({"image_file": "media/a.png"}, "Only image"), ({"slide": 99}, "slide")])
def test_a_bad_question_is_refused_with_a_reason(client, change, word):
    vid = approved_version(client)
    r = client.post(base(vid), json={**MC, **change}, headers=OP)
    assert r.status_code == 422 and word.lower() in r.json()["detail"].lower(), r.text
    assert client.get(base(vid), headers=OP).json()["questions"] == []


def test_a_conceptual_question_needs_a_model_answer_and_has_no_options(client):
    vid = approved_version(client)
    assert client.post(base(vid), json={**CONCEPT, "model_answer": ""}, headers=OP).status_code == 422
    q = make(client, vid, {**CONCEPT, "options": ["ignored"], "answer_index": 3})
    assert (q["options"], q["answer_index"], q["model_answer"]) == ([], None, "Chlorophyll reflects green light.")


def test_picture_questions_need_a_picture_from_the_lesson(client):
    vid = approved_version(client)
    body = {**MC, "kind": "image"}
    assert "needs a picture" in client.post(base(vid), json=body, headers=OP).json()["detail"]
    assert "not in this lesson" in client.post(base(vid), json={**body, "image_file": "media/leaf.png"}, headers=OP).json()["detail"]
    add(client, vid, "leaf.png", png())
    q = make(client, vid, {**body, "image_file": "media/leaf.png"})
    assert (q["kind"], q["image_file"]) == ("image", "media/leaf.png")
    assert make(client, vid, {**body, "kind": "diagram", "image_file": "media/leaf.png"})["kind"] == "diagram"


def test_at_most_five_questions_a_version(client):
    vid = approved_version(client)
    for _ in range(5):
        make(client, vid)
    r = client.post(base(vid), json=MC, headers=OP)
    assert r.status_code == 409 and "at most 5" in r.json()["detail"]


# ---- authoring and approval -------------------------------------------------------------------------------------------
def test_authors_change_and_remove_questions_and_positions_stay_in_order(client):
    vid = approved_version(client)
    a, b, c = (make(client, vid, {**MC, "prompt": f"Question {i}"}) for i in range(3))
    assert [q["position"] for q in (a, b, c)] == [1, 2, 3]
    changed = client.put(f"{base(vid)}/{b['id']}", json={**MC, "prompt": "Changed"}, headers=OP).json()
    assert changed["prompt"] == "Changed"
    assert client.delete(f"{base(vid)}/{a['id']}", headers=OP).status_code == 204
    listed = client.get(base(vid), headers=OP).json()["questions"]
    assert [(q["prompt"], q["position"]) for q in listed] == [("Changed", 1), ("Question 2", 2)]
    assert client.put(f"{base(vid)}/nope", json=MC, headers=OP).status_code == 404


def test_only_reviewers_approve_and_changing_an_approved_question_makes_it_a_draft(client):
    vid = approved_version(client)
    q = make(client, vid)
    assert client.post(f"{base(vid)}/{q['id']}/approve", headers=OP).status_code == 403
    done = client.post(f"{base(vid)}/{q['id']}/approve", headers=REVIEWER).json()
    assert done["status"] == "approved" and done["approved_by"]
    assert client.put(f"{base(vid)}/{q['id']}", json={**MC, "prompt": "Edited"}, headers=OP).json()["status"] == "draft"
    client.post(f"{base(vid)}/{q['id']}/approve", headers=REVIEWER)
    assert client.post(f"{base(vid)}/{q['id']}/unapprove", headers=REVIEWER).json()["status"] == "draft"


def test_a_version_is_complete_with_three_approved_questions(client):
    vid = approved_version(client)
    ids = [make(client, vid)["id"] for _ in range(3)]
    assert client.get(base(vid), headers=OP).json()["summary"] == {"count": 3, "approved": 0, "complete": False, "max": 5, "min_complete": 3}
    for i in ids:
        client.post(f"{base(vid)}/{i}/approve", headers=REVIEWER)
    assert client.get(base(vid), headers=OP).json()["summary"]["complete"] is True


def test_learners_cannot_author_and_see_only_approved_questions_without_answers(client):
    vid = approved_version(client)
    draft, ok = make(client, vid), make(client, vid, {**MC, "prompt": "Approved one"})
    client.post(f"{base(vid)}/{ok['id']}/approve", headers=REVIEWER)
    assert client.post(base(vid), json=MC, headers=LEARNER).status_code == 403
    seen = client.get(base(vid), headers=LEARNER).json()
    assert [q["prompt"] for q in seen["questions"]] == ["Approved one"]
    assert not {"answer_index", "explanation", "model_answer"} & set(seen["questions"][0])
    assert client.post(f"{base(vid)}/{draft['id']}/answer", json={"choice": 0}, headers=LEARNER).status_code == 404  # a draft is not for learners


def test_other_companies_see_nothing(client):
    vid = approved_version(client)
    q = make(client, vid)
    other = {"X-Dev-Tenant": "other", **OP}
    assert client.get(base(vid), headers=other).status_code == 404
    assert client.post(f"{base(vid)}/{q['id']}/answer", json={"choice": 0}, headers=other).status_code == 404
    assert client.get(f"{base(vid)}/export.html", headers=other).status_code == 404


# ---- practice ---------------------------------------------------------------------------------------------------------
def test_an_answer_is_marked_at_once_with_the_explanation(client):
    vid = approved_version(client)
    q = make(client, vid)
    client.post(f"{base(vid)}/{q['id']}/approve", headers=REVIEWER)
    right = client.post(f"{base(vid)}/{q['id']}/answer", json={"choice": 0}, headers=LEARNER).json()
    wrong = client.post(f"{base(vid)}/{q['id']}/answer", json={"choice": 1}, headers=LEARNER).json()
    assert (right["correct"], right["correct_index"]) == (True, 0) and "photosynthesis" in right["explanation"]
    assert (wrong["correct"], wrong["correct_index"]) == (False, 0)
    assert client.post(f"{base(vid)}/{q['id']}/answer", json={"choice": 7}, headers=LEARNER).status_code == 422
    assert client.post(f"{base(vid)}/{q['id']}/answer", json={}, headers=LEARNER).status_code == 422


def test_a_conceptual_answer_shows_the_model_answer_and_is_not_marked(client):
    vid = approved_version(client)
    q = make(client, vid, CONCEPT)
    client.post(f"{base(vid)}/{q['id']}/approve", headers=REVIEWER)
    r = client.post(f"{base(vid)}/{q['id']}/answer", json={"text": "Because of chlorophyll"}, headers=LEARNER).json()
    assert r["correct"] is None and r["model_answer"] == "Chlorophyll reflects green light."
    assert client.post(f"{base(vid)}/{q['id']}/answer", json={"text": "  "}, headers=LEARNER).status_code == 422


def test_a_question_picture_is_served_only_while_the_question_is_available(client):
    vid = approved_version(client)
    add(client, vid, "leaf.png", png())
    q = make(client, vid, {**MC, "kind": "image", "image_file": "media/leaf.png"})
    url = f"{base(vid)}/picture/leaf.png"
    assert client.get(url, headers=LEARNER).status_code == 404  # a draft question's picture is not public
    assert client.get(url, headers=OP).content == png()
    client.post(f"{base(vid)}/{q['id']}/approve", headers=REVIEWER)
    r = client.get(url, headers=LEARNER)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get(f"{base(vid)}/picture/other.png", headers=LEARNER).status_code == 404


# ---- export -------------------------------------------------------------------------------------------------------------
def test_the_export_is_one_page_with_approved_questions_only_and_no_external_links(client):
    vid = approved_version(client)
    assert client.get(f"{base(vid)}/export.html", headers=OP).status_code == 409  # nothing approved yet
    add(client, vid, "leaf.png", png())
    a = make(client, vid, {**MC, "kind": "image", "image_file": "media/leaf.png", "prompt": "Name </script><script>alert(1)</script> this"})
    make(client, vid, {**MC, "prompt": "Still a draft"})
    client.post(f"{base(vid)}/{a['id']}/approve", headers=REVIEWER)
    r = client.get(f"{base(vid)}/export.html", headers=LEARNER)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    page = r.text
    assert "Still a draft" not in page and "data:image/png;base64," in page
    assert "</script><script>alert(1)" not in page  # a question cannot close the page script and inject its own
    assert page.count("<script>") == 1
    assert not re.search(r"(src|href)=[\"']https?://", page) and "fetch(" not in page


# ---- from the ChatGPT quiz ------------------------------------------------------------------------------------------------
def test_the_quiz_in_lesson_plan_json_becomes_draft_questions():
    items = A.from_plan_quiz([{"question": "Why?", "options": ["A", "B"], "answer": "B", "explanation": "Because"},
                              {"question": "Explain.", "answer": "Because it is so"}, {"question": "Bad", "options": ["A", "B"], "answer": "C"}, "nonsense"])
    drafts = [i["draft"] for i in items if "draft" in i]
    assert [(d["kind"], d.get("answer_index")) for d in drafts] == [("multiple_choice", 1), ("conceptual", None)]
    assert len([i for i in items if "skipped" in i]) == 2


def test_importing_the_plan_quiz_creates_drafts_and_respects_the_limit(client):
    vid = approved_version(client)
    plan = {"quiz": [{"question": f"Q{i}?", "options": ["A", "B"], "answer": "A", "explanation": "E"} for i in range(7)]}
    from tests.test_versions_review import CSV
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("lesson.csv", CSV)
        zf.writestr("lesson_plan.json", json.dumps(plan))
    assert client.post(f"/api/lesson-versions/{vid}/import", files=[("files", ("p.zip", out.getvalue(), "application/zip"))], headers=OP).status_code == 200
    r = client.post(f"{base(vid)}/from-plan", headers=OP).json()
    assert len(r["created"]) == 5 and all(q["status"] == "draft" for q in r["created"]) and r["skipped"]
    assert client.post(f"{base(vid)}/from-plan", headers=OP).json()["created"] == []  # no room left


def test_the_prompt_asks_for_three_to_five_questions_with_explanations(client):
    vid = approved_version(client)
    text = client.get(f"/api/lesson-versions/{vid}/prompt-spec").text
    assert "3 to 5 practice questions" in text and '"explanation"' in text
