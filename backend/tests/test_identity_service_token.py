"""P2-S3: Academics can call Identity with a service token instead of the shared secret. Off unless the two service-client settings are set."""
import httpx

from types import SimpleNamespace

from app.identity_client import IdentityClient

BASE = "http://identity.test"


def make(handler, secret="", service_id="", service_secret=""):
    settings = SimpleNamespace(identity_issuer_url=BASE, identity_product_secret=secret, identity_service_client_id=service_id, identity_service_client_secret=service_secret)
    return IdentityClient(settings, http=httpx.Client(transport=httpx.MockTransport(handler)))


class Fake:
    """A pretend Identity that records every request."""

    def __init__(self, token_status=200, expires_in=600):
        self.calls, self.token_status, self.expires_in, self.n = [], token_status, expires_in, 0

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append((req.method, req.url.path, dict(req.headers), req.content.decode()))
        if req.url.path == "/token":
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "access_denied", "error_description": "The company has no active subscription for the calling product"})
            self.n += 1
            return httpx.Response(200, json={"access_token": f"tok-{self.n}", "token_type": "Bearer", "expires_in": self.expires_in})
        return httpx.Response(200, json={"invited": True, "identity_id": "u1"})


def test_default_behaviour_is_unchanged_without_service_credentials():
    f = Fake()
    c = make(f, secret="old-secret")
    assert not c.token_mode and c.enabled
    assert c.enrol("t1", "a@x.com", "A", "boss")["ok"]
    method, path, headers, _ = f.calls[0]
    assert path == "/api/products/enrol" and headers["authorization"] == "Bearer old-secret"  # old path, old secret, no token request
    assert all(call[1] != "/token" for call in f.calls)


def test_token_mode_asks_for_a_token_for_that_company_and_uses_the_v1_path():
    f = Fake()
    c = make(f, service_id="tracker-identity", service_secret="s3")
    assert c.enabled and c.token_mode  # enabled with no product secret at all
    out = c.enrol("t1", "a@x.com", "A", "boss")
    assert out["ok"] and out["message"].startswith("An invitation")
    token_call, enrol_call = f.calls
    assert token_call[1] == "/token"
    for part in ("grant_type=client_credentials", "client_id=tracker-identity", "client_secret=s3", "audience=identity", "scope=identity%3Aenrol", "tenant_id=t1"):
        assert part in token_call[3], part
    assert enrol_call[1] == "/api/v1/products/enrol" and enrol_call[2]["authorization"] == "Bearer tok-1"


def test_tokens_are_cached_per_company_and_action_then_renewed():
    f = Fake(expires_in=600)
    c = make(f, service_id="i", service_secret="s")
    c.enrol("t1", "a@x.com", "A", "b")
    c.enrol("t1", "b@x.com", "B", "b")
    assert f.n == 1  # the second call reused the token
    c.enrol("t2", "c@x.com", "C", "b")
    assert f.n == 2  # another company needs its own token
    c.remove("t1", "a@x.com", "b")
    assert f.n == 3  # another action needs its own scope
    # a token about to expire is renewed
    f2 = Fake(expires_in=30)
    c2 = make(f2, service_id="i", service_secret="s")
    c2.enrol("t1", "a@x.com", "A", "b")
    c2.enrol("t1", "b@x.com", "B", "b")
    assert f2.n == 2


def test_remove_uses_its_own_scope():
    f = Fake()
    make(f, service_id="i", service_secret="s").remove("t1", "a@x.com", "b")
    assert "scope=identity%3Aremove" in f.calls[0][3] and f.calls[1][1] == "/api/v1/products/remove"


def test_if_no_token_can_be_had_the_secret_is_used_so_people_can_still_be_added():
    f = Fake(token_status=400)
    c = make(f, secret="old-secret", service_id="i", service_secret="wrong")
    out = c.enrol("t1", "a@x.com", "A", "b")
    assert out["ok"]
    assert f.calls[-1][1] == "/api/products/enrol" and f.calls[-1][2]["authorization"] == "Bearer old-secret"


def test_with_no_secret_to_fall_back_on_the_reason_is_shown():
    f = Fake(token_status=400)
    out = make(f, service_id="i", service_secret="wrong").enrol("t1", "a@x.com", "A", "b")
    assert out["ok"] is False and "no active subscription" in out["message"]
    assert [c[1] for c in f.calls] == ["/token"]  # the enrol request was never sent


def test_identity_unreachable_during_the_token_request_does_not_raise():
    def boom(req):
        raise httpx.ConnectError("down")
    out = make(boom, service_id="i", service_secret="s").enrol("t1", "a@x.com", "A", "b")
    assert out["ok"] is False and "could not be reached" in out["message"]


def test_nothing_is_enabled_with_neither_secret_nor_service_client():
    assert not make(Fake()).enabled


# ---- entitlement reader (P2-S5) -------------------------------------------------------------------------------------
ANSWER = {"tenant_id": "t1", "product": "tracker", "entitled": True, "plan": {"key": "tracker-pro", "name": "Tracker Pro"}, "features": ["costing"], "limits": {"projects": 50}}


class Ent(Fake):
    def __init__(self, fail=False, **kw):
        super().__init__(**kw)
        self.fail = fail
        self.reads = 0

    def __call__(self, req):
        if req.url.path == "/api/v1/entitlements":
            self.calls.append((req.method, req.url.path, dict(req.headers), str(req.url.query)))
            self.reads += 1
            if self.fail:
                raise httpx.ConnectError("down")
            return httpx.Response(200, json=ANSWER)
        return super().__call__(req)


def test_entitlements_are_read_with_a_token_scoped_to_that_action_and_cached():
    f = Ent()
    c = make(f, service_id="i", service_secret="s")
    assert c.entitlements("t1") == ANSWER and c.entitlements("t1") == ANSWER
    assert f.reads == 1  # the second call came from the cache
    tok = next(call for call in f.calls if call[1] == "/token")
    assert "scope=identity%3Aentitlements" in tok[3] and "tenant_id=t1" in tok[3]
    read = next(call for call in f.calls if call[1] == "/api/v1/entitlements")
    assert read[2]["authorization"] == "Bearer tok-1" and "tenant_id=t1" in read[3]


def test_entitlements_with_only_the_shared_secret_use_the_secret():
    f = Ent()
    c = make(f, secret="old")
    assert c.entitlements("t1") == ANSWER
    assert f.calls[0][2]["authorization"] == "Bearer old" and all(call[1] != "/token" for call in f.calls)


def test_the_cache_expires_and_the_last_answer_is_served_if_identity_is_down(monkeypatch):
    f = Ent()
    c = make(f, secret="old")
    c.entitlements("t1")
    key = next(iter(c._entitlements))
    c._entitlements[key] = (c._entitlements[key][0], c._entitlements[key][1] - 400)  # older than the 5 minutes
    c.entitlements("t1")
    assert f.reads == 2  # refreshed
    f.fail = True
    c._entitlements[key] = (c._entitlements[key][0], c._entitlements[key][1] - 400)
    assert c.entitlements("t1") == ANSWER  # Identity unreachable: the last known answer, not a lock-out
    assert Ent(fail=True) and make(Ent(fail=True), secret="old").entitlements("t9") is None  # never known: None


def test_other_companies_are_cached_separately():
    f = Ent()
    c = make(f, secret="old")
    c.entitlements("t1")
    c.entitlements("t2")
    assert f.reads == 2
