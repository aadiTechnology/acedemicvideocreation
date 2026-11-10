"""Conformance tests: a product runs these against its own app to prove it behaves like every other product that uses the kit.

A product supplies an ``Adapter``:
    request(actor, method, path, json=None) -> (status_code, body)   actor is one of the four below
    reset()                                                          empty the database (called before each test)
    limited_role_key                                                 a default role key that holds NO organization capabilities
Actors: "admin" (signs in first in company A, so becomes its administrator), "limited" (signs in as the person the admin adds with the
limited role), "stranger" (signs in to company A but was never added), "other" (the first person of company B).

In pytest:  @pytest.mark.parametrize("name,fn", CONFORMANCE_TESTS) ... fn(adapter)"""
from __future__ import annotations

import uuid
from typing import Any, Callable, Protocol


class Adapter(Protocol):
    limited_role_key: str

    def request(self, actor: str, method: str, path: str, json: Any = None) -> tuple[int, Any]: ...
    def reset(self) -> None: ...


def _ok(r, want=(200, 201, 204)):
    status, body = r
    assert status in want, f"expected {want}, got {status}: {body}"
    return body


def _status(r, want):
    status, body = r
    assert status == want, f"expected {want}, got {status}: {body}"
    return body


def _boot(a: Adapter) -> dict:
    return _ok(a.request("admin", "GET", "/org/me"))


def _role(a: Adapter, key: str) -> dict:
    return next(r for r in _ok(a.request("admin", "GET", "/org/roles")) if r["key"] == key)


def _add_limited(a: Adapter, email: str = "limited@example.test") -> dict:
    return _ok(a.request("admin", "POST", "/org/users", {"email": email, "name": "Limited Person", "role_id": _role(a, a.limited_role_key)["id"]}))


def _usable_cap(a: Adapter) -> str:
    cat = _ok(a.request("admin", "GET", "/org/catalog"))
    for c in cat["capabilities"]:
        if not c["key"].startswith(("org.", "audit.")):
            return f"{c['key']}:{c['scopes'][0]}" if c["scopes"] else c["key"]
    raise AssertionError("the catalog has no product capability")


def first_user_becomes_administrator(a):
    me = _boot(a)
    cat = _ok(a.request("admin", "GET", "/org/catalog"))
    assert me["member"]["role"] == cat["admin_role"] and me["member"]["status"] == "active"
    assert {"org.users.manage", "org.roles.manage", "org.departments.manage", "audit.view"} <= set(me["caps"])


def default_roles_are_seeded_from_the_catalog(a):
    _boot(a)
    cat = _ok(a.request("admin", "GET", "/org/catalog"))
    roles = _ok(a.request("admin", "GET", "/org/roles"))
    assert {d["key"] for d in cat["default_roles"]} <= {r["key"] for r in roles}
    assert all(r["is_system"] for r in roles if r["key"] in {d["key"] for d in cat["default_roles"]})


def a_person_who_was_never_added_has_no_account(a):
    _boot(a)
    status, _ = a.request("stranger", "GET", "/org/me")
    assert status == 403


def departments_can_be_created_renamed_and_removed(a):
    _boot(a)
    d = _ok(a.request("admin", "POST", "/org/departments", {"name": "Content"}))
    _status(a.request("admin", "POST", "/org/departments", {"name": "Content"}), 409)
    _status(a.request("admin", "POST", "/org/departments", {"name": "  "}), 422)
    assert _ok(a.request("admin", "PATCH", f"/org/departments/{d['id']}", {"name": "Content team"}))["name"] == "Content team"
    _ok(a.request("admin", "DELETE", f"/org/departments/{d['id']}"))
    assert all(x["id"] != d["id"] for x in _ok(a.request("admin", "GET", "/org/departments")))


def departments_nest_without_cycles_and_block_deletion_while_in_use(a):
    _boot(a)
    top = _ok(a.request("admin", "POST", "/org/departments", {"name": "Academics"}))
    sub = _ok(a.request("admin", "POST", "/org/departments", {"name": "Science", "parent_id": top["id"]}))
    _status(a.request("admin", "PATCH", f"/org/departments/{top['id']}", {"parent_id": sub["id"]}), 422)
    _status(a.request("admin", "PATCH", f"/org/departments/{top['id']}", {"parent_id": top["id"]}), 422)
    _status(a.request("admin", "DELETE", f"/org/departments/{top['id']}"), 409)  # has a sub-department
    m = _add_limited(a)
    _ok(a.request("admin", "PATCH", f"/org/users/{m['id']}", {"department_id": sub["id"]}))
    _status(a.request("admin", "DELETE", f"/org/departments/{sub['id']}"), 409)  # a person is in it


