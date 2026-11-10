"""Assessment questions (E11): the rules a question must meet, converting a quiz from lesson_plan.json, and the self-contained practice page.

Kinds
  multiple_choice  2 to 5 options, exactly one correct (answer_index)
  image            a picture from the lesson's media (see E9) and 2 to 5 options: "what is this?"
  diagram          like image, for naming a part or label of a diagram or photograph
  conceptual       an open question with a model answer the learner compares with; nothing to mark automatically
Every question needs an explanation shown after answering. A lesson version holds at most 5 questions and is "complete" with 3 or more approved."""
from __future__ import annotations

import base64
import html
import json
import re
import zipfile
from pathlib import Path, PurePosixPath

KINDS = ("multiple_choice", "image", "diagram", "conceptual")
CHOICE_KINDS = ("multiple_choice", "image", "diagram")
PICTURE_KINDS = ("image", "diagram")
MAX_QUESTIONS = 5
MIN_COMPLETE = 3
MIN_OPTIONS, MAX_OPTIONS = 2, 5
MAX_PROMPT, MAX_OPTION, MAX_TEXT = 400, 160, 1200
STATUSES = ("draft", "approved")


class QuestionProblem(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _text(value, name: str, limit: int, required: bool = True) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise QuestionProblem(f"{name} must be text.")
    value = " ".join(value.split()) if limit <= MAX_OPTION else value.strip()
    if required and not value:
        raise QuestionProblem(f"{name} cannot be empty.")
    if len(value) > limit:
        raise QuestionProblem(f"{name} is longer than {limit} characters.")
    return value


def clean(data: dict, media_files: set[str], slide_numbers: set[int]) -> dict:
    """Validate and normalise a question from the API. Raises QuestionProblem with a plain-words reason."""
    kind = data.get("kind")
    if kind not in KINDS:
        raise QuestionProblem(f"kind must be one of: {', '.join(KINDS)}.")
    out: dict = {"kind": kind, "prompt": _text(data.get("prompt"), "The question", MAX_PROMPT),
                 "explanation": _text(data.get("explanation"), "The explanation", MAX_TEXT)}
    if kind in CHOICE_KINDS:
        raw = data.get("options")
        if not isinstance(raw, list):
            raise QuestionProblem("options must be a list of answer choices.")
        options = [_text(o, "An answer choice", MAX_OPTION) for o in raw]
        if not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
            raise QuestionProblem(f"Give {MIN_OPTIONS} to {MAX_OPTIONS} answer choices.")
        if len({o.casefold() for o in options}) != len(options):
            raise QuestionProblem("Two answer choices are the same.")
        idx = data.get("answer_index")
        if not isinstance(idx, int) or isinstance(idx, bool) or not 0 <= idx < len(options):
            raise QuestionProblem("Choose which answer is correct.")
        out.update(options=options, answer_index=idx, model_answer="")
    else:
        out.update(options=[], answer_index=None, model_answer=_text(data.get("model_answer"), "The model answer", MAX_TEXT))
    image = data.get("image_file")
    if kind in PICTURE_KINDS:
        if not isinstance(image, str) or not image.strip():
            raise QuestionProblem(f"A {kind} question needs a picture: add one in the slide editor (Pictures and clips) and choose it here.")
        if image not in media_files:
            raise QuestionProblem(f"The picture {image!r} is not in this lesson. Add it first.")
        out["image_file"] = image
    elif image:
        raise QuestionProblem("Only image and diagram questions use a picture.")
    else:
        out["image_file"] = None
    slide = data.get("slide")
    if slide not in (None, ""):
        if not isinstance(slide, int) or isinstance(slide, bool) or slide not in slide_numbers:
            raise QuestionProblem("slide must be the number of a slide in this lesson.")
        out["slide"] = slide
    else:
        out["slide"] = None
    return out


def media_files(package_path: str | None) -> set[str]:
    """Names (``media/<file>``) of the photos in the stored package; clips cannot be question pictures."""
    if not package_path or not Path(package_path).is_file():
        return set()
    with zipfile.ZipFile(package_path) as zf:
        return {n[len("assets/"):] for n in zf.namelist() if n.startswith("assets/media/") and PurePosixPath(n).suffix.lower() in (".png", ".jpg", ".jpeg")}


def picture(package_path: str | None, name: str) -> tuple[bytes, str] | None:
    if not package_path or not Path(package_path).is_file():
        return None
    with zipfile.ZipFile(package_path) as zf:
        try:
            data = zf.read(f"assets/{name}")
        except KeyError:
            return None
    return data, ("image/png" if name.lower().endswith(".png") else "image/jpeg")


def from_plan_quiz(quiz: list) -> list[dict]:
    """Draft questions from the ``quiz`` list ChatGPT wrote in lesson_plan.json. Items that cannot be understood are skipped, with a reason each."""
    drafts, skipped = [], []
    for i, q in enumerate(quiz if isinstance(quiz, list) else [], 1):
        if not isinstance(q, dict) or not isinstance(q.get("question"), str):
            skipped.append(f"Question {i} has no text.")
            continue
        options, answer = q.get("options"), q.get("answer")
        kind = q.get("kind") if q.get("kind") in KINDS else ("multiple_choice" if isinstance(options, list) and options else "conceptual")
        draft = {"kind": kind, "prompt": q["question"], "explanation": q.get("explanation") or "Explain the answer here.", "slide": None}
        if kind in CHOICE_KINDS:
            opts = [str(o) for o in options] if isinstance(options, list) else []
            idx = opts.index(str(answer)) if str(answer) in opts else (answer if isinstance(answer, int) and 0 <= answer < len(opts) else None)
            if idx is None:
                skipped.append(f"Question {i}: the answer is not one of the options.")
                continue
            draft.update(options=opts, answer_index=idx)
        else:
            draft.update(options=[], answer_index=None, model_answer=str(answer or q.get("model_answer") or "Write the model answer here."))
        if kind in PICTURE_KINDS:
            kind = "multiple_choice"  # the picture is added by the teacher; start as a plain choice question
            draft["kind"] = kind
        drafts.append(draft)
    return [{"draft": d} for d in drafts] + [{"skipped": s} for s in skipped]


def summary(questions: list) -> dict:
    approved = sum(1 for q in questions if q.status == "approved")
    return {"count": len(questions), "approved": approved, "complete": approved >= MIN_COMPLETE, "max": MAX_QUESTIONS, "min_complete": MIN_COMPLETE}


def out(q, include_answer: bool = True) -> dict:
    d = {"id": q.id, "position": q.position, "kind": q.kind, "prompt": q.prompt, "options": q.options or [], "image_file": q.image_file, "slide": q.slide,
         "status": q.status, "approved_by": q.approved_by, "approved_at": q.approved_at}
    if include_answer:
        d.update(answer_index=q.answer_index, model_answer=q.model_answer, explanation=q.explanation)
    return d


def check(q, choice=None, text: str | None = None) -> dict:
    """Mark one answer. Choice questions are marked; conceptual questions show the model answer and are never marked."""
    if q.kind in CHOICE_KINDS:
        if not isinstance(choice, int) or isinstance(choice, bool) or not 0 <= choice < len(q.options or []):
            raise QuestionProblem("Choose one of the answers.")
        return {"correct": choice == q.answer_index, "correct_index": q.answer_index, "explanation": q.explanation}
    if not (isinstance(text, str) and text.strip()):
        raise QuestionProblem("Write your answer first, then compare it with the model answer.")
    return {"correct": None, "model_answer": q.model_answer, "explanation": q.explanation}


_SAFE = re.compile(r"[^A-Za-z0-9 _.-]")


def export_html(title: str, language: str, questions: list, package_path: str | None) -> str:
    """One self-contained page (no network, no tracking) that lets a learner answer the approved questions and see feedback at once."""
    items = []
    for n, q in enumerate(questions, 1):
        pic = picture(package_path, q.image_file) if q.image_file else None
        items.append({"n": n, "kind": q.kind, "prompt": q.prompt, "options": q.options or [], "answer": q.answer_index, "model": q.model_answer, "explanation": q.explanation,
                      "image": f"data:{pic[1]};base64,{base64.b64encode(pic[0]).decode('ascii')}" if pic else None})
    data = json.dumps(items, ensure_ascii=False).replace("<", "\\u003c")  # no "<" survives, so a question can never end or restart the script
    return f"""<!doctype html>
<html lang="{html.escape(language)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}: practice questions</title>
<style>
body{{font:17px/1.5 system-ui,Segoe UI,sans-serif;margin:0;background:#f4f6f8;color:#14202b}} main{{max-width:760px;margin:0 auto;padding:20px 16px 60px}}
h1{{font-size:24px}} .q{{background:#fff;border:1px solid #d7dde3;border-radius:10px;padding:16px 18px;margin:16px 0}} .q img{{max-width:100%;border-radius:8px;margin:8px 0}}
button.o{{display:block;width:100%;text-align:left;margin:6px 0;padding:10px 12px;border:1px solid #b9c3cc;border-radius:8px;background:#fff;font:inherit;cursor:pointer}}
button.o.right{{background:#e3f6e8;border-color:#2e9e57}} button.o.wrong{{background:#fde8e8;border-color:#d64545}} textarea{{width:100%;box-sizing:border-box;min-height:80px;font:inherit}}
.fb{{margin-top:10px;padding:10px 12px;border-radius:8px;background:#eef3f8}} .go{{padding:8px 14px;border:0;border-radius:8px;background:#2756d6;color:#fff;font:inherit;cursor:pointer}} #score{{font-weight:600}}
</style></head><body><main>
<h1>{html.escape(title)}</h1><p id="score" aria-live="polite"></p><div id="qs"></div>
<script>
const Q={data};let right=0,done=0;const box=document.getElementById("qs"),score=document.getElementById("score");
function note(){{score.textContent=done?`You have answered ${{done}} of ${{Q.length}}; ${{right}} marked correct.`:`${{Q.length}} questions. Choose an answer to see feedback.`}}
function fb(el,html){{let f=el.querySelector(".fb");if(!f){{f=document.createElement("div");f.className="fb";el.appendChild(f)}}f.innerHTML=html}}
function esc(s){{return String(s).replace(/[&<>"]/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]))}}
Q.forEach(q=>{{const el=document.createElement("section");el.className="q";let h=`<strong>${{q.n}}. ${{esc(q.prompt)}}</strong>`;if(q.image)h+=`<br><img src="${{q.image}}" alt="Picture for question ${{q.n}}">`;el.innerHTML=h;
if(q.kind==="conceptual"){{const t=document.createElement("textarea");t.setAttribute("aria-label","Your answer");el.appendChild(t);const b=document.createElement("button");b.className="go";b.textContent="Show the model answer";
b.onclick=()=>{{if(!t.value.trim()){{fb(el,"Write your answer first, then compare it with the model answer.");return}}if(!el.dataset.done){{el.dataset.done=1;done++;note()}}fb(el,`<b>Model answer:</b> ${{esc(q.model)}}<br>${{esc(q.explanation)}}`)}};el.appendChild(b)}}
else{{q.options.forEach((o,i)=>{{const b=document.createElement("button");b.className="o";b.textContent=o;b.onclick=()=>{{if(el.dataset.done)return;el.dataset.done=1;done++;const ok=i===q.answer;if(ok)right++;
b.classList.add(ok?"right":"wrong");if(!ok)el.querySelectorAll("button.o")[q.answer].classList.add("right");fb(el,`<b>${{ok?"Correct.":"Not quite."}}</b> ${{esc(q.explanation)}}`);note()}};el.appendChild(b)}})}}
box.appendChild(el)}});note();
</script></main></body></html>"""
