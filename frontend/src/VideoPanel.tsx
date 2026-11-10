import { useCallback, useEffect, useState } from "react";
import { ApiError, Issue, Me, video, VideoCaps, VideoSummary } from "./api";
import QualityPanel from "./QualityPanel";

const ACTIVE = ["submitting", "queued", "validating", "awaiting_audio", "generating_audio", "rendering", "finalizing"];
const STATE_TEXT: Record<string, string> = {
  submitting: "Sending to the video service", queued: "Waiting in the queue", validating: "Checking the lesson", awaiting_audio: "Waiting for narration audio",
  generating_audio: "Preparing narration", rendering: "Making the video", finalizing: "Finishing", succeeded: "Ready", failed: "Failed", cancelled: "Cancelled",
};
const mb = (n: number) => (n < 1048576 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1048576).toFixed(1)} MB`);

export default function VideoPanel({ versionId, approved, me }: { versionId: string; approved: boolean; me: Me }) {
  const [s, setS] = useState<VideoSummary | null>(null);
  const [caps, setCaps] = useState<VideoCaps | null>(null);
  const [err, setErr] = useState("");
  const [issues, setIssues] = useState<Issue[]>([]);
  const [busy, setBusy] = useState(false);
  const [provider, setProvider] = useState("azure");
  const [profile, setProfile] = useState("480p24");
  const [subtitles, setSubtitles] = useState(true);
  const [style, setStyle] = useState("animated");
  const [speed, setSpeed] = useState("normal");
  const [audio, setAudio] = useState<File | null>(null);
  const can = me.roles.includes("admin") || me.roles.includes("production_operator");

  const load = useCallback(async () => {
    try { setS(await video.get(versionId)); } catch (e) { setErr((e as ApiError).message); }
  }, [versionId]);
  // reload when the version changes, and when its approval changes (the summary says whether video can be made)
  useEffect(() => { setS(null); setErr(""); setIssues([]); load(); video.caps().then(setCaps).catch(() => undefined); }, [load, approved]);
  const active = !!s?.job && ACTIVE.includes(s.job.state);
  useEffect(() => {
    if (!active) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [active, load]);

  const run = async (fn: () => Promise<VideoSummary>) => {
    setBusy(true); setErr(""); setIssues([]);
    try { setS(await fn()); } catch (e) { const a = e as ApiError; setErr(a.message); setIssues(a.issues ?? []); } finally { setBusy(false); }
  };

  if (!approved) return <p className="muted">Video production becomes available when this version is approved.</p>;
  const job = s?.job ?? null;
  const azure = caps?.providers.find((p) => p.name === "azure");
  return (
    <div>
      <h4>5. Make the video</h4>
      {err && <div className="err" role="alert">{err}</div>}
      {issues.length > 0 && <ul className="err" role="alert">{issues.map((i, n) => <li key={n}>{i.message}</li>)}</ul>}

      {(!job || !active) && can && (
        <div className="row">
          <label>Voice
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              <option value="colab">Google Colab (you upload the narration)</option>
              <option value="azure" disabled={azure ? !azure.configured : false}>Azure voice{azure && !azure.configured ? " (not set up)" : ""}</option>
            </select>
          </label>
          <label>Slides
            <select value={style} onChange={(e) => setStyle(e.target.value)}>
              <option value="animated">Animated (recommended)</option><option value="plain">Plain</option>
            </select>
          </label>
          <label>Narration speed
            <select value={speed} onChange={(e) => setSpeed(e.target.value)}>
              <option value="slow">Slow</option><option value="normal">Normal</option><option value="fast">Fast</option>
            </select>
          </label>
          <label>Quality
            <select value={profile} onChange={(e) => setProfile(e.target.value)}>
              <option value="480p24">Standard (480p, fastest)</option><option value="720p24">HD (720p)</option><option value="1080p24">Full HD (1080p)</option>
            </select>
          </label>
          <label style={{ gridAutoFlow: "column", alignItems: "center", display: "inline-flex", gap: 6 }}>
            <input type="checkbox" style={{ minWidth: 0 }} checked={subtitles} onChange={(e) => setSubtitles(e.target.checked)} />Subtitles
          </label>
          <button className="primary" disabled={busy || !(s?.can_generate ?? true)} onClick={() => run(() => video.generate(versionId, { provider, profile, subtitles, style, speed, rerender: job?.state === "succeeded" }))}>
            {job?.state === "succeeded" ? "Make the video again" : "Generate video"}
          </button>
        </div>
      )}
      {!can && !job && <p className="muted">Ask a production operator to generate the video.</p>}
      {s && !s.can_generate && s.blocked_reason && !active && <p className="muted">{s.blocked_reason}</p>}

      {job && (
        <div className="card" style={{ marginTop: 12 }}>
          <p><span className={`chip ${job.state === "succeeded" ? "approved" : job.state === "failed" ? "changes_required" : "in_review"}`}>{STATE_TEXT[job.state] ?? job.state}</span>
            {" "}<span className="muted">{job.settings.provider === "colab" ? "Colab voice" : "Azure voice"}, {({ "1080p24": "Full HD", "720p24": "HD", "480p24": "Standard 480p" } as Record<string, string>)[job.settings.profile] ?? job.settings.profile}, {job.settings.style === "animated" ? "animated slides" : "plain slides"}</span></p>
          {active && job.state !== "awaiting_audio" && (
            <div aria-label="Progress" style={{ background: "var(--line)", borderRadius: 6, height: 12, maxWidth: 480 }}>
              <div style={{ width: `${Math.max(4, job.percent)}%`, height: 12, borderRadius: 6, background: "var(--accent)" }} />
            </div>
          )}
          {active && job.state !== "awaiting_audio" && <p className="muted">{job.percent}%. You can leave this page; the video keeps being made.</p>}

          {job.state === "awaiting_audio" && (
            <ol>
              <li><a href={`/api/video-jobs/${job.id}/narration-batch`} download="narration-batch.json">Download the narration file</a></li>
              <li>Open the Colab notebook (<code>notebooks/colab_tts.ipynb</code>), upload that file and run it. It gives you <code>narration_audio.zip</code>.</li>
              <li>Upload that ZIP here:{" "}
                <input type="file" accept=".zip" onChange={(e) => setAudio(e.target.files?.[0] ?? null)} />{" "}
                <button className="primary" disabled={!audio || busy || !can} onClick={() => audio && run(() => video.uploadAudio(job.id, audio))}>Upload narration</button>
              </li>
            </ol>
          )}

          {job.state === "failed" && <>
            <p className="err" role="alert">{job.error_message}</p>
            {job.retryable && can && <button className="primary" disabled={busy} onClick={() => run(() => video.retry(job.id))}>Try again</button>}
          </>}
          {active && can && <button className="link" disabled={busy} onClick={() => run(() => video.cancel(job.id))}>Cancel</button>}

          {job.state === "succeeded" && <>
            <video controls preload="metadata" style={{ width: "100%", maxWidth: 800, borderRadius: 8, background: "#000" }} src={`/api/video-jobs/${job.id}/download`} />
            <p><a className="primary" style={{ display: "inline-block", padding: "9px 16px", borderRadius: 6, background: "var(--accent)", color: "#fff", textDecoration: "none" }}
                  href={`/api/video-jobs/${job.id}/download`} download>Download MP4</a></p>
            <ul>{(s?.assets ?? []).map((a) => (
              <li key={a.id}><a href={`/api/video-jobs/${job.id}/assets/${a.id}`}>{a.filename}</a>{" "}
                <span className="muted">{a.kind === "video" ? `${a.width}x${a.height}, ${a.fps} fps, ${Math.round(a.duration_seconds ?? 0)} s, ` : ""}{mb(a.size_bytes)}</span></li>))}
            </ul>
            {(s?.assets ?? []).some((a) => a.kind === "quality_report") && <QualityPanel jobId={job.id} />}
          </>}
        </div>
      )}
      {s && s.history.length > 0 && <p className="muted">Earlier attempts: {s.history.map((h) => `${STATE_TEXT[h.state] ?? h.state} (${new Date(h.created_at).toLocaleString()})`).join("; ")}</p>}
    </div>
  );
}
