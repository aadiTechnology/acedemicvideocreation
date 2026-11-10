"""Tells Aadi Identity about the people this product enrols, so they can sign in and switch between products.

Identity decides who may sign in (company, product subscription, seats); the product owns users, departments and roles.
Off unless IDENTITY_PRODUCT_SECRET is set. A failure never undoes the change in this product: the person is still added here,
and the message says what Identity said, so the administrator can fix it (for example, no free seats)."""
from __future__ import annotations

import logging

import httpx

from aadi_org.router import OrgHooks, Principal
from app.config import Settings

log = logging.getLogger("academic.identity")


class IdentityClient:
    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.base = settings.identity_issuer_url
        self.secret = settings.identity_product_secret
        self.http = http or httpx.Client(timeout=10.0)

    @property
    def enabled(self) -> bool:
        return bool(self.base and self.secret)

    def _post(self, path: str, body: dict) -> dict:
        try:
            r = self.http.post(f"{self.base}{path}", json=body, headers={"Authorization": f"Bearer {self.secret}"})
        except httpx.HTTPError:
            log.exception("identity unreachable")
            return {"ok": False, "message": "Aadi Identity could not be reached. The person was added here; try again later."}
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", "")
            except ValueError:
                detail = ""
            return {"ok": False, "message": detail if isinstance(detail, str) and detail else f"Aadi Identity refused ({r.status_code})."}
        return {"ok": True, **r.json()}

    def enrol(self, tenant_id: str, email: str, name: str, actor: str) -> dict:
        out = self._post("/api/products/enrol", {"tenant_id": tenant_id, "email": email, "name": name, "actor": actor})
        if out["ok"]:
            out["message"] = "An invitation was sent by email." if out.get("invited") else "Added; they can sign in with their existing account."
        return out

    def remove(self, tenant_id: str, email: str, actor: str) -> dict:
        return self._post("/api/products/remove", {"tenant_id": tenant_id, "email": email, "actor": actor})


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
