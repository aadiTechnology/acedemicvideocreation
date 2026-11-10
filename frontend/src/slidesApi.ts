import { ApiError, Slide, call } from "./api";

export interface LayoutInfo { name: string; title: string; purpose: string; required_diagram_keys: string[]; example: { bullets?: string[]; diagram?: unknown } }
export interface SlidePlan { slide: number; headline: string; bullets?: string[]; layout?: string; diagram?: unknown; key_terms?: string[] }
export interface Recommendation { layout: string; score: number; reason: string }
export interface SlideDraft { headline: string; bullets: string[]; layout: string; diagram: unknown | null; key_terms: string[]; module?: string; voice_text?: string; subtitle_text?: string; visual_instruction?: string }

export interface MediaFile { file: string; size: number; kind: "image" | "clip"; used_by: number[] }

export const slides = {
  media: (versionId: string) => call<{ items: MediaFile[]; licences: string[] }>("GET", `/lesson-versions/${versionId}/media`),
  async addMedia(versionId: string, file: File): Promise<{ file: string; name: string; kind: string }> {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`/api/lesson-versions/${versionId}/media`, { method: "POST", credentials: "same-origin", body: form });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new ApiError(typeof data?.detail === "string" ? data.detail : data?.detail?.message ?? `Upload failed (${res.status})`);
    return data;
  },
  layouts: () => call<{ layouts: LayoutInfo[] }>("GET", "/layouts"),
  get: (versionId: string, n: number) => call<{ row: Slide; plan: SlidePlan }>("GET", `/lesson-versions/${versionId}/slides/${n}`),
  save: (versionId: string, n: number, draft: SlideDraft) => call<{ saved: boolean; review_status: string }>("PUT", `/lesson-versions/${versionId}/slides/${n}`, draft),
  recommend: (versionId: string, n: number) => call<{ age_group: string | null; recommendations: Recommendation[] }>("POST", `/lesson-versions/${versionId}/slides/${n}/recommend`, {}),
  async preview(versionId: string, n: number, plan: SlideDraft | null, at: number, captions = false): Promise<string> {
    const res = await fetch(`/api/lesson-versions/${versionId}/slides/${n}/preview`, {
      method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
      body: JSON.stringify({ plan, at, profile: "480p24", subtitles: captions, voice_text: plan?.voice_text, subtitle_text: plan?.subtitle_text, module: plan?.module }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new ApiError(typeof data?.detail === "string" ? data.detail : data?.detail?.message ?? `Preview failed (${res.status})`);
    }
    return URL.createObjectURL(await res.blob());
  },
};
