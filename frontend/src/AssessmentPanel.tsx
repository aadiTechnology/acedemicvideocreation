import { useCallback, useEffect, useState } from "react";
import { ApiError, call } from "./api";

type Kind = "multiple_choice" | "image" | "diagram" | "conceptual";
interface Question { id: string; position: number; kind: Kind; prompt: string; options: string[]; image_file: string | null; slide: number | null; status: "draft" | "approved";
  answer_index?: number | null; model_answer?: string; explanation?: string }
interface Listing { questions: Question[]; summary: { count: number; approved: number; complete: boolean; max: number; min_complete: number }; can_edit: boolean; can_approve: boolean; pictures: string[] }
interface Marked { correct: boolean | null; correct_index?: number; model_answer?: string; explanation: string }
interface Draft { kind: Kind; prompt: string; options: string[]; answer_index: number | null; model_answer: string; explanation: string; image_file: string; slide: string }

const KINDS: { value: Kind; label: string }[] = [
  { value: "multiple_choice", label: "Multiple choice" }, { value: "image", label: "Picture question" },
  { value: "diagram", label: "Name the part of a diagram" }, { value: "conceptual", label: "Open question (model answer)" },
];
const EMPTY: Draft = { kind: "multiple_choice", prompt: "", options: ["", "", ""], answer_index: 0, model_answer: "", explanation: "", image_file: "", slide: "" };
const base = (v: string) => `/lesson-versions/${v}/assessment`;

