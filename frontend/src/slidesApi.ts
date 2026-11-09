import { ApiError, Slide, call } from "./api";

export interface LayoutInfo { name: string; title: string; purpose: string; required_diagram_keys: string[]; example: { bullets?: string[]; diagram?: unknown } }
export interface SlidePlan { slide: number; headline: string; bullets?: string[]; layout?: string; diagram?: unknown }
export interface Recommendation { layout: string; score: number; reason: string }
export interface SlideDraft { headline: string; bullets: string[]; layout: string; diagram: unknown | null }

export const slides = {
  layouts: () => call<{ layouts: LayoutInfo[] }>("GET", "/layouts"),
  get: (versionId: string, n: number) => call<{ row: Slide; plan: SlidePlan }>("GET", `/lesson-versions/${versionId}/slides/${n}`),
  save: (versionId: string, n: number, draft: SlideDraft) => call<{ saved: boolean; review_status: string }>("PUT", `/lesson-versions/${versionId}/slides/${n}`, draft),
  recommend: (versionId: string, n: number) => call<{ age_group: string | null; recommendations: Recommendation[] }>("POST", `/lesson-versions/${versionId}/slides/${n}/recommend`, {}),
  async preview(versionId: string, n: number, plan: SlideDraft | null, at: number): Promise<string> {
    const res = await fetch(`/api/lesson-versions/${versionId}/slides/${n}/preview`, {
      method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
      body: JSON.stringify({ plan, at, profile: "480p24", subtitles: false }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new ApiError(typeof data?.detail === "string" ? data.detail : data?.detail?.message ?? `Preview failed (${res.status})`);
    }
    return URL.createObjectURL(await res.blob());
  },
};
