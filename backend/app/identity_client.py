"""Tells Aadi Identity about the people this product enrols, so they can sign in and switch between products.

Identity decides who may sign in (company, product subscription, seats); the product owns users, departments and roles.

How it proves who it is (both are supported; the first one that is configured wins):
  * an Identity SERVICE TOKEN (preferred): set IDENTITY_SERVICE_CLIENT_ID and IDENTITY_SERVICE_CLIENT_SECRET (a service client for audience "identity" created by a
    platform administrator). The token is short-lived, limited to one company and one action, cached and renewed before it expires. If Identity cannot issue
    one and a product secret is also set, the call falls back to the secret (and says so in the log), so a mistake in the new setting never stops people being added.
  * the product's shared secret (the older way, to be retired): IDENTITY_PRODUCT_SECRET.
Off unless one of them is set. A failure never undoes the change in this product: the person is still added here,
and the message says what Identity said, so the administrator can fix it (for example, no free seats)."""
from __future__ import annotations

import logging
import threading
import time

import httpx

from aadi_org.router import OrgHooks, Principal
from app.config import Settings

log = logging.getLogger("academic.identity")
RENEW_BEFORE_SECONDS = 60


class IdentityClient:
    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.base = settings.identity_issuer_url
        self.secret = settings.identity_product_secret
        self.service_id = getattr(settings, "identity_service_client_id", "")
        self.service_secret = getattr(settings, "identity_service_client_secret", "")
        self.http = http or httpx.Client(timeout=10.0)
        self._tokens: dict[tuple[str, str], tuple[str, float]] = {}  # (scope, company) -> (token, monotonic expiry)
        self._lock = threading.Lock()

    @property
    def token_mode(self) -> bool:
        return bool(self.service_id and self.service_secret)

    @property
    def enabled(self) -> bool:
        return bool(self.base and (self.secret or self.token_mode))

    def _token(self, scope: str, tenant_id: str) -> tuple[str | None, str]:
        """A cached service token for one company and one action, or (None, why not)."""
        key = (scope, tenant_id)
        with self._lock:
            got = self._tokens.get(key)
            if got and got[1] - time.monotonic() > RENEW_BEFORE_SECONDS:
                return got[0], ""
        try:
            r = self.http.post(f"{self.base}/token", data={"grant_type": "client_credentials", "client_id": self.service_id, "client_secret": self.service_secret,
                                                           "audience": "identity", "scope": scope, "tenant_id": tenant_id})
        except httpx.HTTPError:
            log.exception("identity unreachable (token)")
            return None, "Aadi Identity could not be reached. The person was added here; try again later."
        if r.status_code != 200:
            try:
                why = r.json().get("error_description") or r.json().get("error") or ""
            except ValueError:
                why = ""
            return None, why or f"Aadi Identity would not issue a token ({r.status_code})."
        body = r.json()
        with self._lock:
            self._tokens[key] = (body["access_token"], time.monotonic() + int(body.get("expires_in", 600)))
        return body["access_token"], ""

    def _post(self, path: str, body: dict, scope: str = "") -> dict:
        headers = {"Authorization": f"Bearer {self.secret}"}
        if self.token_mode and scope:
            token, why = self._token(scope, body.get("tenant_id", ""))
            if token:
                headers, path = {"Authorization": f"Bearer {token}"}, path.replace("/api/", "/api/v1/", 1)
            elif self.secret:
                log.warning("identity service token unavailable (%s); using the product secret", why)
            else:
                return {"ok": False, "message": why}
        try:
            r = self.http.post(f"{self.base}{path}", json=body, headers=headers)
        except httpx.HTTPError:
            log.exception("identity unreachable")
            return {"ok": False, "message": "Aadi Identity could not be reached. The person was added here; try again later."}
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", "")
            except ValueError:
                detail = ""
            if r.status_code == 422:  # a validation problem: in practice the email address
                return {"ok": False, "message": "Aadi Identity did not accept this email address. Check it and add the person again."}
            return {"ok": False, "message": detail if isinstance(detail, str) and detail else f"Aadi Identity refused ({r.status_code})."}
        return {"ok": True, **r.json()}

    def enrol(self, tenant_id: str, email: str, name: str, actor: str) -> dict:
        out = self._post("/api/products/enrol", {"tenant_id": tenant_id, "email": email, "name": name, "actor": actor}, "identity:enrol")
        if out["ok"]:
            out["message"] = "An invitation was sent by email." if out.get("invited") else "Added; they can sign in with their existing account."
        return out

    def remove(self, tenant_id: str, email: str, actor: str) -> dict:
        return self._post("/api/products/remove", {"tenant_id": tenant_id, "email": email, "actor": actor}, "identity:remove")


class IdentityHooks(OrgHooks):
    def __init__(self, client: IdentityClient):
        self.client = client

    def member_created(self, member: dict, principal: Principal) -> dict | None:
        if not self.client.enabled:
            return None
        return self.client.enrol(principal.tenant_id, member["email"], member.get("name") or "", principal.email)

    def member_status_changed(self, member: dict, principal: Principal) -> dict | None:
        if not self.client.enabled:
            return None
        if member["status"] == "suspended":
            out = self.client.remove(principal.tenant_id, member["email"], principal.email)
            if not out["ok"] and "not registered" in out["message"]:
                return None
            return out
        return self.client.enrol(principal.tenant_id, member["email"], member.get("name") or "", principal.email)
