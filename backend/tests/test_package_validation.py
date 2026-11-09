import csv
import io
import json
import zipfile

import pytest

from app import package
from app.package import CANONICAL_COLUMNS, ImportRejected, parse_upload

DEFAULTS = {"title": "Photosynthesis", "learning_objectives": ["Explain"], "source_references": [], "expected_duration_minutes": 1}
ROW = ["1", "Intro", "Plants make food using sunlight and water in their leaves every day.", "Plants make food.", "Show a leaf"]


def csv_bytes(rows, header=CANONICAL_COLUMNS, encoding="utf-8-sig") -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode(encoding)


def make_zip(entries: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name, data in entries.items():
            info = zipfile.ZipInfo("x")
            info.filename = name
            zf.writestr(info, data)
    return out.getvalue()


def codes(files, language="en-IN") -> list[str]:
    with pytest.raises(ImportRejected) as ctx:
        parse_upload(files, language, DEFAULTS)
    return [i.code for i in ctx.value.issues]


def ok(files, language="en-IN"):
    return parse_upload(files, language, DEFAULTS)


def test_valid_zip_normalizes_and_keeps_original_csv():
    raw = csv_bytes([ROW, ["2", "End", "Summary words " * 5, "Summary", "Show a plant"]])
    plan = json.dumps({"language": "en", "learning_objectives": ["Explain"], "quiz": [{"question": "Why?"}]}).encode()
    p = ok([("pkg.zip", make_zip({"lesson.csv": raw, "lesson_plan.json": plan}))])
    assert [s["slide"] for s in p.slides] == [1, 2] and p.slides[0]["module"] == "Intro"
    with zipfile.ZipFile(io.BytesIO(p.zip_bytes)) as zf:
        assert zf.read("lesson.csv") == raw  # original bytes untouched
        assert json.loads(zf.read("lesson_plan.json"))["quiz"][0]["question"] == "Why?"


def test_hash_is_deterministic():
    files = [("pkg.zip", make_zip({"lesson.csv": csv_bytes([ROW])}))]
    assert ok(files).sha256 == ok(files).sha256


def test_root_folder_in_zip_is_accepted():
    p = ok([("p.zip", make_zip({"lesson-package/lesson.csv": csv_bytes([ROW]), "lesson-package/assets/a.png": b"png"}))])
    with zipfile.ZipFile(io.BytesIO(p.zip_bytes)) as zf:
        assert set(zf.namelist()) == {"lesson.csv", "lesson_plan.json", "assets/a.png"}


def test_csv_only_and_json_upload_builds_package():
    p = ok([("lesson.csv", csv_bytes([ROW])), ("lesson_plan.json", b'{"title": "T"}')])
    assert p.lesson_plan == {"title": "T"} and len(p.slides) == 1


def test_generated_plan_when_missing_warns():
    p = ok([("lesson.csv", csv_bytes([ROW]))])
    assert p.lesson_plan["title"] == "Photosynthesis" and "no_plan" in [w.code for w in p.warnings]


def test_unicode_hindi_marathi_content_round_trips():
    row = ["1", "परिचय", "पौधे सूर्य के प्रकाश से अपना भोजन बनाते हैं।", "पौधे भोजन बनाते हैं।", "पत्ती दिखाएँ"]
    assert ok([("lesson.csv", csv_bytes([row]))], "hi-IN").slides[0]["module"] == "परिचय"


@pytest.mark.parametrize("header,expected", [
    (["Slide", "Module", "voice_text", "subtitle_text"], "missing_column"),
    (list(CANONICAL_COLUMNS) + ["notes"], "unexpected_column"),
    (list(CANONICAL_COLUMNS) + ["Slide"], "duplicate_column"),
])
def test_header_problems(header, expected):
    assert expected in codes([("lesson.csv", csv_bytes([], header))])


def test_row_problems_are_reported_together_with_rows():
    rows = [["", "m", "v", "s", "vi"], ["x", "m", "v", "s", "vi"], ["2", "m", "", "s", "vi"], ["3", "m", "v", "s", "vi"], ["3", "m", "v", "s", "vi"]]
    with pytest.raises(ImportRejected) as ctx:
        parse_upload([("lesson.csv", csv_bytes(rows))], "en-IN", DEFAULTS)
    found = {(i.code, i.row) for i in ctx.value.issues}
    assert {("empty_slide_id", 2), ("bad_slide_id", 3), ("empty_field", 4), ("duplicate_slide", 6)} <= found


def test_row_with_unquoted_comma_is_explained():
    raw = b"Slide,Module,voice_text,subtitle_text,visual_instruction\n1,Intro,Hello, world,Sub,Vis\n"
    assert "row_shape" in codes([("lesson.csv", raw)])


def test_wrong_encoding_is_explained():
    raw = csv_bytes([["1", "Intro", "caf\u00e9 text", "s", "v"]], encoding="cp1252")
    assert "encoding" in codes([("lesson.csv", raw)])


def test_empty_and_header_only_csv():
    assert "empty_csv" in codes([("lesson.csv", b"")])
    assert "no_slides" in codes([("lesson.csv", csv_bytes([]))])


@pytest.mark.parametrize("name", ["../evil.txt", "/abs.txt", "a\\b.txt", "C:/x.txt", "assets/../../x.png"])
def test_unsafe_archive_paths_rejected(name):
    assert "unsafe_path" in codes([("p.zip", make_zip({"lesson.csv": csv_bytes([ROW]), name: b"x"}))])


def test_symlink_member_rejected():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("lesson.csv", csv_bytes([ROW]))
        info = zipfile.ZipInfo("link")
        info.external_attr = (0o120777 << 16)
        zf.writestr(info, "lesson.csv")
    assert "symlink" in codes([("p.zip", out.getvalue())])


def test_unexpected_files_and_types_rejected():
    assert "unexpected_file" in codes([("p.zip", make_zip({"lesson.csv": csv_bytes([ROW]), "run.exe": b"MZ"}))])
    assert "unexpected_file" in codes([("p.zip", make_zip({"lesson.csv": csv_bytes([ROW]), "assets/a.svg": b"<svg/>"}))])
    assert "file_type" in codes([("lesson.csv", csv_bytes([ROW])), ("notes.docx", b"x")])


def test_missing_csv_and_not_a_zip():
    assert "no_csv" in codes([("p.zip", make_zip({"lesson_plan.json": b"{}"}))])
    assert "bad_zip" in codes([("p.zip", b"not a zip")])
    assert "no_files" in codes([])


def test_plan_problems():
    assert "plan_json" in codes([("lesson.csv", csv_bytes([ROW])), ("lesson_plan.json", b"{nope")])
    assert "plan_shape" in codes([("lesson.csv", csv_bytes([ROW])), ("lesson_plan.json", b"[1]")])
    assert "plan_language" in codes([("lesson.csv", csv_bytes([ROW])), ("lesson_plan.json", b'{"language": "hi"}')], "en-IN")
    assert "plan_shape" in codes([("lesson.csv", csv_bytes([ROW])), ("lesson_plan.json", b'{"learning_objectives": "x"}')])


def test_image_column_must_exist_in_assets():
    raw = csv_bytes([ROW + ["a.png"]], list(CANONICAL_COLUMNS) + ["image"])
    assert "missing_image" in codes([("p.zip", make_zip({"lesson.csv": raw}))])
    assert ok([("p.zip", make_zip({"lesson.csv": raw, "assets/a.png": b"png"}))]).slides[0]["image"] == "a.png"


def test_size_limits(monkeypatch):
    monkeypatch.setattr(package, "MAX_CSV_BYTES", 50)
    assert "csv_too_large" in codes([("lesson.csv", csv_bytes([ROW]))])
    monkeypatch.setattr(package, "MAX_ZIP_BYTES", 10)
    assert "zip_too_large" in codes([("p.zip", make_zip({"lesson.csv": csv_bytes([ROW])}))])


def test_field_and_slide_count_limits(monkeypatch):
    monkeypatch.setattr(package, "MAX_TEXT", 10)
    assert "field_too_long" in codes([("lesson.csv", csv_bytes([ROW]))])
    monkeypatch.setattr(package, "MAX_TEXT", 4000)
    monkeypatch.setattr(package, "MAX_SLIDES", 1)
    assert "too_many_slides" in codes([("lesson.csv", csv_bytes([ROW, ["2"] + ROW[1:]]))])


def test_duration_warning_is_not_an_error():
    p = ok([("lesson.csv", csv_bytes([["1", "m", "word " * 600, "s", "v"]]))])
    assert "duration" in [w.code for w in p.warnings] and p.estimated_minutes > 4


def test_plan_slides_are_validated():
    base = [("lesson.csv", csv_bytes([ROW]))]
    assert "plan_slides" in codes(base + [("lesson_plan.json", b'{"slides": "x"}')])
    assert "plan_slides" in codes(base + [("lesson_plan.json", b'{"slides": [{"slide": 1}]}')])
    assert "plan_slides" in codes(base + [("lesson_plan.json", json.dumps({"slides": [{"slide": 1, "headline": "H", "bullets": ["b"] * 6}]}).encode())])
    assert "plan_slides" in codes(base + [("lesson_plan.json", json.dumps({"slides": [{"slide": 9, "headline": "H", "bullets": []}]}).encode())])
    good = json.dumps({"slides": [{"slide": 1, "headline": "Plants make food", "bullets": ["Sunlight", "Water"]}]}).encode()
    assert ok(base + [("lesson_plan.json", good)]).lesson_plan["slides"][0]["headline"] == "Plants make food"


def test_short_subtitles_warn_but_import():
    short = ["1", "Intro", "word " * 60, "Short", "Show"]
    p = ok([("lesson.csv", csv_bytes([short]))])
    assert "short_subtitles" in [w.code for w in p.warnings]
    full = ["1", "Intro", "word " * 60, "word " * 55, "Show"]
    assert "short_subtitles" not in [w.code for w in ok([("lesson.csv", csv_bytes([full]))]).warnings]


def _plan(slide):
    return ("lesson_plan.json", json.dumps({"slides": [{"slide": 1, "headline": "H", **slide}]}).encode())


def test_animation_layouts_are_validated():
    base = [("lesson.csv", csv_bytes([ROW]))]
    good = [
        {"layout": "flow", "diagram": {"steps": [{"label": "Sunlight"}, "Water", {"label": "Glucose", "role": "output"}]}},
        {"layout": "equation", "diagram": {"terms": ["Carbon dioxide", "+", "Water", "→", "Glucose"], "note": "in sunlight"}},
        {"layout": "cycle", "diagram": {"nodes": ["Evaporation", "Condensation", "Precipitation"]}},
        {"layout": "compare", "diagram": {"left": {"title": "A", "points": ["x"]}, "right": {"title": "B", "points": ["y", "z"]}}},
        {"layout": "bullets", "bullets": ["a"]},
    ]
    for slide in good:
        assert ok(base + [_plan(slide)]).lesson_plan["slides"][0]["headline"] == "H", slide
    bad = [
        {"layout": "spiral"},
        {"layout": "flow"},
        {"layout": "flow", "diagram": {"steps": ["only one"]}},
        {"layout": "flow", "diagram": {"steps": ["a"] * 6}},
        {"layout": "equation", "diagram": {"terms": ["a", "+"]}},
        {"layout": "cycle", "diagram": {"nodes": ["a", "b"]}},
        {"layout": "compare", "diagram": {"left": {"title": "A", "points": ["x"]}}},
        {"layout": "compare", "diagram": {"left": {"title": "", "points": ["x"]}, "right": {"title": "B", "points": ["y"]}}},
        {"layout": "flow", "diagram": {"steps": ["x" * 61, "b"]}},
    ]
    for slide in bad:
        assert "plan_diagram" in codes(base + [_plan(slide)]), slide


def test_illustration_layouts_are_validated():
    base = [("lesson.csv", csv_bytes([ROW]))]
    for template in ("refraction", "photosynthesis", "water_cycle", "leaf_section"):
        p = ok(base + [_plan({"layout": "illustration", "diagram": {"template": template}})])
        assert p.lesson_plan["slides"][0]["layout"] == "illustration"
    good = {"layout": "illustration", "diagram": {"template": "refraction", "params": {"medium": "water", "direction": "into_rarer", "angle": 28}, "labels": {"normal": "Normal"}}}
    assert ok(base + [_plan(good)])
    bad = [
        {"layout": "illustration"},
        {"layout": "illustration", "diagram": {"template": "volcano"}},
        {"layout": "illustration", "diagram": {"template": "refraction", "params": {"medium": "oil"}}},
        {"layout": "illustration", "diagram": {"template": "refraction", "params": {"direction": "sideways"}}},
        {"layout": "illustration", "diagram": {"template": "refraction", "params": {"angle": 89}}},
        {"layout": "illustration", "diagram": {"template": "refraction", "params": "x"}},
        {"layout": "illustration", "diagram": {"template": "refraction", "labels": {"normal": ""}}},
    ]
    for slide in bad:
        assert "plan_diagram" in codes(base + [_plan(slide)]), slide


def test_e4_layouts_are_validated():
    base = [("lesson.csv", csv_bytes([ROW]))]
    good = [
        {"layout": "text_illustration", "bullets": ["Light slows in glass"], "diagram": {"template": "refraction"}},
        {"layout": "timeline", "diagram": {"events": [{"label": "1621", "sub": "Snell"}, {"label": "1678"}, "1801"]}},
        {"layout": "labelled_diagram", "diagram": {"shape": "rect", "title": "Cell", "parts": [{"label": "A", "x": 0.2, "y": 0.3}, {"label": "B", "x": 0.7, "y": 0.8}]}},
        {"layout": "experiment", "diagram": {"aim": "To test", "materials": ["leaf"], "procedure": ["Boil it"], "observation": "Blue", "conclusion": "Starch"}},
        {"layout": "experiment", "diagram": {"aim": "To test", "procedure": ["Boil it"]}},
        {"layout": "recap", "bullets": ["one", "two"], "diagram": {"question": "Why?"}},
        {"layout": "recap", "bullets": ["one", "two", "three"]},
    ]
    for slide in good:
        assert ok(base + [_plan(slide)]).lesson_plan["slides"][0]["layout"] == slide["layout"], slide
    bad = [
        {"layout": "text_illustration", "diagram": {"template": "refraction"}},
        {"layout": "text_illustration", "bullets": ["a"], "diagram": {"template": "volcano"}},
        {"layout": "timeline", "diagram": {"events": ["a", "b"]}},
        {"layout": "labelled_diagram", "diagram": {"parts": [{"label": "A", "x": 2, "y": 0.3}, {"label": "B", "x": 0.5, "y": 0.5}]}},
        {"layout": "labelled_diagram", "diagram": {"shape": "star", "parts": [{"label": "A", "x": 0.2, "y": 0.3}, {"label": "B", "x": 0.7, "y": 0.8}]}},
        {"layout": "experiment", "diagram": {"aim": "To test"}},
        {"layout": "experiment", "diagram": {"aim": "", "procedure": ["x"]}},
        {"layout": "recap", "bullets": ["only one"]},
        {"layout": "recap", "bullets": ["a", "b"], "diagram": {"question": ""}},
    ]
    for slide in bad:
        assert "plan_diagram" in codes(base + [_plan(slide)]), slide
