"""Adding a person in Academic enrols them in Aadi Identity (so they can sign in and switch products); a failure never undoes the change."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from tests.conftest import make_settings

HDR = {"X-Dev-User": "u-admin", "X-Dev-Tenant": "company-1", "X-Dev-Email": "boss@example.test", "X-Dev-Org": "real"}


class FakeIdentity:
    def __init__(self):
        self.calls, self.reply = [], (200, {"invited": True, "created": True})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.url.path, json.loads(request.content), request.headers.get("authorization")))
        if self.reply == "down":
            raise httpx.ConnectError("down")
        return httpx.Response(self.reply[0], json=self.reply[1])


@pytest.fixture()
def ctx(database):
    with database.begin() as c:
        c.execute(text("TRUNCATE org_members, org_roles, org_departments, org_audit, app_users, user_roles CASCADE"))
    fake = FakeIdentity()
    settings = make_settings(identity_issuer_url="https://id.test", identity_product_secret="s3cret")
    with TestClient(create_app(settings, identity_http=httpx.Client(transport=httpx.MockTransport(fake)))) as c:
        c.get("/api/org/me", headers=HDR)  # the first person becomes the administrator
        yield c, fake


def add(c, email="teacher@example.test"):
    return c.post("/api/org/users", json={"email": email, "name": "T"}, headers=HDR)


def test_adding_a_person_enrols_them_in_identity(ctx):
    c, fake = ctx
    r = add(c)
    assert r.status_code == 201 and r.json()["integration"]["ok"] is True and "invitation" in r.json()["integration"]["message"]
    path, body, auth = fake.calls[-1]
    assert path == "/api/products/enrol" and auth == "Bearer s3cret"
    assert body == {"tenant_id": "company-1", "email": "teacher@example.test", "name": "T", "actor": "boss@example.test"}


def test_an_existing_identity_account_is_not_invited_again(ctx):
    c, fake = ctx
    fake.reply = (200, {"invited": False, "created": False})
    assert "existing account" in add(c).json()["integration"]["message"]


def test_when_identity_refuses_the_person_is_still_added_and_the_reason_is_shown(ctx):
    c, fake = ctx
    fake.reply = (409, {"detail": "All 5 seats of Academic Video Creation are in use"})
    r = add(c)
    assert r.status_code == 201 and r.json()["integration"] == {"ok": False, "message": "All 5 seats of Academic Video Creation are in use"}
    assert any(u["email"] == "teacher@example.test" for u in c.get("/api/org/users", headers=HDR).json())


def test_when_identity_is_down_the_person_is_still_added(ctx):
    c, fake = ctx
    fake.reply = "down"
    r = add(c)
    assert r.status_code == 201 and r.json()["integration"]["ok"] is False and "could not be reached" in r.json()["integration"]["message"]


def test_suspending_removes_them_from_identitys_registry_and_reactivating_enrols_again(ctx):
    c, fake = ctx
    member = add(c).json()
    fake.reply = (200, {"registered_products": [], "membership_ended": True})
    r = c.post(f"/api/org/users/{member['id']}/suspend", headers=HDR)
    assert r.status_code == 200 and fake.calls[-1][0] == "/api/products/remove"
    fake.reply = (200, {"invited": False})
    c.post(f"/api/org/users/{member['id']}/reactivate", headers=HDR)
    assert fake.calls[-1][0] == "/api/products/enrol"


def test_without_a_product_secret_nothing_is_sent_and_nothing_is_added_to_the_response(database):
    with database.begin() as c:
        c.execute(text("TRUNCATE org_members, org_roles, org_departments, org_audit, app_users, user_roles CASCADE"))
    fake = FakeIdentity()
    with TestClient(create_app(make_settings(identity_issuer_url="https://id.test"), identity_http=httpx.Client(transport=httpx.MockTransport(fake)))) as c:
        c.get("/api/org/me", headers=HDR)
        r = add(c)
    assert r.status_code == 201 and "integration" not in r.json() and fake.calls == []


def test_me_offers_the_product_switcher_only_when_signing_in_through_identity(ctx):
    c, _ = ctx
    assert c.get("/api/me", headers=HDR).json()["hub_url"] == ""  # dev sign-in: no Identity
