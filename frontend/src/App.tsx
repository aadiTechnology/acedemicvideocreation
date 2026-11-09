import { useCallback, useEffect, useState } from "react";
import { api, ApiError, LANGUAGES, Language, LessonRow, Me, Named, versions } from "./api";
import VersionPanel from "./VersionPanel";

type Tab = "lessons" | "structure";

const label = (code: string) => LANGUAGES.find((l) => l.code === code)?.label ?? code;
const statusText = (s: string) => s.replace("_", " ");

function useStructure() {
  const [classes, setClasses] = useState<Named[]>([]);
  const [subjects, setSubjects] = useState<Named[]>([]);
  const [chapters, setChapters] = useState<Named[]>([]);
  const [topics, setTopics] = useState<Named[]>([]);
  const reload = useCallback(async () => {
    const [c, s, ch, t] = await Promise.all([
      api.list<Named>("/classes"), api.list<Named>("/subjects"), api.list<Named>("/chapters"), api.list<Named>("/topics"),
    ]);
    setClasses(c); setSubjects(s); setChapters(ch); setTopics(t);
  }, []);
  useEffect(() => { reload().catch(() => undefined); }, [reload]);
  return { classes, subjects, chapters, topics, reload };
}

function Errors({ message }: { message: string }) {
  return message ? <div className="err" role="alert">{message}</div> : null;
}

