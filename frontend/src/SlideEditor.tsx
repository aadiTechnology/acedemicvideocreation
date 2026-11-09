import { useEffect, useRef, useState } from "react";
import { ApiError, Slide } from "./api";
import { LayoutInfo, Recommendation, SlideDraft, slides } from "./slidesApi";

export default function SlideEditor({ versionId, row, onSaved, onClose }: { versionId: string; row: Slide; onSaved: () => void; onClose: () => void }) {
  const [layouts, setLayouts] = useState<LayoutInfo[]>([]);
  const [layout, setLayout] = useState("bullets");
  const [headline, setHeadline] = useState("");
  const [bullets, setBullets] = useState("");
  const [diagram, setDiagram] = useState("");
  const [at, setAt] = useState(0.92);
  const [img, setImg] = useState("");
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const last = useRef("");

  useEffect(() => {
    setErr(""); setMsg(""); setImg(""); setRecs([]);
    (async () => {
      try {
        const [l, s] = await Promise.all([slides.layouts(), slides.get(versionId, row.slide)]);
        setLayouts(l.layouts);
        setLayout(s.plan.layout ?? "bullets");
        setHeadline(s.plan.headline ?? row.module);
        setBullets((s.plan.bullets ?? []).join("\n"));
        setDiagram(s.plan.diagram ? JSON.stringify(s.plan.diagram, null, 2) : "");
      } catch (e) { setErr((e as ApiError).message); }
    })();
  }, [versionId, row.slide, row.module]);

  const info = layouts.find((l) => l.name === layout);
  function draft(): SlideDraft | null {
    let parsed: unknown = null;
    if (diagram.trim()) {
      try { parsed = JSON.parse(diagram); } catch { setErr("The diagram is not valid JSON."); return null; }
    }
    return { headline: headline.trim(), bullets: bullets.split("\n").map((b) => b.trim()).filter(Boolean), layout, diagram: parsed };
  }
  function pickLayout(name: string) {
    setLayout(name);
    const ex = layouts.find((l) => l.name === name)?.example;
    if (ex?.diagram && !diagram.trim()) setDiagram(JSON.stringify(ex.diagram, null, 2));
    if (ex?.bullets && !bullets.trim()) setBullets(ex.bullets.join("\n"));
  }
  async function run(fn: () => Promise<void>) {
    setBusy(true); setErr(""); setMsg("");
    try { await fn(); } catch (e) { setErr((e as ApiError).message); } finally { setBusy(false); }
  }
  const preview = () => run(async () => {
    const d = draft(); if (!d) return;
    const url = await slides.preview(versionId, row.slide, d, at);
    if (last.current) URL.revokeObjectURL(last.current);
    last.current = url; setImg(url);
  });
  const recommend = () => run(async () => setRecs((await slides.recommend(versionId, row.slide)).recommendations));
  const save = () => run(async () => {
    const d = draft(); if (!d) return;
    const r = await slides.save(versionId, row.slide, d);
    setMsg(r.review_status === "draft" ? "Saved. The version is a draft again and needs a new review." : "Saved.");
    onSaved();
  });

  return (
    <div className="card" aria-label={`Edit slide ${row.slide}`}>
      <div className="row"><strong>Edit slide {row.slide}: {row.module}</strong><button className="link" onClick={onClose}>Close</button></div>
      <div className="grid2">
        <div>
          <label>Layout
            <select value={layout} onChange={(e) => pickLayout(e.target.value)}>
              {(layouts.length ? layouts : [{ name: "bullets", title: "Key points" } as LayoutInfo]).map((l) => <option key={l.name} value={l.name}>{l.title}</option>)}
            </select>
          </label>
          {info && <p className="muted">{info.purpose}{info.required_diagram_keys.length ? ` Needs: ${info.required_diagram_keys.join(", ")}.` : ""}</p>}
          <label>Headline<input value={headline} maxLength={100} onChange={(e) => setHeadline(e.target.value)} /></label>
          <label>Bullets (one per line)<textarea rows={4} value={bullets} onChange={(e) => setBullets(e.target.value)} /></label>
          <label>Diagram (JSON, only for layouts that need it)<textarea rows={8} spellCheck={false} value={diagram} onChange={(e) => setDiagram(e.target.value)} /></label>
          <div className="row">
            <button className="primary" disabled={busy} onClick={recommend}>Suggest a layout</button>
            <button className="primary" disabled={busy} onClick={preview}>Preview</button>
            <button className="primary" disabled={busy || !headline.trim()} onClick={save}>Save slide</button>
          </div>
          {recs.length > 0 && <ul>{recs.map((r) => <li key={r.layout}><button className="link" onClick={() => pickLayout(r.layout)}>{layouts.find((l) => l.name === r.layout)?.title ?? r.layout}</button> <span className="muted">{r.reason}</span></li>)}</ul>}
          {err && <p className="err" role="alert">{err}</p>}
          {msg && <p>{msg}</p>}
        </div>
        <div>
          <label>Moment shown ({Math.round(at * 100)}% of the slide)
            <input type="range" min={0.05} max={1} step={0.05} value={at} onChange={(e) => setAt(Number(e.target.value))} />
          </label>
          {img ? <img src={img} alt={`Preview of slide ${row.slide}`} style={{ width: "100%", borderRadius: 8, border: "1px solid var(--line)" }} /> : <p className="muted">Press Preview to see the slide as it will appear in the video.</p>}
        </div>
      </div>
    </div>
  );
}
