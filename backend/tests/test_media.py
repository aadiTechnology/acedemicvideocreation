"""E9 real-world media: photo, clip and before/after slides need source, licence and credit; files are added to the lesson package."""
import base64
import io
import json
import struct
import zipfile
import zlib

import pytest

from app import package
from tests.fake_engine import FakeEngine
from tests.test_slides import package_plan
from tests.test_video import OP, REVIEWER, approved_version, make_client

PHOTO = {"file": "media/leaf.png", "caption": "A leaf under a lens", "source": "https://commons.example.org/leaf", "licence": "CC BY", "credit": "A. Sharma"}


def png(colour=(200, 40, 40)) -> bytes:
    """A real 4x4 PNG of one colour (built by hand so the tests need no imaging library)."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(bytes([0]) + bytes(colour) * 4 for _ in range(4))
    signature = bytes.fromhex("89504e470d0a1a0a")
    return signature + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def mp4() -> bytes:
    return bytes([0, 0, 0, 24]) + b"ftypmp42" + bytes(40)


@pytest.fixture()
def engine():
    return FakeEngine()


@pytest.fixture()
def client(engine):
    with make_client(engine) as c:
        yield c


def add(client, vid, name, data, headers=OP):
    return client.post(f"/api/lesson-versions/{vid}/media", files={"file": (name, data)}, headers=headers)


def photo_slide(**over):
    return {"headline": "A real leaf", "bullets": ["Look at the veins"], "layout": "photo", "diagram": {"photo": {**PHOTO, **over}}}


# ---- the rules ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("change,word", [({"source": ""}, "source"), ({"credit": ""}, "credit"), ({"licence": "All rights reserved"}, "licence"),
                                          ({"licence": None}, "licence"), ({"file": "leaf.png"}, "file"), ({"file": "../x.png"}, "file"),
                                          ({"file": "media/x.gif"}, "file"), ({"file": "media/a/b.png"}, "file"), ({"file": "media\\x.png"}, "file")])
def test_an_incomplete_or_unsafe_reference_is_refused_with_a_reason(change, word):
    problem = package._diagram_problem({"layout": "photo", "diagram": {"photo": {**PHOTO, **change}}})
    assert problem and word in problem


def test_complete_references_are_accepted_for_every_media_layout():
    assert package._diagram_problem({"layout": "photo", "bullets": ["a"], "diagram": {"photo": PHOTO}}) is None
    assert package._diagram_problem({"layout": "clip", "diagram": {"clip": {**PHOTO, "file": "media/rain.mp4"}}}) is None
    pair = {"before": {**PHOTO, "file": "media/a.png"}, "after": {**PHOTO, "file": "media/b.jpg"}}
    assert package._diagram_problem({"layout": "before_after", "diagram": pair}) is None
    assert "after" in package._diagram_problem({"layout": "before_after", "diagram": {"before": pair["before"]}})
    assert "clip.file" in package._diagram_problem({"layout": "clip", "diagram": {"clip": PHOTO}})  # a picture is not a clip


def test_the_accepted_licences():
    assert package.LICENCES == ("CC0", "Public domain", "CC BY", "CC BY-SA", "Own work", "Permission granted")  # keep in step with the Video Engine (engine/media.py)


# ---- adding files -----------------------------------------------------------------------------------------------------
def test_adding_a_photo_stores_it_in_the_package_and_lists_it(client):
    vid = approved_version(client)
    r = add(client, vid, "Leaf Photo.PNG", png())
    assert r.status_code == 200, r.text
    assert (r.json()["file"], r.json()["kind"]) == ("media/leaf-photo.png", "image")
    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/lesson-versions/{vid}/package").content)) as zf:
        assert zf.read("assets/media/leaf-photo.png") == png()
    listed = client.get(f"/api/lesson-versions/{vid}/media").json()
    assert [(x["file"], x["used_by"]) for x in listed["items"]] == [("media/leaf-photo.png", [])]
    assert "CC BY" in listed["licences"]


def test_adding_a_clip_and_replacing_a_file_with_the_same_name(client):
    vid = approved_version(client)
    assert add(client, vid, "rain.mp4", mp4()).json()["kind"] == "clip"
    add(client, vid, "a.png", png((1, 2, 3)))
    add(client, vid, "a.png", png((9, 9, 9)))
    items = client.get(f"/api/lesson-versions/{vid}/media").json()["items"]
    assert sorted(x["file"] for x in items) == ["media/a.png", "media/rain.mp4"]
    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/lesson-versions/{vid}/package").content)) as zf:
        assert zf.read("assets/media/a.png") == png((9, 9, 9))


@pytest.mark.parametrize("name,data,word", [("x.gif", b"GIF89a", "PNG or JPEG"), ("x.png", b"not a png", "real PNG"), ("x.mp4", b"nope", "real MP4"),
                                             ("x.png", png() + b"0" * (5 * 1024 * 1024), "5 MB"), ("x.mp4", mp4() + b"0" * (20 * 1024 * 1024), "20 MB")])
def test_wrong_or_oversized_files_are_refused(client, name, data, word):
    vid = approved_version(client)
    before = client.get(f"/api/lesson-versions/{vid}").json()["package_sha256"]
    r = add(client, vid, name, data)
    assert r.status_code == 422 and word in r.json()["detail"]
    assert client.get(f"/api/lesson-versions/{vid}").json()["package_sha256"] == before


def test_only_content_operators_may_add_files_and_other_tenants_see_nothing(client):
    vid = approved_version(client)
    assert add(client, vid, "a.png", png(), REVIEWER).status_code == 403
    assert add(client, vid, "a.png", png(), {"X-Dev-Tenant": "other", **OP}).status_code == 404
    assert client.get(f"/api/lesson-versions/{vid}/media", headers={"X-Dev-Tenant": "other"}).status_code == 404


def test_adding_a_file_to_an_approved_version_cancels_the_approval(client):
    vid = approved_version(client)
    assert client.get(f"/api/lesson-versions/{vid}").json()["review_status"] == "approved"
    add(client, vid, "a.png", png())
    detail = client.get(f"/api/lesson-versions/{vid}").json()
    assert detail["review_status"] == "draft" and detail["events"][-1]["action"] == "content_changed"


# ---- slides that use media --------------------------------------------------------------------------------------------
def test_a_photo_slide_can_be_saved_once_its_file_is_in_the_lesson(client):
    vid = approved_version(client)
    refused = client.put(f"/api/lesson-versions/{vid}/slides/1", json=photo_slide(), headers=OP)
    assert refused.status_code == 422 and "not in the package" in json.dumps(refused.json())  # the file has not been added yet
    add(client, vid, "leaf.png", png())
    saved = client.put(f"/api/lesson-versions/{vid}/slides/1", json=photo_slide(), headers=OP)
    assert saved.status_code == 200, saved.text
    entry = next(s for s in package_plan(client, vid)["slides"] if s["slide"] == 1)
    assert (entry["layout"], entry["diagram"]["photo"]["credit"]) == ("photo", "A. Sharma")
    assert client.get(f"/api/lesson-versions/{vid}/media").json()["items"][0]["used_by"] == [1]


def test_a_photo_slide_without_a_licence_cannot_be_saved(client):
    vid = approved_version(client)
    add(client, vid, "leaf.png", png())
    r = client.put(f"/api/lesson-versions/{vid}/slides/1", json=photo_slide(licence="Stolen"), headers=OP)
    assert r.status_code == 422 and "licence" in json.dumps(r.json())


def test_preview_sends_the_photos_the_slide_uses_but_not_clips(client, engine):
    vid = approved_version(client)
    add(client, vid, "leaf.png", png())
    add(client, vid, "rain.mp4", mp4())
    r = client.post(f"/api/lesson-versions/{vid}/slides/1/preview", json={"plan": photo_slide(), "at": 0.9})
    assert r.status_code == 200, r.text
    media = engine.previews[-1]["media"]
    assert list(media) == ["media/leaf.png"] and base64.b64decode(media["media/leaf.png"]) == png()
    clip = {"headline": "Rain", "layout": "clip", "diagram": {"clip": {**PHOTO, "file": "media/rain.mp4"}}}
    client.post(f"/api/lesson-versions/{vid}/slides/1/preview", json={"plan": clip})
    assert engine.previews[-1]["media"] == {}


def test_the_chatgpt_prompt_asks_for_media_ideas_not_media(client):
    vid = approved_version(client)
    text = client.get(f"/api/lesson-versions/{vid}/prompt-spec").text
    assert "media_ideas" in text and "do NOT use these layouts yourself" in text


# ---- importing a package that has media ---------------------------------------------------------------------------------
def build_zip(plan_slides, files):
    from tests.test_versions_review import CSV
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("lesson.csv", CSV)
        zf.writestr("lesson_plan.json", json.dumps({"slides": plan_slides}))
        for name, data in files.items():
            zf.writestr(name, data)
    return out.getvalue()


def test_a_package_with_media_imports_and_a_missing_or_oversized_file_is_refused():
    slide = {"slide": 1, "headline": "Leaf", "bullets": ["a"], "layout": "photo", "diagram": {"photo": PHOTO}}
    ok = package.parse_upload([("p.zip", build_zip([slide], {"assets/media/leaf.png": png()}))], "en-IN", {})
    assert ok.slides
    with pytest.raises(package.ImportRejected) as missing:
        package.parse_upload([("p.zip", build_zip([slide], {}))], "en-IN", {})
    assert any(i.code == "media_missing" for i in missing.value.issues)
    with pytest.raises(package.ImportRejected) as big:
        package.parse_upload([("p.zip", build_zip([slide], {"assets/media/leaf.png": png() + b"0" * (5 * 1024 * 1024)}))], "en-IN", {})
    assert any(i.code == "media_too_large" for i in big.value.issues)
    with pytest.raises(package.ImportRejected) as other:
        package.parse_upload([("p.zip", build_zip([], {"assets/media/leaf.gif": b"x"}))], "en-IN", {})
    assert any(i.code == "unexpected_file" for i in other.value.issues)
