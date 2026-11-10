import { useEffect, useMemo, useState } from "react";
import { call } from "./api";

interface Check { id: string; category: string; severity: string; slide: number | null; message: string }
interface Report {
  stage: string; result: "pass" | "review" | "fail"; estimate: { score: number; method: string };
  summary: { errors: number; warnings: number; passed: number; slides: number };
  categories: Record<string, { title: string; score: number; errors: number; warnings: number; passed?: number }>;
  checks: Check[]; passed_checks?: Check[]; needs_human: string[];
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
const CHIP: Record<string, string> = { pass: "approved", review: "in_review", fail: "changes_required" };
const RESULT: Record<string, string> = { pass: "Passed", review: "Passed, with points to review", fail: "Problems found" };
const SEVERITY: Record<string, { label: string; order: number }> = {
  error: { label: "Error", order: 0 }, warning: { label: "Warning", order: 1 }, info: { label: "Note", order: 2 }, pass: { label: "Passed", order: 3 },
};
const CATEGORY: Record<string, string> = {
  narration: "Narration", captions: "Captions", visuals: "Visual elements", layout: "Layout", sync: "Diagrams vs narration", coverage: "Objectives and review", duration: "Length",
};

export default function QualityPanel({ jobId }: { jobId: string }) {
  const [r, setR] = useState<Report | null>(null);
  const [gone, setGone] = useState(false);
  const [open, setOpen] = useState<boolean | null>(null); // null: decide from the result
  const [showPassed, setShowPassed] = useState(false);
  const [level, setLevel] = useState("all");
  useEffect(() => {
    setR(null); setGone(false); setOpen(null); setShowPassed(false); setLevel("all");
    call<Report>("GET", `/video-jobs/${jobId}/quality`).then(setR).catch(() => setGone(true));
  }, [jobId]);

  const rows = useMemo(() => {
    if (!r) return [];
    const all = [...r.checks, ...(showPassed ? r.passed_checks ?? [] : [])];
    return all
      .filter((c) => level === "all" || c.severity === level)
      .sort((a, b) => SEVERITY[a.severity].order - SEVERITY[b.severity].order || (a.slide ?? 0) - (b.slide ?? 0));
  }, [r, showPassed, level]);

  if (gone || !r) return null;
  const isOpen = open ?? r.result === "fail"; // problems open by default; a clean report stays folded
  return (
    <div style={{ marginTop: 16 }} aria-label="Quality check">
      <div className="row" style={{ alignItems: "center" }}>
        <strong>Quality check</strong>
        <span className={`chip ${CHIP[r.result]}`}>{RESULT[r.result]}</span>
        <span>{r.estimate.score}/100</span>
        <span className="muted">{plural(r.summary.errors, "error")}, {plural(r.summary.warnings, "warning")}, {r.summary.passed} passed, {plural(r.summary.slides, "slide")}</span>
        <button className="link" aria-expanded={isOpen} onClick={() => setOpen(!isOpen)}>{isOpen ? "Hide quality report" : "Show quality report"}</button>
      </div>
      {isOpen && (
        <div>
          <p className="muted">A rule-based estimate from automatic checks, not a judgement of the lesson.</p>
          <h4>By area</h4>
          <table>
            <thead><tr><th>Area</th><th>Score</th><th>Errors</th><th>Warnings</th><th>Passed</th></tr></thead>
            <tbody>
              {Object.entries(r.categories).map(([k, c]) => (
                <tr key={k}><td>{c.title}</td><td>{c.score}</td><td>{c.errors}</td><td>{c.warnings}</td><td>{c.passed ?? 0}</td></tr>
              ))}
            </tbody>
          </table>
          <h4>Checks</h4>
          <div className="row">
            <label>Show
              <select value={level} onChange={(e) => setLevel(e.target.value)}>
                <option value="all">Everything below</option><option value="error">Errors</option><option value="warning">Warnings</option><option value="info">Notes</option>
                {showPassed && <option value="pass">Passed</option>}
              </select>
            </label>
            <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
              <input type="checkbox" style={{ minWidth: 0 }} checked={showPassed} onChange={(e) => { setShowPassed(e.target.checked); if (!e.target.checked && level === "pass") setLevel("all"); }} />
              Include passed checks
            </label>
          </div>
          {rows.length === 0 ? <p className="muted">Nothing to show for this filter.</p> : (
            <table>
              <thead><tr><th>Slide</th><th>Area</th><th>Result</th><th>Details</th></tr></thead>
              <tbody>
                {rows.map((c, i) => (
                  <tr key={`${c.id}-${c.slide}-${i}`}>
                    <td>{c.slide ?? "All"}</td>
                    <td>{CATEGORY[c.category] ?? c.category}</td>
                    <td><span className={`chip ${c.severity === "error" ? "changes_required" : c.severity === "warning" ? "in_review" : c.severity === "pass" ? "approved" : ""}`}>{SEVERITY[c.severity].label}</span></td>
                    <td>{c.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <h4>A person still has to check</h4>
          <table>
            <thead><tr><th>#</th><th>Item</th></tr></thead>
            <tbody>{r.needs_human.map((t, i) => <tr key={t}><td>{i + 1}</td><td>{t}</td></tr>)}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