function StructureTab({ s }: { s: ReturnType<typeof useStructure> }) {
  const [err, setErr] = useState("");
  const [name, setName] = useState({ cls: "", subject: "", chapterNo: "", chapter: "", topic: "" });
  const [parent, setParent] = useState({ cls: "", subject: "", chapter: "" });
  const run = async (fn: () => Promise<unknown>) => {
    setErr("");
    try { await fn(); await s.reload(); } catch (e) { setErr((e as ApiError).message); }
  };
  const subjectsOf = s.subjects.filter((x) => x.class_id === parent.cls);
  const chaptersOf = s.chapters.filter((x) => x.subject_id === parent.subject);
  return (
    <div className="grid2">
      <div className="card">
        <h3>Classes</h3>
        <div className="row">
          <label>New class<input value={name.cls} onChange={(e) => setName({ ...name, cls: e.target.value })} placeholder="Class 7" /></label>
          <button className="primary" disabled={!name.cls} onClick={() => run(async () => { await api.create("/classes", { name: name.cls }); setName({ ...name, cls: "" }); })}>Add</button>
        </div>
        <ul>{s.classes.map((c) => <li key={c.id}>{c.name} <button className="link" onClick={() => run(() => api.remove(`/classes/${c.id}`))}>remove</button></li>)}</ul>
      </div>
      <div className="card">
        <h3>Subjects, chapters, topics</h3>
        <div className="row">
          <label>Class<select value={parent.cls} onChange={(e) => setParent({ cls: e.target.value, subject: "", chapter: "" })}><option value="">Select</option>{s.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
          <label>New subject<input value={name.subject} onChange={(e) => setName({ ...name, subject: e.target.value })} placeholder="Science" /></label>
          <button className="primary" disabled={!parent.cls || !name.subject} onClick={() => run(async () => { await api.create("/subjects", { class_id: parent.cls, name: name.subject }); setName({ ...name, subject: "" }); })}>Add subject</button>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <label>Subject<select value={parent.subject} onChange={(e) => setParent({ ...parent, subject: e.target.value, chapter: "" })}><option value="">Select</option>{subjectsOf.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
          <label>No.<input style={{ minWidth: 60, width: 70 }} value={name.chapterNo} onChange={(e) => setName({ ...name, chapterNo: e.target.value })} /></label>
          <label>New chapter<input value={name.chapter} onChange={(e) => setName({ ...name, chapter: e.target.value })} placeholder="Nutrition in Plants" /></label>
          <button className="primary" disabled={!parent.subject || !name.chapter || !Number(name.chapterNo)} onClick={() => run(async () => { await api.create("/chapters", { subject_id: parent.subject, number: Number(name.chapterNo), title: name.chapter }); setName({ ...name, chapter: "", chapterNo: "" }); })}>Add chapter</button>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <label>Chapter<select value={parent.chapter} onChange={(e) => setParent({ ...parent, chapter: e.target.value })}><option value="">Select</option>{chaptersOf.map((x) => <option key={x.id} value={x.id}>{x.number}. {x.title}</option>)}</select></label>
          <label>New topic<input value={name.topic} onChange={(e) => setName({ ...name, topic: e.target.value })} placeholder="Photosynthesis" /></label>
          <button className="primary" disabled={!parent.chapter || !name.topic} onClick={() => run(async () => { await api.create("/topics", { chapter_id: parent.chapter, title: name.topic }); setName({ ...name, topic: "" }); })}>Add topic</button>
        </div>
        <Errors message={err} />
      </div>
    </div>
  );
}

function NewLesson({ s, onCreated }: { s: ReturnType<typeof useStructure>; onCreated: () => void }) {
  const [f, setF] = useState({ cls: "", subject: "", chapter: "", topic: "", title: "", description: "", objectives: "", minutes: "5" });
  const [langs, setLangs] = useState<Language[]>(["en-IN"]);
  const [err, setErr] = useState("");
  const subjects = s.subjects.filter((x) => x.class_id === f.cls);
  const chapters = s.chapters.filter((x) => x.subject_id === f.subject);
  const topics = s.topics.filter((x) => x.chapter_id === f.chapter);
  const toggle = (c: Language) => setLangs((l) => (l.includes(c) ? l.filter((x) => x !== c) : [...l, c]));
  const submit = async () => {
    setErr("");
    try {
      await api.create("/lessons", {
        topic_id: f.topic, title: f.title, description: f.description, expected_duration_minutes: Number(f.minutes) || 5,
        learning_objectives: f.objectives.split("\n").map((x) => x.trim()).filter(Boolean), languages: langs,
      });
      setF({ ...f, title: "", description: "", objectives: "" });
      onCreated();
    } catch (e) { setErr((e as ApiError).message); }
  };
  return (
    <div className="card">
      <h3>New lesson</h3>
      <div className="row">
        <label>Class<select value={f.cls} onChange={(e) => setF({ ...f, cls: e.target.value, subject: "", chapter: "", topic: "" })}><option value="">Select</option>{s.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <label>Subject<select value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value, chapter: "", topic: "" })}><option value="">Select</option>{subjects.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
        <label>Chapter<select value={f.chapter} onChange={(e) => setF({ ...f, chapter: e.target.value, topic: "" })}><option value="">Select</option>{chapters.map((x) => <option key={x.id} value={x.id}>{x.number}. {x.title}</option>)}</select></label>
        <label>Topic<select value={f.topic} onChange={(e) => setF({ ...f, topic: e.target.value })}><option value="">Select</option>{topics.map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}</select></label>
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <label>Lesson title<input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
        <label>Target minutes<input type="number" min={1} max={120} value={f.minutes} onChange={(e) => setF({ ...f, minutes: e.target.value })} /></label>
        <fieldset style={{ border: 0, padding: 0 }}>
          <legend className="muted" style={{ fontSize: 13 }}>Language versions</legend>
          {LANGUAGES.map((l) => <label key={l.code} style={{ display: "inline-flex", gridAutoFlow: "column", alignItems: "center", gap: 4, marginRight: 12 }}><input type="checkbox" style={{ minWidth: 0 }} checked={langs.includes(l.code)} onChange={() => toggle(l.code)} />{l.label}</label>)}
        </fieldset>
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <label>Description<textarea rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
        <label>Learning objectives (one per line)<textarea rows={2} value={f.objectives} onChange={(e) => setF({ ...f, objectives: e.target.value })} /></label>
        <button className="primary" disabled={!f.topic || !f.title} onClick={submit}>Create lesson</button>
      </div>
      <Errors message={err} />
    </div>
  );
}

function LessonsTab({ s, me }: { s: ReturnType<typeof useStructure>; me: Me }) {
  const [rows, setRows] = useState<LessonRow[]>([]);
  const [language, setLanguage] = useState("");
  const [open, setOpen] = useState<LessonRow | null>(null);
  const [openVersion, setOpenVersion] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(async () => {
    try { setRows(await api.list<LessonRow>(`/lessons${language ? `?language=${language}` : ""}`)); } catch (e) { setErr((e as ApiError).message); }
  }, [language]);
  useEffect(() => { load(); }, [load]);
  const addVersion = async (lesson: LessonRow, code: Language) => {
    setErr("");
    try { await api.create(`/lessons/${lesson.id}/versions`, { language: code }); await load(); setOpen(null); } catch (e) { setErr((e as ApiError).message); }
  };
  return (
    <>
      <NewLesson s={s} onCreated={load} />
      <div className="card">
        <div className="row" style={{ marginBottom: 8 }}>
          <h3 style={{ margin: 0 }}>Lessons</h3>
          <label>Language<select value={language} onChange={(e) => setLanguage(e.target.value)}><option value="">All</option>{LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}</select></label>
        </div>
        <Errors message={err} />
        {rows.length === 0 ? <p className="muted">No lessons yet. Add a class, subject, chapter and topic under Structure, then create a lesson.</p> : (
          <table>
            <thead><tr><th>Class</th><th>Subject</th><th>Chapter</th><th>Topic</th><th>Lesson</th><th>Languages</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="pick" onClick={() => setOpen(open?.id === r.id ? null : r)}>
                  <td>{r.class_name}</td><td>{r.subject_name}</td><td>{r.chapter_number}. {r.chapter_title}</td><td>{r.topic_title}</td><td>{r.title}</td>
                  <td>{r.versions.map((v) => <span key={v.id} className={`chip ${v.review_status}`}>{label(v.language)}: {statusText(v.review_status)}</span>)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {open && (
        <div className="card">
          <h3>{open.title}</h3>
          <p className="muted">{open.description || "No description."} Target {open.expected_duration_minutes} min.</p>
          {open.learning_objectives.length > 0 && <ul>{open.learning_objectives.map((o) => <li key={o}>{o}</li>)}</ul>}
          <p>Add a language version:{" "}
            {LANGUAGES.filter((l) => !open.versions.some((v) => v.language === l.code)).map((l) => <button key={l.code} className="link" style={{ marginRight: 10 }} onClick={() => addVersion(open, l.code)}>{l.label}</button>)}
          </p>
          <p>Open a language version to import and review its content:{" "}
            {open.versions.map((v) => <button key={v.id} className="link" style={{ marginRight: 10 }} onClick={() => setOpenVersion(v.id)}>{label(v.language)} ({statusText(v.review_status)})</button>)}
          </p>
        </div>
      )}
      {open && openVersion && open.versions.some((v) => v.id === openVersion) && <VersionPanel versionId={openVersion} me={me} onChanged={load} />}
    </>
  );
}

export default function App() {
  const [tab, setTab] = useState<Tab>("lessons");
  const s = useStructure();
  const [me, setMe] = useState<Me>({ user_id: "", email: "", name: "", roles: [] });
  useEffect(() => { versions.me().then(setMe); }, []);
  return (
    <>
      <header>
        <h1>Aadi Academic Video Creation</h1>
        <nav>
          <button className={tab === "lessons" ? "on" : ""} onClick={() => setTab("lessons")}>Lessons</button>
          <button className={tab === "structure" ? "on" : ""} onClick={() => setTab("structure")}>Structure</button>
        </nav>
      </header>
      <main>{tab === "lessons" ? <LessonsTab s={s} me={me} /> : <StructureTab s={s} />}</main>
    </>
  );
}