export default function AssessmentPanel({ versionId }: { versionId: string }) {
  const [data, setData] = useState<Listing | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [practice, setPractice] = useState(false);

  const load = useCallback(async () => {
    try { setData(await call<Listing>("GET", base(versionId))); } catch (e) { setErr((e as ApiError).message); }
  }, [versionId]);
  useEffect(() => { setDraft(null); setEditId(null); setPractice(false); setMsg(""); load(); }, [load]);

  const run = async (fn: () => Promise<unknown>, ok = "") => {
    setErr(""); setMsg("");
    try { await fn(); await load(); if (ok) setMsg(ok); } catch (e) { setErr((e as ApiError).message); }
  };
  if (!data) return <p className="muted">{err || "Loading..."}</p>;
  const { summary } = data;
  const body = (d: Draft) => ({
    kind: d.kind, prompt: d.prompt, explanation: d.explanation,
    options: d.kind === "conceptual" ? null : d.options.filter((o) => o.trim()), answer_index: d.kind === "conceptual" ? null : d.answer_index,
    model_answer: d.kind === "conceptual" ? d.model_answer : null, image_file: d.kind === "image" || d.kind === "diagram" ? d.image_file || null : null, slide: d.slide ? Number(d.slide) : null,
  });
  const save = () => draft && run(async () => {
    if (editId) await call("PUT", `${base(versionId)}/${editId}`, body(draft)); else await call("POST", base(versionId), body(draft));
    setDraft(null); setEditId(null);
  }, "Saved. A new or changed question is a draft until a reviewer approves it.");
  const edit = (q: Question) => { setEditId(q.id); setDraft({ kind: q.kind, prompt: q.prompt, options: q.options.length ? q.options : ["", "", ""], answer_index: q.answer_index ?? 0, model_answer: q.model_answer ?? "", explanation: q.explanation ?? "", image_file: q.image_file ?? "", slide: q.slide ? String(q.slide) : "" }); };
  const pictureQuestion = draft && (draft.kind === "image" || draft.kind === "diagram");

  return (
    <div aria-label="Practice questions">
      <p className="muted">{summary.count} of {summary.max} questions, {summary.approved} approved. {summary.complete ? "Ready: this lesson has enough approved questions." : `A lesson is ready with ${summary.min_complete} approved questions.`}</p>
      {err && <p className="err" role="alert">{err}</p>}
      {msg && <p>{msg}</p>}
      <div className="row">
        <button className="primary" onClick={() => setPractice(!practice)} disabled={!data.questions.length}>{practice ? "Back to the list" : "Practise"}</button>
        {summary.approved > 0 && <a className="link" href={`/api${base(versionId)}/export.html`}>Download practice page (HTML)</a>}
        {data.can_edit && summary.count < summary.max && !draft && <button className="primary" onClick={() => { setEditId(null); setDraft({ ...EMPTY, options: [...EMPTY.options] }); }}>Add a question</button>}
        {data.can_edit && summary.count < summary.max && !draft && <button className="link" onClick={() => run(async () => {
          const r = await call<{ created: unknown[]; skipped: string[] }>("POST", `${base(versionId)}/from-plan`, {});
          setMsg(`${r.created.length} question(s) made from the quiz in lesson_plan.json.${r.skipped.length ? ` Skipped: ${r.skipped.join(" ")}` : ""}`);
        })}>Make questions from the imported quiz</button>}
      </div>

      {practice ? <Practice versionId={versionId} questions={data.questions} /> : (
        <>
          {data.questions.length === 0 && <p className="muted">No questions yet.</p>}
          {data.questions.length > 0 && <table>
            <thead><tr><th>#</th><th>Question</th><th>Kind</th><th>Status</th><th></th></tr></thead>
            <tbody>{data.questions.map((q) => (
              <tr key={q.id}><td>{q.position}</td><td>{q.prompt}{q.image_file ? <span className="muted"> ({q.image_file})</span> : null}</td><td>{KINDS.find((k) => k.value === q.kind)?.label}</td>
                <td><span className={`chip ${q.status === "approved" ? "approved" : "draft"}`}>{q.status}</span></td>
                <td>
                  {data.can_edit && <button className="link" onClick={() => edit(q)}>Edit</button>}{" "}
                  {data.can_approve && (q.status === "draft"
                    ? <button className="link" onClick={() => run(() => call("POST", `${base(versionId)}/${q.id}/approve`, {}))}>Approve</button>
                    : <button className="link" onClick={() => run(() => call("POST", `${base(versionId)}/${q.id}/unapprove`, {}))}>Make draft</button>)}{" "}
                  {data.can_edit && <button className="link" onClick={() => run(() => call("DELETE", `${base(versionId)}/${q.id}`))}>Remove</button>}
                </td></tr>))}</tbody>
          </table>}
        </>
      )}

      {draft && !practice && (
        <fieldset aria-label="Question" style={{ border: "1px solid var(--line)", borderRadius: 8, padding: 10, margin: "8px 0" }}>
          <legend>{editId ? "Edit question" : "New question"}</legend>
          <label>Kind
            <select value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value as Kind })}>{KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}</select>
          </label>
          <label>Question<textarea rows={2} maxLength={400} value={draft.prompt} onChange={(e) => setDraft({ ...draft, prompt: e.target.value })} /></label>
          {pictureQuestion && (
            <label>Picture (add pictures in the slide editor, under Pictures and clips)
              <select value={draft.image_file} onChange={(e) => setDraft({ ...draft, image_file: e.target.value })}>
                <option value="">Choose a picture</option>{data.pictures.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </label>
          )}
          {draft.kind !== "conceptual" ? (
            <div>
              <strong>Answer choices (2 to 5), mark the correct one</strong>
              {draft.options.map((o, i) => (
                <div className="row" key={i}>
                  <input type="radio" name="correct" aria-label={`Choice ${i + 1} is correct`} style={{ minWidth: 0 }} checked={draft.answer_index === i} onChange={() => setDraft({ ...draft, answer_index: i })} />
                  <input aria-label={`Choice ${i + 1}`} maxLength={160} value={o} onChange={(e) => setDraft({ ...draft, options: draft.options.map((x, j) => (j === i ? e.target.value : x)) })} />
                </div>))}
              <div className="row">
                {draft.options.length < 5 && <button className="link" onClick={() => setDraft({ ...draft, options: [...draft.options, ""] })}>Add a choice</button>}
                {draft.options.length > 2 && <button className="link" onClick={() => setDraft({ ...draft, options: draft.options.slice(0, -1), answer_index: Math.min(draft.answer_index ?? 0, draft.options.length - 2) })}>Remove the last choice</button>}
              </div>
            </div>
          ) : <label>Model answer<textarea rows={3} value={draft.model_answer} onChange={(e) => setDraft({ ...draft, model_answer: e.target.value })} /></label>}
          <label>Explanation (shown after the learner answers)<textarea rows={3} value={draft.explanation} onChange={(e) => setDraft({ ...draft, explanation: e.target.value })} /></label>
          <label>Slide it belongs to (optional)<input type="number" min={1} value={draft.slide} onChange={(e) => setDraft({ ...draft, slide: e.target.value })} /></label>
          <div className="row"><button className="primary" onClick={save}>Save question</button><button className="link" onClick={() => { setDraft(null); setEditId(null); }}>Cancel</button></div>
        </fieldset>
      )}
    </div>
  );
}

