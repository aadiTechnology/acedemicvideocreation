"""Academic's use of the organization kit: conformance with every other product, the pinned copy, and the move of existing users."""
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text

from aadi_org import vendoring
from aadi_org.conformance import CONFORMANCE_TESTS
from app.main import create_app
from tests.conftest import TEST_URL, make_settings
from tests.test_migrations import _cfg

ACTORS = {"admin": ("u-admin", "A", "admin@example.test"), "limited": ("u-limited", "A", "limited@example.test"),
          "stranger": ("u-stranger", "A", "stranger@example.test"), "other": ("u-other", "B", "other@example.test")}


class AcademicAdapter:
    """The kit's conformance suite run against Academic's real app, with real accounts and roles (X-Dev-Org: real)."""
    limited_role_key = "viewer"

    def __init__(self, client, database):
        self.client, self.database = client, database

    def reset(self):
        with self.database.begin() as c:
            c.execute(text("TRUNCATE org_members, org_roles, org_departments, org_audit, app_users, user_roles CASCADE"))

    def request(self, actor, method, path, json=None):
        user, tenant, email = ACTORS[actor]
        r = self.client.request(method, f"/api{path}", json=json, headers={"X-Dev-User": user, "X-Dev-Tenant": tenant, "X-Dev-Email": email, "X-Dev-Org": "real"})
        try:
            body = r.json() if r.content else None
        except ValueError:
            body = r.text
        return r.status_code, body


@pytest.fixture()
def adapter(database):
    with TestClient(create_app(make_settings())) as c:
        yield AcademicAdapter(c, database)


@pytest.mark.parametrize("name,fn", CONFORMANCE_TESTS, ids=[n for n, _ in CONFORMANCE_TESTS])
def test_academic_conforms_to_the_kit(adapter, name, fn):
    adapter.reset()
    fn(adapter)


def test_the_pinned_kit_copy_is_exactly_the_recorded_version():
    kit = Path(__file__).resolve().parents[1] / "aadi_org"
    assert vendoring.verify(kit, "0.1.1") == []


def test_academic_roles_and_capabilities(adapter):
    status, me = adapter.request("admin", "GET", "/org/me")
    assert status == 200 and me["member"]["role"] == "admin"
    status, cat = adapter.request("admin", "GET", "/org/catalog")
    assert {c["key"] for c in cat["capabilities"]} >= {"lessons.manage", "structure.manage", "review.decide", "video.generate", "org.users.manage"}
    assert [d["key"] for d in cat["default_roles"]] == ["admin", "content_operator", "reviewer", "production_operator", "viewer"]


def test_existing_people_and_roles_move_across_in_the_migration(database):
    with database.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    command.upgrade(_cfg(), "0005")
    people = [("t1", "boss", "boss@x.test", ["admin"]), ("t1", "ed", "ed@x.test", ["content_operator"]), ("t1", "rev", "rev@x.test", ["reviewer"]),
              ("t1", "combo", "combo@x.test", ["reviewer", "production_operator"]), ("t1", "nobody", "nobody@x.test", []),
              ("t1", "dup", "ED@x.test", ["reviewer"]), ("t2", "solo", "", ["admin", "reviewer"])]
    with database.begin() as c:
        for tenant, uid, email, roles in people:
            c.execute(text("INSERT INTO app_users (id, tenant_id, created_at, user_id, email, name, last_login_at) VALUES (:i, :t, now(), :u, :e, :n, now())"),
                      {"i": f"{tenant}-{uid}", "t": tenant, "u": uid, "e": email, "n": uid.title()})
            for r in roles:
                c.execute(text("INSERT INTO user_roles (id, tenant_id, created_at, user_id, role) VALUES (:i, :t, now(), :u, :r)"), {"i": f"{tenant}-{uid}-{r}", "t": tenant, "u": uid, "r": r})
    command.upgrade(_cfg(), "head")
    with database.connect() as c:
        rows = c.execute(text("SELECT m.tenant_id, m.user_id, m.email, m.status, r.key, r.caps::text FROM org_members m JOIN org_roles r ON r.id = m.role_id ORDER BY m.tenant_id, m.user_id")).all()
        by = {(t, u): (e, s, k, caps) for t, u, e, s, k, caps in rows}
        assert len(rows) == len(people)  # nobody is lost
        assert all(v[1] == "active" for v in by.values())
        assert [by[("t1", u)][2] for u in ("boss", "ed", "rev", "nobody")] == ["admin", "content_operator", "reviewer", "viewer"]
        assert by[("t1", "combo")][2] == "combo_reviewer_production_operator"
        assert "review.decide" in by[("t1", "combo")][3] and "video.generate" in by[("t1", "combo")][3] and "lessons.manage" not in by[("t1", "combo")][3]
        assert by[("t2", "solo")][2] == "admin" and by[("t2", "solo")][0].endswith("@no-email.invalid")  # a person without an email still gets an account
        assert by[("t1", "dup")][0].endswith("@duplicate.invalid")  # a clashing email does not stop the migration
        # each company has its own copy of the built-in roles
        assert c.execute(text("SELECT count(*) FROM org_roles WHERE tenant_id='t1' AND is_system")).scalar() == 5
        assert c.execute(text("SELECT count(*) FROM org_roles WHERE tenant_id='t2' AND is_system")).scalar() == 5
