import { useEffect, useState } from "react";
import { call } from "./api";

interface Check { id: string; category: string; severity: string; slide: number | null; message: string }
interface Report {
  stage: string; result: "pass" | "review" | "fail"; estimate: { score: number; method: string };
  summary: { errors: number; warnings: number; passed: number; slides: number };
  categories: Record<string, { title: string; score: number; errors: number; warnings: number }>;
  checks: Check[]; needs_human: string[];
}

const CHIP: Record<string, string> = { pass: "approved", review: "in_review", fail: "changes_required" };
const RESULT: Record<string, string> = { pass: "Passed", review: "Passed, with points to review", fail: "Problems found" };

export default function QualityPanel({ jobId }: { jobId: string }) {
  const [r, setR] = useState<Report | null>(null);
  const [gone, setGone] = useState(false);
  useEffect(() => {
    setR(null); setGone(false);
    call<Report>("GET", `/video-jobs/${jobId}/quality`).then(setR).catch(() => setGone(true));
  }, [jobId]);
  if (gone || !r) return null;
  const issues = r.checks.filter((c) => c.severity === "error" || c.severity === "warning");
  const notes = r.checks.filter((c) => c.severity === "info");
  return (
    <div style={{ marginTop: 16 }} aria-label="Quality check">
      <strong>Quality check</strong>{" "}
      <span className={`chip ${CHIP[r.result]}`}>{RESULT[r.result]}</span>
      <p className="muted">
        Estimate {r.estimate.score}/100 from {r.summary.passed + issues.length + notes.length} automatic checks over {r.summary.slides} slides:
        {" "}{r.summary.errors} errors, {r.summary.warnings} warnings. It is a rule-based score, not a judgement of the lesson.
      </p>
      <table>
        <thead><tr><th>Area</th><th>Score</th><th>Errors</th><th>Warnings</th></tr></thead>
        <tbody>{Object.entries(r.categories).map(([k, c]) => <tr key={k}><td>{c.title}</td><td>{c.score}</td><td>{c.errors}</td><td>{c.warnings}</td></tr>)}</tbody>
      </table>
      {issues.length > 0 && <ul>{issues.map((c, i) => <li key={i} className={c.severity === "error" ? "err" : undefined}>{c.slide ? `Slide ${c.slide}: ` : ""}{c.message}</li>)}</ul>}
      {notes.length > 0 && <ul className="muted">{notes.map((c, i) => <li key={i}>{c.message}</li>)}</ul>}
      <details><summary>What a person still has to check</summary><ul>{r.needs_human.map((t) => <li key={t}>{t}</li>)}</ul></details>
    </div>
  );
}
