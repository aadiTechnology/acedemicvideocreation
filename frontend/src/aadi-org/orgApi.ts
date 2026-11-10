// Calls to the kit's /org API. The product mounts the router under its own prefix (for example /api).
export interface OrgMember {
  id: string | number; user_id: string | null; email: string; name: string; title: string; status: string;
  role_id: string | number; role: string | null; role_name: string | null; department_id: string | number | null; department: string | null;
  manager_id: string | number | null; manager: string | null;
}
export interface OrgIntegration { ok: boolean; message?: string }
export type OrgAdded = OrgMember & { integration?: OrgIntegration }
export interface OrgDepartment { id: string | number; name: string; parent_id: string | number | null; head_member_id: string | number | null; members: number }
export interface OrgRole { id: string | number; key: string; name: string; description: string; caps: string[]; is_system: boolean; members: number }
export interface OrgCapability { key: string; label: string; scopes: string[]; feature: string }
export interface OrgMatrix { product: string; features: Record<string, string>; admin_role: string; capabilities: OrgCapability[]; roles: { id: string | number; key: string; name: string; is_system: boolean; grants: Record<string, string> }[] }
export interface OrgAuditItem { id: number; actor: string; action: string; entity: string; entity_id: string; detail: Record<string, unknown>; at: string }
export interface OrgMe { member: OrgMember; caps: string[]; product: string }

export class OrgError extends Error {}

export function orgApi(base = "/api") {
  async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${base}/org${path}`, {
      method, credentials: "same-origin",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      let msg = `Request failed (${res.status})`;
      try { const d = await res.json(); if (typeof d.detail === "string") msg = d.detail; } catch { /* keep the generic message */ }
      throw new OrgError(msg);
    }
    return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
  }
  return {
    me: () => call<OrgMe>("GET", "/me"),
    users: () => call<OrgMember[]>("GET", "/users"),
    addUser: (b: { email: string; name?: string; title?: string; role_id?: string | number | null; department_id?: string | number | null }) => call<OrgAdded>("POST", "/users", b),
    patchUser: (id: string | number, b: Record<string, unknown>) => call<OrgMember>("PATCH", `/users/${id}`, b),
    suspend: (id: string | number) => call<OrgAdded>("POST", `/users/${id}/suspend`),
    reactivate: (id: string | number) => call<OrgAdded>("POST", `/users/${id}/reactivate`),
    departments: () => call<OrgDepartment[]>("GET", "/departments"),
    addDepartment: (b: { name: string; parent_id?: string | number | null }) => call<OrgDepartment>("POST", "/departments", b),
    patchDepartment: (id: string | number, b: Record<string, unknown>) => call<OrgDepartment>("PATCH", `/departments/${id}`, b),
    deleteDepartment: (id: string | number) => call<void>("DELETE", `/departments/${id}`),
    roles: () => call<OrgRole[]>("GET", "/roles"),
    addRole: (b: { key: string; name: string; caps: string[] }) => call<OrgRole>("POST", "/roles", b),
    setRole: (id: string | number, b: { name?: string; caps?: string[] }) => call<OrgRole>("PUT", `/roles/${id}`, b),
    deleteRole: (id: string | number) => call<void>("DELETE", `/roles/${id}`),
    matrix: () => call<OrgMatrix>("GET", "/matrix"),
    audit: () => call<{ total: number; items: OrgAuditItem[] }>("GET", "/audit?limit=100"),
  };
}
