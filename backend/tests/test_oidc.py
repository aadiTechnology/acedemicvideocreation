"""Sign-in through Aadi Identity, against a fake Identity (RSA key, JWKS, token endpoint with PKCE and client secret checks)."""

import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from app.main import create_app
from tests.conftest import make_settings

ISSUER = "https://id.test"
CLIENT_ID, CLIENT_SECRET = "academics-web", "s3cret"


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class FakeIdentity:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(RSAAlgorithm.to_jwk(self.key.public_key()))
        jwk.update({"kid": "k1", "use": "sig", "alg": "RS256"})
        self.jwks = {"keys": [jwk]}
        self.codes: dict[str, dict] = {}
        self.sign_key = self.key
        self.http = httpx.Client(transport=httpx.MockTransport(self.handle))

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/jwks.json":
            return httpx.Response(200, json=self.jwks)
        if request.url.path == "/token":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            rec = self.codes.pop(form.get("code", ""), None)
            if rec is None or form.get("client_secret") != CLIENT_SECRET or form.get("client_id") != CLIENT_ID:
                return httpx.Response(400, json={"error": "invalid_grant"})
            if _b64u(hashlib.sha256(form["code_verifier"].encode()).digest()) != rec["challenge"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            claims = {"iss": ISSUER, "aud": CLIENT_ID, "sub": rec["sub"], "tid": rec["tid"], "email": rec["email"], "name": rec["name"],
                      "tenant_slug": "acme", "product": "academics", "nonce": rec["nonce"], "exp": int(time.time()) + 600, **rec.get("override", {})}
            token = jwt.encode(claims, self.sign_key, algorithm="RS256", headers={"kid": "k1"})
            return httpx.Response(200, json={"id_token": token, "access_token": "a", "token_type": "Bearer"})
        return httpx.Response(404)

    def approve(self, authorize_url: str, sub="user-1", tid="tenant-1", email="a@x.test", name="Asha", **override) -> str:
        q = {k: v[0] for k, v in parse_qs(urlparse(authorize_url).query).items()}
        code = f"code-{len(self.codes)}-{sub}"
        self.codes[code] = {"challenge": q["code_challenge"], "nonce": q["nonce"], "sub": sub, "tid": tid, "email": email, "name": name, "override": override}
        return f"/auth/callback?code={code}&state={q['state']}"


@pytest.fixture()
def identity():
    return FakeIdentity()


def make_client(identity):
    settings = make_settings(auth_mode="oidc", identity_issuer_url=ISSUER, identity_client_id=CLIENT_ID, identity_client_secret=CLIENT_SECRET)
    return TestClient(create_app(settings, oidc_http=identity.http), follow_redirects=False)


def sign_in(client, identity, **who):
    r = client.get("/auth/login")
    assert r.status_code == 303
    return client.get(identity.approve(r.headers["location"], **who))


def test_login_redirects_to_identity_with_pkce(identity):
    with make_client(identity) as c:
        r = c.get("/auth/login?tenant=tenant-9")
        u = urlparse(r.headers["location"])
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        assert f"{u.scheme}://{u.netloc}{u.path}" == f"{ISSUER}/authorize"
        assert (q["response_type"], q["client_id"], q["code_challenge_method"], q["tenant"]) == ("code", CLIENT_ID, "S256", "tenant-9")
        assert q["redirect_uri"] == "http://testserver/auth/callback" and "openid" in q["scope"]
        assert "academic_oidc" in r.headers["set-cookie"] and "HttpOnly" in r.headers["set-cookie"]


def test_full_sign_in_and_me(identity):
    with make_client(identity) as c:
        assert c.get("/api/me").status_code == 401
        r = sign_in(c, identity)
        assert r.status_code == 303 and r.headers["location"] == "/"
        me = c.get("/api/me").json()
        assert (me["user_id"], me["tenant_id"], me["email"]) == ("user-1", "tenant-1", "a@x.test")
        assert me["roles"] == ["admin"]  # first person of a company administers it


def test_data_is_scoped_to_the_token_tenant(identity):
    with make_client(identity) as a, make_client(identity) as b:
        sign_in(a, identity, sub="u-a", tid="tenant-a")
        sign_in(b, identity, sub="u-b", tid="tenant-b")
        assert a.post("/api/classes", json={"name": "Class 7"}).status_code == 201
        assert [x["name"] for x in a.get("/api/classes").json()] == ["Class 7"]
        assert b.get("/api/classes").json() == []


def test_a_person_needs_an_account_an_administrator_created(identity):
    with make_client(identity) as admin, make_client(identity) as other:
        sign_in(admin, identity, sub="boss", tid="t1", email="boss@x.test")
        # Identity let her in, but this product has no account for her: she is told so and gets no session
        r = sign_in(other, identity, sub="staff", tid="t1", email="staff@x.test")
        assert r.status_code == 403 and "do not have an account" in r.text
        assert other.get("/api/me").status_code == 401
        # the administrator adds her (by email, default role: viewer); her first sign-in links the account
        added = admin.post("/api/org/users", json={"email": "Staff@X.test", "name": "Staff"})
        assert added.status_code == 201 and added.json()["role"] == "viewer"
        assert sign_in(other, identity, sub="staff", tid="t1", email="staff@x.test").status_code == 303
        me = other.get("/api/me").json()
        assert me["roles"] == [] and me["caps"] == []
        assert other.get("/api/classes").status_code == 200
        assert other.post("/api/classes", json={"name": "Class 8"}).status_code == 403
        assert other.get("/api/org/users").status_code == 403
        # the administrator gives her the content operator role
        role = next(x for x in admin.get("/api/org/roles").json() if x["key"] == "content_operator")
        assert admin.patch(f"/api/org/users/{added.json()['id']}", json={"role_id": role["id"]}).status_code == 200
        assert other.post("/api/classes", json={"name": "Class 8"}).status_code == 201
        assert other.get("/api/me").json()["roles"] == ["content_operator"]
        # the only administrator cannot demote or suspend themselves
        mine = next(u for u in admin.get("/api/org/users").json() if u["email"] == "boss@x.test")
        viewer = next(x for x in admin.get("/api/org/roles").json() if x["key"] == "viewer")
        assert admin.patch(f"/api/org/users/{mine['id']}", json={"role_id": viewer["id"]}).status_code == 409
        assert admin.post(f"/api/org/users/{mine['id']}/suspend").status_code == 409


def test_a_suspended_person_cannot_sign_in_or_use_a_live_session(identity):
    with make_client(identity) as admin, make_client(identity) as other:
        sign_in(admin, identity, sub="boss", tid="t1", email="boss@x.test")
        added = admin.post("/api/org/users", json={"email": "staff@x.test"}).json()
        sign_in(other, identity, sub="staff", tid="t1", email="staff@x.test")
        assert other.get("/api/me").status_code == 200
        assert admin.post(f"/api/org/users/{added['id']}/suspend").status_code == 200
        assert other.get("/api/me").status_code == 403  # a session already open is refused at once
        assert sign_in(other, identity, sub="staff", tid="t1", email="staff@x.test").status_code == 403


@pytest.mark.parametrize("tamper", ["state", "no_cookie"])
def test_callback_rejects_bad_state_or_missing_cookie(identity, tamper):
    with make_client(identity) as c:
        r = c.get("/auth/login")
        url = identity.approve(r.headers["location"])
        if tamper == "state":
            url = url.split("state=")[0] + "state=forged"
        else:
            c.cookies.clear()
        assert c.get(url).status_code == 400
        assert c.get("/api/me").status_code == 401


@pytest.mark.parametrize("override", [
    {"nonce": "other"}, {"aud": "someone-else"}, {"iss": "https://evil.test"}, {"exp": 1}, {"tid": ""}, {"product": "tracker"},
])
def test_callback_rejects_invalid_id_tokens(identity, override):
    with make_client(identity) as c:
        r = c.get("/auth/login")
        resp = c.get(identity.approve(r.headers["location"], **override))
        assert resp.status_code == 401, override
        assert c.get("/api/me").status_code == 401


def test_callback_rejects_token_signed_with_unknown_key(identity):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    identity.sign_key = other
    with make_client(identity) as c:
        r = c.get("/auth/login")
        assert c.get(identity.approve(r.headers["location"])).status_code == 401


def test_identity_refusal_is_reported(identity):
    with make_client(identity) as c:
        c.get("/auth/login")
        assert c.get("/auth/callback?code=unknown&state=x").status_code in (400, 401)


def test_tampered_session_cookie_is_ignored(identity):
    with make_client(identity) as c:
        sign_in(c, identity)
        c.cookies.set("academic_session", "forged.value.here")
        assert c.get("/api/me").status_code == 401


def test_logout_clears_session_and_goes_to_identity(identity):
    with make_client(identity) as c:
        sign_in(c, identity)
        r = c.get("/auth/logout")
        loc = urlparse(r.headers["location"])
        assert f"{loc.scheme}://{loc.netloc}{loc.path}" == f"{ISSUER}/logout"
        assert parse_qs(loc.query)["client_id"] == [CLIENT_ID]
        assert c.get("/api/me").status_code == 401
