import { useCallback, useEffect, useState } from "react";
import { ApiError, Detail, ImportSummary, Issue, LANGUAGES, Me, versions } from "./api";
import SlideEditor from "./SlideEditor";
import VideoPanel from "./VideoPanel";

const langName = (c: string) => LANGUAGES.find((l) => l.code === c)?.label ?? c;
const pretty = (s: string) => s.replace(/_/g, " ");

function IssueList({ issues }: { issues: Issue[] }) {
  if (!issues.length) return null;
  return (
    <ul className="err" role="alert">
      {issues.map((i, n) => <li key={n}>{i.row ? `Row ${i.row}: ` : ""}{i.message}</li>)}
    </ul>
  );
}

export default function VersionPanel({ versionId, me, onChanged }: { versionId: string; me: Me; onChanged: () => void }) {
  const [d, setD] = useState<Detail | null>(null);
  const [err, setErr] = useState("");
  const [issues, setIssues] = useState<Issue[]>([]);
  const [summary, setSummary] = useState<ImportSummary | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [prompt, setPrompt] = useState("");
  const [note, setNote] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const can = (...roles: string[]) => me.roles.includes("admin") || roles.some((r) => me.roles.includes(r));

  const load = useCallback(async () => {
    try { setD(await versions.get(versionId)); } catch (e) { setErr((e as ApiError).message); }
  }, [versionId]);
  useEffect(() => { setSummary(null); setIssues([]); setPrompt(""); setFiles([]); load(); }, [load]);

  const doImport = async (dryRun: boolean) => {
    setErr(""); setIssues([]); setSummary(null);
    try { setSummary(await versions.importFiles(versionId, files, dryRun)); if (!dryRun) { await load(); onChanged(); } }
    catch (e) { const a = e as ApiError; setErr(a.message); setIssues(a.issues ?? []); }
  };
  const act = async (action: string) => {
    setErr("");
    try { setD(await versions.review(versionId, action, note)); setNote(""); onChanged(); } catch (e) { setErr((e as ApiError).message); }
  };
  if (!d) return <div className="card">{err ? <div className="err">{err}</div> : "Loading..."}</div>;

  const s = d.review_status;
  return (
    <div className="card">
      <h3>{d.lesson_title} <span className="muted">({langName(d.language)})</span> <span className={`chip ${s}`}>{pretty(s)}</span></h3>
      {d.review_note && <p className="muted">Reviewer note: {d.review_note}</p>}
      {err && <div className="err" role="alert">{err}</div>}
      <IssueList issues={issues} />

      <h4>1. Get the content</h4>
      <p className="muted">Copy the prompt into ChatGPT yourself, then save the two files it returns.</p>
      <button className="link" onClick={async () => setPrompt(prompt ? "" : await versions.promptSpec(versionId))}>{prompt ? "Hide prompt" : "Show ChatGPT prompt"}</button>
      {prompt && <>
        <textarea readOnly rows={10} style={{ width: "100%" }} value={prompt} />
        <button className="link" onClick={() => navigator.clipboard?.writeText(prompt)}>Copy prompt</button>
      </>}

      {can("content_operator") && <>
        <h4>2. Import</h4>
        <div className="row">
          <label>A ZIP, or lesson.csv with an optional lesson_plan.json
            <input type="file" multiple accept=".zip,.csv,.json" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
          </label>
          <button className="primary" disabled={!files.length} onClick={() => doImport(true)}>Check only</button>
          <button className="primary" disabled={!files.length} onClick={() => doImport(false)}>Import</button>
        </div>
        {summary && <p>{summary.dry_run ? "Looks good (nothing saved)." : "Imported."} {summary.slides} slides, about {summary.estimated_minutes} minutes of narration.
          {summary.warnings.map((w, i) => <span key={i} className="muted"><br />Note: {w.message}</span>)}</p>}
      </>}

      {d.has_content && <>
        <h4>3. Review the content</h4>
        <p className="muted">{d.slides.length} slides, {d.word_count} words.</p>
        {d.learning_objectives.length > 0 && <><strong>Learning objectives</strong><ul>{d.learning_objectives.map((o) => <li key={o}>{o}</li>)}</ul></>}
        <table>
          <thead><tr><th>#</th><th>Module</th><th>Narration</th><th>Subtitle</th><th>Visual</th>{can("content_operator") && <th></th>}</tr></thead>
          <tbody>{d.slides.map((x) => <tr key={x.slide}><td>{x.slide}</td><td>{x.module}</td><td>{x.voice_text}</td><td>{x.subtitle_text}</td><td>{x.visual_instruction}</td>{can("content_operator") && <td><button className="link" onClick={() => setEditing(x.slide)}>Edit</button></td>}</tr>)}</tbody>
        </table>
        {editing !== null && d.slides.find((x) => x.slide === editing) && <SlideEditor versionId={versionId} row={d.slides.find((x) => x.slide === editing)!} onSaved={() => { load(); onChanged(); }} onClose={() => setEditing(null)} />}
        {d.quiz.length > 0 && <><strong>Quiz</strong><ul>{d.quiz.map((q, i) => <li key={i}>{q.question}</li>)}</ul></>}
        {d.source_references.length > 0 && <><strong>Sources</strong><ul>{d.source_references.map((q) => <li key={q}>{q}</li>)}</ul></>}

        <h4>4. Decision</h4>
        <div className="row">
          <label>Note (required for changes or rejection)<input value={note} onChange={(e) => setNote(e.target.value)} /></label>
          {can("content_operator") && (s === "draft" || s === "changes_required") && <button className="primary" onClick={() => act("submit")}>Send for review</button>}
          {can("reviewer") && s === "in_review" && <>
            <button className="primary" onClick={() => act("approve")}>Approve</button>
            <button className="primary" onClick={() => act("request_changes")}>Request changes</button>
            <button className="primary" onClick={() => act("reject")}>Reject</button>
          </>}
          {can("content_operator") && (s === "approved" || s === "rejected") && <button className="primary" onClick={() => act("reopen")}>Reopen as draft</button>}
        </div>
      </>}

      {d.has_content && <VideoPanel versionId={versionId} approved={s === "approved"} me={me} />}

      {d.events.length > 0 && <>
        <h4>History</h4>
        <ul>{d.events.map((e, i) => <li key={i}>{new Date(e.at).toLocaleString()}: {pretty(e.action)} ({pretty(e.from)} to {pretty(e.to)}){e.note ? ` - ${e.note}` : ""}</li>)}</ul>
      </>}
    </div>
  );
}