def roles_are_validated_against_the_catalog(a):
    _boot(a)
    cap = _usable_cap(a)
    _status(a.request("admin", "POST", "/org/roles", {"key": "bad one", "name": "X", "caps": []}), 422)
    _status(a.request("admin", "POST", "/org/roles", {"key": "ghost", "name": "Ghost", "caps": ["nothing.here"]}), 422)
    r = _ok(a.request("admin", "POST", "/org/roles", {"key": "custom_role", "name": "Custom", "caps": [cap]}))
    assert r["caps"] == [cap] and not r["is_system"]
    _status(a.request("admin", "POST", "/org/roles", {"key": "custom_role", "name": "Again", "caps": []}), 409)
    scoped = [c for c in _ok(a.request("admin", "GET", "/org/catalog"))["capabilities"] if c["scopes"]]
    if scoped:  # a scoped capability must say which scope
        _status(a.request("admin", "POST", "/org/roles", {"key": "noscope", "name": "No scope", "caps": [scoped[0]["key"]]}), 422)
        _status(a.request("admin", "POST", "/org/roles", {"key": "badscope", "name": "Bad scope", "caps": [f"{scoped[0]['key']}:galaxy"]}), 422)


def built_in_roles_cannot_be_deleted_and_roles_in_use_cannot_either(a):
    _boot(a)
    builtin = _role(a, a.limited_role_key)
    _status(a.request("admin", "DELETE", f"/org/roles/{builtin['id']}"), 409)
    cap = _usable_cap(a)
    r = _ok(a.request("admin", "POST", "/org/roles", {"key": "temp_role", "name": "Temp", "caps": [cap]}))
    m = _ok(a.request("admin", "POST", "/org/users", {"email": "temp@example.test", "role_id": r["id"]}))
    _status(a.request("admin", "DELETE", f"/org/roles/{r['id']}"), 409)
    _ok(a.request("admin", "PATCH", f"/org/users/{m['id']}", {"role_id": builtin["id"]}))
    _ok(a.request("admin", "DELETE", f"/org/roles/{r['id']}"))


def the_administrator_role_keeps_the_organization_permissions(a):
    me = _boot(a)
    admin = _role(a, me["member"]["role"])
    stripped = [c for c in admin["caps"] if not c.startswith("org.roles.manage")]
    _status(a.request("admin", "PUT", f"/org/roles/{admin['id']}", {"caps": stripped}), 422)


def people_can_be_added_changed_and_must_be_valid(a):
    _boot(a)
    dept = _ok(a.request("admin", "POST", "/org/departments", {"name": "Review"}))
    m = _add_limited(a)
    assert m["status"] == "invited" and m["user_id"] is None
    _status(a.request("admin", "POST", "/org/users", {"email": "LIMITED@example.test"}), 409)  # same email, any case
    _status(a.request("admin", "POST", "/org/users", {"email": "not-an-email"}), 422)
    out = _ok(a.request("admin", "PATCH", f"/org/users/{m['id']}", {"title": "Reviewer", "department_id": dept["id"]}))
    assert (out["title"], out["department"]) == ("Reviewer", "Review")
    boss = _ok(a.request("admin", "POST", "/org/users", {"email": "boss@example.test", "role_id": _role(a, a.limited_role_key)["id"]}))
    _ok(a.request("admin", "PATCH", f"/org/users/{m['id']}", {"manager_id": boss["id"]}))
    _status(a.request("admin", "PATCH", f"/org/users/{boss['id']}", {"manager_id": m["id"]}), 422)  # a loop of managers
    _status(a.request("admin", "PATCH", f"/org/users/{boss['id']}", {"manager_id": boss["id"]}), 422)


def an_added_person_is_linked_on_first_sign_in(a):
    _boot(a)
    m = _add_limited(a)
    me = _ok(a.request("limited", "GET", "/org/me"))
    assert me["member"]["id"] == m["id"] and me["member"]["status"] == "active" and me["member"]["user_id"]


def capabilities_are_enforced_on_every_endpoint(a):
    _boot(a)
    _add_limited(a)
    _ok(a.request("limited", "GET", "/org/me"))
    for method, path, body in (("GET", "/org/users", None), ("POST", "/org/users", {"email": "x@example.test"}), ("GET", "/org/departments", None),
                               ("POST", "/org/departments", {"name": "Nope"}), ("GET", "/org/roles", None), ("POST", "/org/roles", {"key": "nope", "name": "Nope", "caps": []}),
                               ("GET", "/org/matrix", None), ("GET", "/org/audit", None)):
        status, _ = a.request("limited", method, path, body)
        assert status == 403, f"{method} {path} gave {status} to a person without organization permissions"


