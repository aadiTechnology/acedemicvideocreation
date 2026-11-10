import { useCallback, useEffect, useMemo, useState } from "react";
import { OrgAuditItem, OrgDepartment, OrgError, OrgMatrix, OrgMe, OrgMember, OrgRole, orgApi } from "./orgApi";

type Tab = "people" | "departments" | "roles" | "activity";
const TABS: { id: Tab; label: string; cap: string }[] = [
  { id: "people", label: "People", cap: "org.users.view" }, { id: "departments", label: "Departments", cap: "org.users.view" },
  { id: "roles", label: "Roles and features", cap: "org.users.view" }, { id: "activity", label: "Activity", cap: "audit.view" },
];
const STATUS_CHIP: Record<string, string> = { active: "approved", invited: "in_review", suspended: "changes_required" };

export default function OrgAdmin({ base = "/api", title = "People and roles" }: { base?: string; title?: string }) {
  const api = useMemo(() => orgApi(base), [base]);
  const [me, setMe] = useState<OrgMe | null>(null);
  const [tab, setTab] = useState<Tab>("people");
  const [err, setErr] = useState("");
  useEffect(() => { api.me().then(setMe).catch((e) => setErr((e as Error).message)); }, [api]);
  if (err && !me) return <div className="card"><p className="err" role="alert">{err}</p></div>;
  if (!me) return <div className="card"><p className="muted">Loading...</p></div>;
  const can = (c: string) => me.caps.includes(c);
  const tabs = TABS.filter((t) => can(t.cap));
  return (
    <div className="card" aria-label={title}>
      <h3>{title}</h3>
      <div className="row" role="tablist">
        {tabs.map((t) => <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? "primary" : "link"} onClick={() => setTab(t.id)}>{t.label}</button>)}
      </div>
      {tab === "people" && <People api={api} can={can} />}
      {tab === "departments" && <Departments api={api} can={can} />}
      {tab === "roles" && <Roles api={api} can={can} />}
      {tab === "activity" && <Activity api={api} />}
    </div>
  );
}

type Api = ReturnType<typeof orgApi>;
type Can = (c: string) => boolean;

function useLoad<T>(fn: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(async () => { try { setData(await fn()); } catch (e) { setErr((e as Error).message); } }, [fn]);
  useEffect(() => { load(); }, [load]);
  return { data, err, setErr, load };
}

