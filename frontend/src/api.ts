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

export class ApiError extends Error {}

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
      else if (Array.isArray(data.detail)) detail = data.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch { /* keep default */ }
    throw new ApiError(detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  list: <T,>(path: string) => call<T[]>("GET", path),
  create: <T,>(path: string, body: unknown) => call<T>("POST", path, body),
  remove: (path: string) => call<void>("DELETE", path),
};