def the_last_administrator_cannot_be_suspended_or_demoted(a):
    me = _boot(a)
    mine = me["member"]["id"]
    _status(a.request("admin", "POST", f"/org/users/{mine}/suspend"), 409)
    _status(a.request("admin", "PATCH", f"/org/users/{mine}", {"role_id": _role(a, a.limited_role_key)["id"]}), 409)
    admin_role = _role(a, me["member"]["role"])
    second = _ok(a.request("admin", "POST", "/org/users", {"email": "second@example.test", "role_id": admin_role["id"]}))
    assert second["role"] == admin_role["key"]
    # the second administrator has not signed in yet, so the first is still the only ACTIVE one
    _status(a.request("admin", "POST", f"/org/users/{mine}/suspend"), 409)


def a_suspended_person_is_refused_and_can_be_restored(a):
    _boot(a)
    m = _add_limited(a)
    _ok(a.request("limited", "GET", "/org/me"))
    _ok(a.request("admin", "POST", f"/org/users/{m['id']}/suspend"))
    status, _ = a.request("limited", "GET", "/org/me")
    assert status == 403
    _ok(a.request("admin", "POST", f"/org/users/{m['id']}/reactivate"))
    _ok(a.request("limited", "GET", "/org/me"))


def companies_cannot_see_or_change_each_other(a):
    _boot(a)
    mine = _add_limited(a)
    _ok(a.request("other", "GET", "/org/me"))
    assert [u["email"] for u in _ok(a.request("other", "GET", "/org/users"))] == [u["email"] for u in _ok(a.request("other", "GET", "/org/users")) if u["email"] != "limited@example.test"]
    assert all(u["id"] != mine["id"] for u in _ok(a.request("other", "GET", "/org/users")))
    _status(a.request("other", "PATCH", f"/org/users/{mine['id']}", {"title": "Hijack"}), 404)
    _status(a.request("other", "POST", f"/org/users/{mine['id']}/suspend"), 404)
    dept = _ok(a.request("admin", "POST", "/org/departments", {"name": "Private"}))
    _status(a.request("other", "DELETE", f"/org/departments/{dept['id']}"), 404)
    assert all(d["name"] != "Private" for d in _ok(a.request("other", "GET", "/org/departments")))


def changes_are_recorded_in_the_activity_log(a):
    _boot(a)
    _ok(a.request("admin", "POST", "/org/departments", {"name": "Logged"}))
    m = _add_limited(a)
    _ok(a.request("admin", "POST", f"/org/users/{m['id']}/suspend"))
    log = _ok(a.request("admin", "GET", "/org/audit"))
    actions = {i["action"] for i in log["items"]}
    assert {"department.created", "member.created", "member.suspended"} <= actions
    assert all(i["actor"] for i in log["items"] if i["action"] != "member.first_admin")


def the_roles_and_features_matrix_lists_every_role(a):
    _boot(a)
    mx = _ok(a.request("admin", "GET", "/org/matrix"))
    assert mx["capabilities"] and mx["roles"] and all("grants" in r for r in mx["roles"])
    admin = next(r for r in mx["roles"] if r["key"] == mx["admin_role"])
    assert len(admin["grants"]) == len(mx["capabilities"])


CONFORMANCE_TESTS: list[tuple[str, Callable]] = [(f.__name__, f) for f in (
    first_user_becomes_administrator, default_roles_are_seeded_from_the_catalog, a_person_who_was_never_added_has_no_account,
    departments_can_be_created_renamed_and_removed, departments_nest_without_cycles_and_block_deletion_while_in_use,
    roles_are_validated_against_the_catalog, built_in_roles_cannot_be_deleted_and_roles_in_use_cannot_either,
    the_administrator_role_keeps_the_organization_permissions, people_can_be_added_changed_and_must_be_valid,
    an_added_person_is_linked_on_first_sign_in, capabilities_are_enforced_on_every_endpoint,
    the_last_administrator_cannot_be_suspended_or_demoted, a_suspended_person_is_refused_and_can_be_restored,
    companies_cannot_see_or_change_each_other, changes_are_recorded_in_the_activity_log, the_roles_and_features_matrix_lists_every_role)]


def run_all(adapter: Adapter) -> list[str]:
    """Run every test; return the failures (empty when the product conforms). Handy outside pytest."""
    failures = []
    for name, fn in CONFORMANCE_TESTS:
        adapter.reset()
        try:
            fn(adapter)
        except AssertionError as e:
            failures.append(f"{name}: {e}")
    _ = uuid
    return failures
