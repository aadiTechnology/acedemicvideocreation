export type Language = "en-IN" | "hi-IN" | "mr-IN";
export const LANGUAGES: { code: Language; label: string }[] = [
  { code: "en-IN", label: "English" },
  { code: "hi-IN", label: "Hindi" },
  { code: "mr-IN", label: "Marathi" },
];

export interface Named { id: string; name?: string; title?: string; number?: number; class_id?: string; subject_id?: string; chapter_id?: string }
export interface Version { id: string; lesson_id: string; language: Language; review_status: string; publication_status: string | null }
export interface LessonRow {
  id: string; topic_id: string; title: string; description: string; learning_objectives: string[]; target_audience: string;
  expected_duration_minutes: number; source_references: string[]; versions: Version[];
  class_name: string; subject_name: string; chapter_number: number; chapter_title: string; topic_title: string;
}

export interface Issue { code: string; message: string; row?: number; column?: string; severity?: string }
export class ApiError extends Error { issues: Issue[] = []; }

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  if (res.status === 401) {
    window.location.href = "/auth/login";
    throw new ApiError("Signing in...");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") detail = data.detail;
      else if (data.detail && Array.isArray(data.detail.issues)) { const e = new ApiError(data.detail.message); e.issues = data.detail.issues; throw e; }
      else if (Array.isArray(data.detail)) detail = data.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch (e) { if (e instanceof ApiError) throw e; }
    throw new ApiError(detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  list: <T,>(path: string) => call<T[]>("GET", path),
  create: <T,>(path: string, body: unknown) => call<T>("POST", path, body),
  remove: (path: string) => call<void>("DELETE", path),
};

export interface Slide { slide: number; module: string; voice_text: string; subtitle_text: string; visual_instruction: string }
export interface Detail {
  id: string; lesson_title: string; language: Language; review_status: string; review_note: string; reviewed_at: string | null;
  has_content: boolean; slides: Slide[]; learning_objectives: string[]; quiz: { question: string }[]; source_references: string[];
  word_count: number; package_sha256: string | null; imported_at: string | null;
  events: { action: string; from: string; to: string; note: string; actor_id: string; at: string }[];
}
export interface ImportSummary { slides: number; word_count: number; estimated_minutes: number; dry_run: boolean; warnings: Issue[] }
export interface Me { user_id: string; email: string; name: string; roles: string[] }

export const versions = {
  get: (id: string) => call<Detail>("GET", `/lesson-versions/${id}`),
  review: (id: string, action: string, note: string) => call<Detail>("POST", `/lesson-versions/${id}/review`, { action, note }),
  me: () => call<Me>("GET", "/me").catch(() => ({ user_id: "", email: "", name: "", roles: [] as string[] })),
  async promptSpec(id: string): Promise<string> {
    const res = await fetch(`/api/lesson-versions/${id}/prompt-spec`, { credentials: "same-origin" });
    if (!res.ok) throw new ApiError("Could not load the prompt.");
    return res.text();
  },
  async importFiles(id: string, files: File[], dryRun: boolean): Promise<ImportSummary> {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    const res = await fetch(`/api/lesson-versions/${id}/import${dryRun ? "?dry_run=true" : ""}`, { method: "POST", body: form, credentials: "same-origin" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const e = new ApiError(data?.detail?.message ?? (typeof data?.detail === "string" ? data.detail : `Import failed (${res.status})`));
      e.issues = data?.detail?.issues ?? [];
      throw e;
    }
    return data as ImportSummary;
  },
};

export interface VideoJob {
  id: string; state: string; stage: string | null; percent: number; error_code: string | null; error_message: string | null;
  retryable: boolean; awaiting_audio: boolean; settings: { provider: string; mode: string; profile: string; subtitles: boolean };
  created_at: string; finished_at: string | null;
}
export interface VideoAsset { id: string; kind: string; filename: string; size_bytes: number; duration_seconds?: number; width?: number; height?: number; fps?: number }
export interface VideoSummary { job: VideoJob | null; assets: VideoAsset[]; history: VideoJob[]; can_generate: boolean; blocked_reason: string | null }
export interface VideoCaps { providers: { name: string; modes: string[]; configured: boolean }[]; profiles: string[] }

export const video = {
  get: (versionId: string) => call<VideoSummary>("GET", `/lesson-versions/${versionId}/video`),
  caps: () => call<VideoCaps>("GET", "/video/capabilities"),
  generate: (versionId: string, body: { provider: string; profile: string; subtitles: boolean; rerender?: boolean }) =>
    call<VideoSummary>("POST", `/lesson-versions/${versionId}/video`, body),
  retry: (jobId: string) => call<VideoSummary>("POST", `/video-jobs/${jobId}/retry`, {}),
  cancel: (jobId: string) => call<VideoSummary>("POST", `/video-jobs/${jobId}/cancel`, {}),
  async uploadAudio(jobId: string, file: File): Promise<VideoSummary> {
    const form = new FormData();
    form.append("audio", file);
    const res = await fetch(`/api/video-jobs/${jobId}/audio`, { method: "POST", body: form, credentials: "same-origin" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const e = new ApiError(data?.detail?.message ?? (typeof data?.detail === "string" ? data.detail : `Upload failed (${res.status})`));
      e.issues = data?.detail?.issues ?? [];
      throw e;
    }
    return data as VideoSummary;
  },
};