function Practice({ versionId, questions }: { versionId: string; questions: Question[] }) {
  const shown = questions.filter((q) => q.status === "approved");
  const [i, setI] = useState(0);
  const [result, setResult] = useState<Marked | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [score, setScore] = useState({ right: 0, done: 0 });
  const [err, setErr] = useState("");
  if (!shown.length) return <p className="muted">Practice uses approved questions. None are approved yet.</p>;
  if (i >= shown.length) return <p>You answered {score.done} questions; {score.right} were marked correct. <button className="link" onClick={() => { setI(0); setResult(null); setPicked(null); setText(""); setScore({ right: 0, done: 0 }); }}>Practise again</button></p>;
  const q = shown[i];
  const answer = async (body: { choice?: number; text?: string }) => {
    setErr("");
    try {
      const r = await call<Marked>("POST", `${base(versionId)}/${q.id}/answer`, body);
      setResult(r); setScore((s) => ({ right: s.right + (r.correct ? 1 : 0), done: s.done + 1 }));
    } catch (e) { setErr((e as ApiError).message); }
  };
  const next = () => { setI(i + 1); setResult(null); setPicked(null); setText(""); };
  return (
    <div className="card" aria-label={`Question ${i + 1}`}>
      <strong>Question {i + 1} of {shown.length}</strong>
      <p>{q.prompt}</p>
      {q.image_file && <img src={`/api${base(versionId)}/picture/${q.image_file.replace("media/", "")}`} alt={`Picture for question ${i + 1}`} style={{ maxWidth: "100%", borderRadius: 8 }} />}
      {q.kind !== "conceptual" ? (
        <div>{q.options.map((o, n) => {
          const state = result ? (n === result.correct_index ? "right" : n === picked ? "wrong" : "") : "";
          return <button key={n} className={`link ${state}`} disabled={!!result} style={{ display: "block", textAlign: "left", margin: "4px 0", fontWeight: state ? 700 : 400, color: state === "right" ? "#1b7a3d" : state === "wrong" ? "#b3261e" : undefined }}
            onClick={() => { setPicked(n); answer({ choice: n }); }}>{String.fromCharCode(65 + n)}. {o}</button>;
        })}</div>
      ) : (
        <div><textarea aria-label="Your answer" rows={3} value={text} disabled={!!result} onChange={(e) => setText(e.target.value)} />
          {!result && <button className="primary" onClick={() => answer({ text })}>Show the model answer</button>}</div>
      )}
      {err && <p className="err" role="alert">{err}</p>}
      {result && <div role="status">
        {result.correct === true && <p><strong>Correct.</strong></p>}
        {result.correct === false && <p><strong>Not quite.</strong></p>}
        {result.model_answer && <p><strong>Model answer:</strong> {result.model_answer}</p>}
        <p>{result.explanation}</p>
        <button className="primary" onClick={next}>{i + 1 < shown.length ? "Next question" : "Finish"}</button>
      </div>}
    </div>
  );
}
