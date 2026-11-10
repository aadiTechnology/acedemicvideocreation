"""Lesson package import: validation, safe archive handling and normalization.

Accepted uploads: one ZIP, or ``lesson.csv`` (plus an optional ``lesson_plan.json``). The five canonical CSV columns are
preserved exactly; the original CSV bytes are stored untouched in the canonical package.

    lesson-package/
      lesson.csv            Slide, Module, voice_text, subtitle_text, visual_instruction   (optional extra column: image)
      lesson_plan.json      optional; objectives, quiz, source references
      academic_review.json  optional
      assets/               optional PNG/JPEG images
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

CANONICAL_COLUMNS = ("Slide", "Module", "voice_text", "subtitle_text", "visual_instruction")
REQUIRED_TEXT = ("Module", "voice_text", "subtitle_text", "visual_instruction")
IMAGE_EXTS = (".png", ".jpg", ".jpeg")
MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_UNPACKED = 200 * 1024 * 1024
MAX_FILES = 300
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_SLIDES = 200
MAX_TEXT = 4000
WORDS_PER_MINUTE = 130
LANG_ALIASES = {"en": "en-IN", "hi": "hi-IN", "mr": "mr-IN", "en-in": "en-IN", "hi-in": "hi-IN", "mr-in": "mr-IN"}


@dataclass
class Issue:
    code: str
    message: str
    row: int | None = None
    column: str | None = None
    severity: str = "error"

    def dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


class ImportRejected(Exception):
    def __init__(self, issues: list[Issue]) -> None:
        super().__init__("The package has errors.")
        self.issues = issues


@dataclass
class ParsedPackage:
    slides: list[dict]
    lesson_plan: dict | None
    zip_bytes: bytes
    sha256: str
    warnings: list[Issue] = field(default_factory=list)
    word_count: int = 0

    @property
    def estimated_minutes(self) -> float:
        return round(self.word_count / WORDS_PER_MINUTE, 1)


def _err(code: str, message: str, **kw) -> Issue:
    return Issue(code, message, **kw)


def _safe_members(zf: zipfile.ZipFile, issues: list[Issue]) -> list[zipfile.ZipInfo]:
    members = [m for m in zf.infolist() if not m.is_dir()]
    if len(members) > MAX_FILES:
        issues.append(_err("too_many_files", f"The package has more than {MAX_FILES} files."))
        return []
    total = 0
    for m in members:
        raw = m.orig_filename
        path = PurePosixPath(raw)
        if "\\" in raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw) or ".." in path.parts:
            issues.append(_err("unsafe_path", f"Unsafe path in the archive: {raw!r}."))
        if (m.external_attr >> 16) & 0o170000 == 0o120000:
            issues.append(_err("symlink", f"Links are not allowed in the archive: {raw!r}."))
        total += m.file_size
        if m.file_size > 1024 * 1024 and m.compress_size and m.file_size / m.compress_size > 200:
            issues.append(_err("zip_bomb", f"{raw!r} is suspiciously compressed."))
    if total > MAX_UNPACKED:
        issues.append(_err("too_large", "The package is too large when unpacked."))
    return members


def _strip_root(names: list[str]) -> str:
    """If every file sits in one folder (lesson-package/...), return that prefix."""
    tops = {PurePosixPath(n).parts[0] for n in names if len(PurePosixPath(n).parts) > 1}
    flat = [n for n in names if len(PurePosixPath(n).parts) == 1]
    return f"{tops.pop()}/" if len(tops) == 1 and not flat else ""


def _parse_csv(raw: bytes, issues: list[Issue], assets: set[str]) -> list[dict]:
    if len(raw) > MAX_CSV_BYTES:
        issues.append(_err("csv_too_large", "lesson.csv is larger than 2 MB."))
        return []
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        issues.append(_err("encoding", "lesson.csv must be saved as UTF-8 (CSV UTF-8 in Excel). It looks like another encoding."))
        return []
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        issues.append(_err("empty_csv", "lesson.csv is empty."))
        return []
    except csv.Error as exc:
        issues.append(_err("csv_format", f"lesson.csv is not a valid CSV file: {exc}"))
        return []
    for col in CANONICAL_COLUMNS:
        if col not in header:
            issues.append(_err("missing_column", f"Missing column {col!r}. Expected: {', '.join(CANONICAL_COLUMNS)}.", column=col))
    for col in header:
        if col not in CANONICAL_COLUMNS and col != "image":
            issues.append(_err("unexpected_column", f"Unexpected column {col!r}. Remove it or move the data to lesson_plan.json.", column=col))
    if len(set(header)) != len(header):
        issues.append(_err("duplicate_column", "A column name appears more than once."))
    if any(i.code in ("missing_column", "unexpected_column", "duplicate_column") for i in issues):
        return []
    rows, seen = [], {}
    try:
        for n, cells in enumerate(reader, start=2):
            if not any(c.strip() for c in cells):
                continue
            if len(cells) != len(header):
                issues.append(_err("row_shape", f"Row {n} has {len(cells)} cells but the header has {len(header)}. Check for an unquoted comma.", row=n))
                continue
            row = {h: c.strip() for h, c in zip(header, cells)}
            sid = row["Slide"]
            if not sid:
                issues.append(_err("empty_slide_id", f"Row {n}: Slide is empty.", row=n, column="Slide"))
            elif not (sid.isdigit() and int(sid) >= 1):
                issues.append(_err("bad_slide_id", f"Row {n}: Slide must be a positive whole number, got {sid!r}.", row=n, column="Slide"))
            elif int(sid) in seen:
                issues.append(_err("duplicate_slide", f"Row {n}: Slide {sid} already appears in row {seen[int(sid)]}.", row=n, column="Slide"))
            else:
                seen[int(sid)] = n
            for col in REQUIRED_TEXT:
                if not row[col]:
                    issues.append(_err("empty_field", f"Row {n}: {col} is empty.", row=n, column=col))
                elif len(row[col]) > MAX_TEXT:
                    issues.append(_err("field_too_long", f"Row {n}: {col} is longer than {MAX_TEXT} characters.", row=n, column=col))
            image = row.get("image", "")
            if image and f"assets/{image}" not in assets:
                issues.append(_err("missing_image", f"Row {n}: image {image!r} is not in assets/.", row=n, column="image"))
            rows.append((n, row))
    except csv.Error as exc:
        issues.append(_err("csv_format", f"lesson.csv is not a valid CSV file: {exc}"))
        return []
    if not rows:
        issues.append(_err("no_slides", "lesson.csv has a header but no slides."))
    if len(rows) > MAX_SLIDES:
        issues.append(_err("too_many_slides", f"The lesson has more than {MAX_SLIDES} slides."))
    slides = []
    for _, row in sorted(rows, key=lambda r: int(r[1]["Slide"]) if r[1]["Slide"].isdigit() else 0):
        slide = {"slide": int(row["Slide"]) if row["Slide"].isdigit() else 0, "module": row["Module"], "voice_text": row["voice_text"],
                 "subtitle_text": row["subtitle_text"], "visual_instruction": row["visual_instruction"]}
        if row.get("image"):
            slide["image"] = row["image"]
        slides.append(slide)
    return slides


LAYOUTS = ("bullets", "flow", "equation", "cycle", "compare", "illustration",
           "text_illustration", "timeline", "labelled_diagram", "experiment", "recap", "code", "photo", "clip", "before_after")
MEDIA_LAYOUTS = ("photo", "clip", "before_after")
LICENCES = ("CC0", "Public domain", "CC BY", "CC BY-SA", "Own work", "Permission granted")  # same list as the Video Engine
CLIP_EXTS = (".mp4",)
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_CLIP_BYTES = 20 * 1024 * 1024


def _media_ref_problem(ref, name: str, exts: tuple) -> str | None:
    if not isinstance(ref, dict):
        return f"{name} must be an object with file, source, licence and credit."
    file = ref.get("file")
    if not isinstance(file, str) or not file.strip():
        return f"{name}.file is required, for example \"media/{'clip.mp4' if '.mp4' in exts else 'picture.jpg'}\"."
    path = PurePosixPath(file)
    if "\\" in file or path.is_absolute() or ".." in path.parts or path.parts[:1] != ("media",) or len(path.parts) != 2:
        return f"{name}.file must be \"media/<file name>\" (the file is added to the lesson with Add picture or clip)."
    if path.suffix.lower() not in exts:
        return f"{name}.file must be {' or '.join(exts)}."
    for key, limit in (("source", 300), ("credit", 120)):
        if not (isinstance(ref.get(key), str) and 0 < len(ref[key].strip()) <= limit):
            what = "where the file came from (a web address or a book)" if key == "source" else "the name to show on screen (author or owner)"
            return f"{name}.{key} is required: {what}."
    if ref.get("licence") not in LICENCES:
        return f"{name}.licence must be one of: {', '.join(LICENCES)}."
    for key in ("caption", "label"):
        if key in ref and not (isinstance(ref[key], str) and len(ref[key]) <= 100):
            return f"{name}.{key} is text of up to 100 characters."
    return None


def media_refs(item: dict) -> list[dict]:
    diagram = item.get("diagram") if isinstance(item.get("diagram"), dict) else {}
    layout = item.get("layout")
    if layout in ("photo", "clip"):
        return [diagram.get(layout)]
    if layout == "before_after":
        return [diagram.get("before"), diagram.get("after")]
    return []


def _media_problem(layout: str, diagram: dict, item: dict) -> str | None:
    if layout == "photo":
        problem = _media_ref_problem(diagram.get("photo"), "photo", IMAGE_EXTS)
    elif layout == "clip":
        problem = _media_ref_problem(diagram.get("clip"), "clip", CLIP_EXTS)
    else:
        problem = _media_ref_problem(diagram.get("before"), "before", IMAGE_EXTS) or _media_ref_problem(diagram.get("after"), "after", IMAGE_EXTS)
    if problem:
        return problem
    if layout != "before_after" and item.get("bullets") and not _texts(item["bullets"], 1, 4):
        return f"{layout} takes at most 4 short bullets beside the media."
    return None
ILLUSTRATIONS = ("refraction", "photosynthesis", "water_cycle", "leaf_section")


def _texts(value, low: int, high: int) -> bool:
    items = [(v.get("label") if isinstance(v, dict) else v) for v in value] if isinstance(value, list) else None
    return items is not None and low <= len(items) <= high and all(isinstance(x, str) and x.strip() and len(x) <= 60 for x in items)


CODE_LANGUAGES = ("python", "javascript", "java", "c", "cpp", "sql", "bash", "html", "json")


def _code_problem(diagram: dict) -> str | None:
    code = diagram.get("code")
    if not isinstance(code, str) or not code.strip():
        return "code needs diagram.code: the code as text (up to 18 lines of up to 80 characters)."
    lines = code.rstrip("\n").split("\n")
    if len(lines) > 18 or any(len(ln) > 80 for ln in lines):
        return "code: at most 18 lines, each up to 80 characters. Show a shorter excerpt."
    if diagram.get("language", "python") not in CODE_LANGUAGES:
        return f"code language must be one of: {', '.join(CODE_LANGUAGES)}."
    steps = diagram.get("steps")
    if steps is None:
        return None
    if not isinstance(steps, list) or not 1 <= len(steps) <= 12:
        return "code steps: 1 to 12 items."
    for n, st in enumerate(steps, 1):
        nums = st.get("lines", [st["line"]] if isinstance(st, dict) and "line" in st else None) if isinstance(st, dict) else None
        if not (isinstance(nums, list) and nums and all(isinstance(x, int) and 1 <= x <= len(lines) for x in nums)):
            return f"code step {n}: lines must be line numbers between 1 and {len(lines)}."
        if "output" in st and not (isinstance(st["output"], str) and len(st["output"]) <= 200):
            return f"code step {n}: output must be text up to 200 characters."
        vars_ = st.get("vars", {})
        if not (isinstance(vars_, dict) and len(vars_) <= 6 and all(isinstance(k, str) and 0 < len(k) <= 30 and len(str(v)) <= 40 for k, v in vars_.items())):
            return f"code step {n}: vars is up to 6 names with short values."
    return None


def _terms_ok(value) -> bool:
    return isinstance(value, list) and len(value) <= 20 and all(isinstance(t, str) and 0 < len(t.strip()) <= 40 for t in value)


def _diagram_problem(item: dict) -> str | None:
    """Check the optional animation layout of one slide. Returns a plain-words problem, or None."""
    layout = item.get("layout", "bullets")
    if "key_terms" in item and not _terms_ok(item["key_terms"]):
        return "key_terms must be a list of up to 20 short terms (each up to 40 characters)."
    if layout not in LAYOUTS:
        return f"layout must be one of {', '.join(LAYOUTS)}."
    diagram = item.get("diagram")
    if layout == "bullets":
        return None
    if not isinstance(diagram, dict):
        if layout == "recap" and diagram is None:
            diagram = {}
        else:
            return f"layout {layout} needs a diagram object."
    if layout in MEDIA_LAYOUTS:
        return _media_problem(layout, diagram, item)
    if layout == "flow" and not _texts(diagram.get("steps"), 2, 5):
        return "flow needs diagram.steps: 2 to 5 short labels."
    if layout == "equation" and not _texts(diagram.get("terms"), 3, 9):
        return "equation needs diagram.terms: 3 to 9 items, for example [\"Carbon dioxide\", \"+\", \"Water\", \"→\", \"Glucose\"]."
    if layout == "cycle" and not _texts(diagram.get("nodes"), 3, 6):
        return "cycle needs diagram.nodes: 3 to 6 short labels."
    if layout == "illustration":
        if diagram.get("template") not in ILLUSTRATIONS:
            return f"illustration needs diagram.template, one of: {', '.join(ILLUSTRATIONS)}."
        params, labels = diagram.get("params", {}), diagram.get("labels", {})
        if not isinstance(params, dict) or not isinstance(labels, dict) or not all(isinstance(v, str) and 0 < len(v) <= 60 for v in labels.values()):
            return "illustration params and labels must be objects; labels are short texts."
        if params.get("medium", "glass") not in ("glass", "water") or params.get("direction", "into_denser") not in ("into_denser", "into_rarer"):
            return "refraction params: medium is glass or water, direction is into_denser or into_rarer."
        if "angle" in params and not (isinstance(params["angle"], (int, float)) and 10 <= params["angle"] <= 75):
            return "refraction params: angle is a number between 10 and 75 degrees."
        return None
    if layout == "text_illustration":
        if diagram.get("template") not in ILLUSTRATIONS:
            return f"text_illustration needs diagram.template, one of: {', '.join(ILLUSTRATIONS)}."
        if not _texts(item.get("bullets"), 1, 5):
            return "text_illustration needs 1 to 5 short bullets next to the picture."
    if layout == "timeline":
        events = diagram.get("events")
        if not (_texts(events, 3, 6) and all(len(str(e.get("sub", ""))) <= 60 for e in events if isinstance(e, dict))):
            return "timeline needs diagram.events: 3 to 6 items, each with a short label (for example a year) and an optional short sub text."
    if layout == "labelled_diagram":
        parts = diagram.get("parts")
        ok = isinstance(parts, list) and 2 <= len(parts) <= 8 and all(
            isinstance(p, dict) and isinstance(p.get("label"), str) and p["label"].strip() and len(p["label"]) <= 60
            and all(isinstance(p.get(c), (int, float)) and 0 <= p[c] <= 1 for c in ("x", "y")) for p in parts)
        if not ok:
            return "labelled_diagram needs diagram.parts: 2 to 8 items, each with a label and x, y between 0 and 1."
        if diagram.get("shape", "oval") not in ("oval", "rect", "circle"):
            return "labelled_diagram shape is oval, rect or circle."
    if layout == "experiment":
        if not (isinstance(diagram.get("aim"), str) and diagram["aim"].strip() and _texts(diagram.get("procedure"), 1, 4)):
            return "experiment needs diagram.aim and diagram.procedure (1 to 4 short steps); materials, observation and conclusion are optional."
        if "materials" in diagram and not _texts(diagram["materials"], 1, 6):
            return "experiment materials: 1 to 6 short items."
    if layout == "code":
        problem = _code_problem(diagram)
        if problem:
            return problem
    if layout == "recap":
        if not _texts(item.get("bullets"), 2, 5):
            return "recap needs 2 to 5 short bullets (the key points)."
        if "question" in diagram and not (isinstance(diagram["question"], str) and 0 < len(diagram["question"]) <= 120):
            return "recap question must be a short text."
    if layout == "compare":
        for side in ("left", "right"):
            part = diagram.get(side)
            if not (isinstance(part, dict) and isinstance(part.get("title"), str) and part["title"].strip() and _texts(part.get("points"), 1, 4)):
                return f"compare needs diagram.{side} with a title and 1 to 4 points."
    return None


def _parse_plan(raw: bytes, language: str, issues: list[Issue], name: str = "lesson_plan.json") -> dict | None:
    try:
        plan = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        issues.append(_err("plan_json", f"{name} is not valid UTF-8 JSON."))
        return None
    if not isinstance(plan, dict):
        issues.append(_err("plan_shape", f"{name} must be a JSON object."))
        return None
    lang = plan.get("language")
    if lang is not None:
        if not isinstance(lang, str) or LANG_ALIASES.get(lang.lower()) != language:
            names = {"en-IN": "English", "hi-IN": "Hindi", "mr-IN": "Marathi"}
            issues.append(_err("plan_language", f"{name} says language {lang!r} but this version is {language} ({names.get(language, language)}). "
                                                f"Each language version needs its own files: copy the prompt from THIS version (Show ChatGPT prompt) so ChatGPT writes "
                                                f"{names.get(language, language)} text with \"language\": \"{language}\". "
                                                f"If the text really is in {names.get(language, language)}, change \"language\" in {name} to \"{language}\" and import again."))
    for key in ("learning_objectives", "source_references", "quiz"):
        if key in plan and not isinstance(plan[key], list):
            issues.append(_err("plan_shape", f"{name}: {key} must be a list."))
    if "key_terms" in plan and not _terms_ok(plan["key_terms"]):
        issues.append(_err("plan_shape", f"{name}: key_terms must be a list of up to 20 short terms (each up to 40 characters)."))
    if isinstance(plan.get("learning_objectives"), list) and not all(isinstance(x, str) for x in plan["learning_objectives"]):
        issues.append(_err("plan_shape", f"{name}: learning_objectives must be a list of text."))
    if "slides" in plan:
        if not isinstance(plan["slides"], list):
            issues.append(_err("plan_slides", f"{name}: slides must be a list of {{slide, headline, bullets}}."))
        else:
            for i, item in enumerate(plan["slides"], 1):
                ok = (isinstance(item, dict) and isinstance(item.get("slide"), int) and item["slide"] >= 1
                      and isinstance(item.get("headline"), str) and item["headline"].strip()
                      and isinstance(item.get("bullets", []), list) and all(isinstance(b, str) for b in item.get("bullets", [])))
                if not ok:
                    issues.append(_err("plan_slides", f"{name}: slides item {i} needs a whole-number slide, a headline and a list of bullet texts."))
                elif len(item.get("bullets", [])) > 5 or any(len(b) > 140 for b in item.get("bullets", [])) or len(item["headline"]) > 100:
                    issues.append(_err("plan_slides", f"{name}: slides item {i} is too long (headline up to 100 characters, at most 5 bullets of up to 140)."))
                else:
                    problem = _diagram_problem(item)
                    if problem:
                        issues.append(_err("plan_diagram", f"{name}: slides item {i} (slide {item['slide']}): {problem}"))
    return plan


def parse_upload(files: list[tuple[str, bytes]], language: str, lesson_defaults: dict) -> ParsedPackage:
    """Validate an upload and build the canonical package. Raises ImportRejected with every problem found."""
    issues: list[Issue] = []
    members: dict[str, bytes] = {}
    if not files:
        raise ImportRejected([_err("no_files", "No file was uploaded.")])
    if len(files) == 1 and files[0][0].lower().endswith(".zip"):
        data = files[0][1]
        if len(data) > MAX_ZIP_BYTES:
            raise ImportRejected([_err("zip_too_large", "The ZIP is larger than 50 MB.")])
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise ImportRejected([_err("bad_zip", "The file is not a valid ZIP archive.")]) from None
        with zf:
            infos = _safe_members(zf, issues)
            if issues:
                raise ImportRejected(issues)
            prefix = _strip_root([i.orig_filename for i in infos])
            for info in infos:
                members[info.orig_filename[len(prefix):]] = zf.read(info)
    else:
        for name, data in files:
            base = PurePosixPath(name.replace("\\", "/")).name.lower()
            if base.endswith(".csv"):
                if "lesson.csv" in members:
                    issues.append(_err("two_csv", "Upload only one CSV file."))
                members["lesson.csv"] = data
            elif base.endswith(".json"):
                members["academic_review.json" if base == "academic_review.json" else "lesson_plan.json"] = data
            else:
                issues.append(_err("file_type", f"{name!r}: upload one ZIP, or lesson.csv with an optional lesson_plan.json."))
    if "lesson.csv" not in members:
        issues.append(_err("no_csv", "lesson.csv was not found at the top of the package."))
    for name in members:
        p = PurePosixPath(name)
        if name in ("lesson.csv", "lesson_plan.json", "academic_review.json"):
            continue
        if p.parts[0] == "assets" and p.suffix.lower() in IMAGE_EXTS:
            if p.parts[1:2] == ("media",) and len(members[name]) > MAX_IMAGE_BYTES:
                issues.append(_err("media_too_large", f"{name!r} is larger than {MAX_IMAGE_BYTES // 1048576} MB."))
            continue
        if p.parts[:2] == ("assets", "media") and len(p.parts) == 3 and p.suffix.lower() in CLIP_EXTS:
            if len(members[name]) > MAX_CLIP_BYTES:
                issues.append(_err("media_too_large", f"{name!r} is larger than {MAX_CLIP_BYTES // 1048576} MB."))
            continue
        issues.append(_err("unexpected_file", f"Unexpected file {name!r}. Only lesson.csv, lesson_plan.json, academic_review.json, PNG/JPEG images in assets/ and photos or MP4 clips in assets/media/ are accepted."))
    assets = {n for n in members if n.startswith("assets/")}
    slides = _parse_csv(members["lesson.csv"], issues, assets) if "lesson.csv" in members else []
    plan = _parse_plan(members["lesson_plan.json"], language, issues) if "lesson_plan.json" in members else None
    if isinstance(plan, dict):  # real-world media named in the plan must be in the package
        for item in plan.get("slides", []) if isinstance(plan.get("slides"), list) else []:
            if isinstance(item, dict) and item.get("layout") in MEDIA_LAYOUTS:
                for ref in media_refs(item):
                    if isinstance(ref, dict) and isinstance(ref.get("file"), str) and f"assets/{ref['file']}" not in members:
                        issues.append(_err("media_missing", f"lesson_plan.json: slide {item.get('slide')} uses {ref['file']!r}, which is not in the package (assets/{ref['file']})."))
    if "academic_review.json" in members:
        _parse_plan(members["academic_review.json"], language, issues, "academic_review.json")
    if issues:
        raise ImportRejected(issues)

    warnings: list[Issue] = []
    words = sum(len(s["voice_text"].split()) for s in slides)
    target = lesson_defaults.get("expected_duration_minutes") or 0
    est = words / WORDS_PER_MINUTE
    if target and not (0.5 * target <= est <= 1.5 * target):
        warnings.append(Issue("duration", f"The narration has about {words} words, roughly {est:.1f} minutes, but the lesson target is {target} minutes.", severity="warning"))
    for s in slides:
        if len(s["subtitle_text"]) > 200:
            warnings.append(Issue("long_subtitle", f"Slide {s['slide']}: subtitle_text is long ({len(s['subtitle_text'])} characters); it may be hard to read on screen.", row=s["slide"], severity="warning"))
    known = {s["slide"] for s in slides}
    for item in (plan or {}).get("slides", []) if isinstance((plan or {}).get("slides"), list) else []:
        if isinstance(item, dict) and isinstance(item.get("slide"), int) and item["slide"] not in known:
            raise ImportRejected([_err("plan_slides", f"lesson_plan.json describes slide {item['slide']}, which is not in lesson.csv.")])
    short = [s["slide"] for s in slides if len(s["subtitle_text"].split()) < 0.6 * len(s["voice_text"].split())]
    if short:
        warnings.append(Issue("short_subtitles", "Captions are timed from subtitle_text, so they follow the narration only if it is close to voice_text. "
                              f"Slide(s) {', '.join(map(str, short[:8]))}{'...' if len(short) > 8 else ''} have a much shorter subtitle_text than voice_text. "
                              "Use the narration text as the subtitle text, and put short on-screen wording in lesson_plan.json under slides.", severity="warning"))
    if plan is None:
        plan_out = {"title": lesson_defaults.get("title", ""), "language": language,
                    "learning_objectives": lesson_defaults.get("learning_objectives", []),
                    "source_references": lesson_defaults.get("source_references", [])}
        members["lesson_plan.json"] = json.dumps(plan_out, ensure_ascii=False, indent=2).encode("utf-8")
        plan = plan_out
        warnings.append(Issue("no_plan", "No lesson_plan.json was supplied; one was generated from the lesson details.", severity="warning"))

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))  # fixed timestamp: same content, same hash
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, members[name])
    blob = out.getvalue()
    return ParsedPackage(slides=slides, lesson_plan=plan, zip_bytes=blob, sha256=hashlib.sha256(blob).hexdigest(), warnings=warnings, word_count=words)