function People({ api, can }: { api: Api; can: Can }) {
  const users = useLoad<OrgMember[]>(api.users);
  const roles = useLoad<OrgRole[]>(api.roles);
  const depts = useLoad<OrgDepartment[]>(api.departments);
  const [f, setF] = useState({ email: "", name: "", title: "", role_id: "", department_id: "" });
  const [msg, setMsg] = useState("");
  const manage = can("org.users.manage");
  const run = async (fn: () => Promise<unknown>) => { users.setErr(""); setMsg(""); try { await fn(); await users.load(); await depts.load(); } catch (e) { users.setErr((e as OrgError).message); } };
  return (
    <div>
      {manage && (
        <div className="row" style={{ margin: "12px 0" }}>
          <label>Email<input value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></label>
          <label>Name<input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
          <label>Title<input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
          <label>Role<select value={f.role_id} onChange={(e) => setF({ ...f, role_id: e.target.value })}><option value="">Default</option>{(roles.data ?? []).map((r) => <option key={r.id} value={String(r.id)}>{r.name}</option>)}</select></label>
          <label>Department<select value={f.department_id} onChange={(e) => setF({ ...f, department_id: e.target.value })}><option value="">None</option>{(depts.data ?? []).map((d) => <option key={d.id} value={String(d.id)}>{d.name}</option>)}</select></label>
          <button className="primary" disabled={!f.email.includes("@")} onClick={() => run(async () => {
            const added = await api.addUser({ email: f.email, name: f.name, title: f.title, role_id: f.role_id || null, department_id: f.department_id || null });
            setF({ email: "", name: "", title: "", role_id: "", department_id: "" });
            setMsg(added.integration ? (added.integration.ok ? `Added. ${added.integration.message ?? ""}` : `Added here, but not yet able to sign in: ${added.integration.message ?? "the sign-in service did not accept them."}`) : "Added. They can sign in once their company has given them access to this product.");
          })}>Add person</button>
        </div>
      )}
      {msg && <p>{msg}</p>}
      {users.err && <p className="err" role="alert">{users.err}</p>}
      <table>
        <thead><tr><th>Name</th><th>Email</th><th>Title</th><th>Department</th><th>Role</th><th>Status</th>{manage && <th></th>}</tr></thead>
        <tbody>
          {(users.data ?? []).map((u) => (
            <tr key={u.id}>
              <td>{u.name || "-"}</td><td>{u.email}</td><td>{u.title || "-"}</td>
              <td>{manage ? <select aria-label={`Department of ${u.email}`} value={u.department_id == null ? "" : String(u.department_id)} onChange={(e) => run(() => api.patchUser(u.id, { department_id: e.target.value || null }))}><option value="">None</option>{(depts.data ?? []).map((d) => <option key={d.id} value={String(d.id)}>{d.name}</option>)}</select> : u.department ?? "-"}</td>
              <td>{manage ? <select aria-label={`Role of ${u.email}`} value={String(u.role_id)} onChange={(e) => run(() => api.patchUser(u.id, { role_id: e.target.value }))}>{(roles.data ?? []).map((r) => <option key={r.id} value={String(r.id)}>{r.name}</option>)}</select> : u.role_name}</td>
              <td><span className={`chip ${STATUS_CHIP[u.status] ?? ""}`}>{u.status}</span></td>
              {manage && <td>{u.status === "suspended" ? <button className="link" onClick={() => run(() => api.reactivate(u.id))}>Reactivate</button> : <button className="link" onClick={() => run(() => api.suspend(u.id))}>Suspend</button>}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Departments({ api, can }: { api: Api; can: Can }) {
  const depts = useLoad<OrgDepartment[]>(api.departments);
  const [name, setName] = useState("");
  const [parent, setParent] = useState("");
  const manage = can("org.departments.manage");
  const run = async (fn: () => Promise<unknown>) => { depts.setErr(""); try { await fn(); await depts.load(); } catch (e) { depts.setErr((e as OrgError).message); } };
  const label = (id: string | number | null) => (depts.data ?? []).find((d) => d.id === id)?.name ?? "-";
  return (
    <div>
      {manage && (
        <div className="row" style={{ margin: "12px 0" }}>
          <label>New department<input value={name} onChange={(e) => setName(e.target.value)} /></label>
          <label>Inside<select value={parent} onChange={(e) => setParent(e.target.value)}><option value="">Top level</option>{(depts.data ?? []).map((d) => <option key={d.id} value={String(d.id)}>{d.name}</option>)}</select></label>
          <button className="primary" disabled={!name.trim()} onClick={() => run(async () => { await api.addDepartment({ name, parent_id: parent || null }); setName(""); setParent(""); })}>Add department</button>
        </div>
      )}
      {depts.err && <p className="err" role="alert">{depts.err}</p>}
      <table>
        <thead><tr><th>Department</th><th>Inside</th><th>People</th>{manage && <th></th>}</tr></thead>
        <tbody>
          {(depts.data ?? []).map((d) => (
            <tr key={d.id}>
              <td>{d.name}</td><td>{label(d.parent_id)}</td><td>{d.members}</td>
              {manage && <td>
                <button className="link" onClick={() => { const n = window.prompt("New name", d.name); if (n && n.trim() && n !== d.name) run(() => api.patchDepartment(d.id, { name: n })); }}>Rename</button>{" "}
                <button className="link" onClick={() => run(() => api.deleteDepartment(d.id))}>Delete</button>
              </td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Roles({ api, can }: { api: Api; can: Can }) {
  const matrix = useLoad<OrgMatrix>(api.matrix);
  const [nr, setNr] = useState({ key: "", name: "" });
  const manage = can("org.roles.manage");
  const m = matrix.data;
  const byFeature = useMemo(() => {
    const out: Record<string, OrgMatrix["capabilities"]> = {};
    (m?.capabilities ?? []).forEach((c) => { (out[c.feature] ||= []).push(c); });
    return out;
  }, [m]);
  if (!m) return <p className="muted">{matrix.err || "Loading..."}</p>;
  const run = async (fn: () => Promise<unknown>) => { matrix.setErr(""); try { await fn(); await matrix.load(); } catch (e) { matrix.setErr((e as OrgError).message); } };
  const capsOf = (role: OrgMatrix["roles"][number]) => Object.entries(role.grants).map(([k, s]) => (m.capabilities.find((c) => c.key === k)?.scopes.length ? `${k}:${s}` : k));
  const change = (role: OrgMatrix["roles"][number], cap: OrgMatrix["capabilities"][number], value: string) => {
    const next = capsOf(role).filter((c) => c.split(":")[0] !== cap.key);
    if (value) next.push(cap.scopes.length ? `${cap.key}:${value}` : cap.key);
    run(() => api.setRole(role.id, { caps: next }));
  };
  return (
    <div>
      <p className="muted">What each role may do. Roles belong to this product; a person has one role.</p>
      {manage && (
        <div className="row" style={{ margin: "12px 0" }}>
          <label>New role key<input value={nr.key} placeholder="for example team_lead" onChange={(e) => setNr({ ...nr, key: e.target.value })} /></label>
          <label>Name<input value={nr.name} onChange={(e) => setNr({ ...nr, name: e.target.value })} /></label>
          <button className="primary" disabled={!nr.key || !nr.name} onClick={() => run(async () => { await api.addRole({ key: nr.key, name: nr.name, caps: [] }); setNr({ key: "", name: "" }); })}>Add role</button>
        </div>
      )}
      {matrix.err && <p className="err" role="alert">{matrix.err}</p>}
      <table>
        <thead><tr><th>Feature</th>{m.roles.map((r) => <th key={r.id}>{r.name}{manage && !r.is_system && <> <button className="link" onClick={() => run(() => api.deleteRole(r.id))}>delete</button></>}</th>)}</tr></thead>
        <tbody>
          {Object.entries(byFeature).map(([feature, caps]) => [
            <tr key={`h-${feature}`}><td colSpan={m.roles.length + 1}><strong>{m.features[feature] ?? feature}</strong></td></tr>,
            ...caps.map((c) => (
              <tr key={c.key}>
                <td>{c.label}</td>
                {m.roles.map((r) => {
                  const held = r.grants[c.key] ?? "";
                  const locked = !manage;
                  return <td key={r.id}>{c.scopes.length
                    ? <select aria-label={`${c.label} for ${r.name}`} disabled={locked} value={held} onChange={(e) => change(r, c, e.target.value)}><option value="">-</option>{c.scopes.map((s) => <option key={s} value={s}>{s}</option>)}</select>
                    : <input type="checkbox" style={{ minWidth: 0 }} aria-label={`${c.label} for ${r.name}`} disabled={locked} checked={!!held} onChange={(e) => change(r, c, e.target.checked ? "all" : "")} />}</td>;
                })}
              </tr>
            )),
          ])}
        </tbody>
      </table>
    </div>
  );
}

function Activity({ api }: { api: Api }) {
  const log = useLoad<{ total: number; items: OrgAuditItem[] }>(api.audit);
  if (!log.data) return <p className="muted">{log.err || "Loading..."}</p>;
  return (
    <table>
      <thead><tr><th>When</th><th>Who</th><th>What</th><th>Details</th></tr></thead>
      <tbody>{log.data.items.map((a) => <tr key={a.id}><td>{new Date(a.at).toLocaleString()}</td><td>{a.actor}</td><td>{a.action.replace(/[._]/g, " ")}</td><td className="muted">{Object.entries(a.detail ?? {}).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`).join("; ")}</td></tr>)}</tbody>
    </table>
  );
}
