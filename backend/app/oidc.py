"""Sign-in through Aadi Identity: OpenID Connect authorization code flow with PKCE (S256), confidential client.

The session is a signed, HttpOnly cookie holding the Identity user id, company id and display data. Identity decides
who may sign in (company membership plus an active subscription to this product); roles live in this product's tables.
"""

from __future__ import annotations

import base64
import hashlib
import json
import html
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import select

from app import db as database
from app.config import Settings
from app.models import AppUser, utcnow

SESSION_COOKIE = "academic_session"
TX_COOKIE = "academic_oidc"
SESSION_SECONDS = 8 * 3600
TX_SECONDS = 600
JWKS_TTL = 600


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class OIDCClient:
    """Talks to Identity. ``http`` can be replaced in tests with an httpx client that uses a MockTransport."""

    def __init__(self, settings: Settings, http: httpx.Client | None = None) -> None:
        self.s = settings
        self.http = http or httpx.Client(timeout=10)
        self._jwks: tuple[float, dict] | None = None

    @property
    def redirect_uri(self) -> str:
        return f"{self.s.app_base_url}/auth/callback"

    def authorize_url(self, state: str, nonce: str, verifier: str, tenant: str | None) -> str:
        params = {
            "response_type": "code", "client_id": self.s.identity_client_id, "redirect_uri": self.redirect_uri,
            "scope": "openid profile email", "state": state, "nonce": nonce,
            "code_challenge": _b64u(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256",
        }
        if tenant:
            params["tenant"] = tenant
        return f"{self.s.identity_issuer_url}/authorize?{urlencode(params)}"

    def exchange(self, code: str, verifier: str) -> dict:
        resp = self.http.post(f"{self.s.identity_issuer_url}/token", data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri,
            "client_id": self.s.identity_client_id, "client_secret": self.s.identity_client_secret, "code_verifier": verifier})
        if resp.status_code != 200:
            raise HTTPException(401, "Sign-in was refused by Aadi Identity.")
        return resp.json()

    def _keys(self) -> dict:
        now = time.time()
        if self._jwks is None or now - self._jwks[0] > JWKS_TTL:
            resp = self.http.get(f"{self.s.identity_issuer_url}/.well-known/jwks.json")
            resp.raise_for_status()
            self._jwks = (now, {k["kid"]: k for k in resp.json()["keys"]})
        return self._jwks[1]

    def verify_id_token(self, token: str, nonce: str) -> dict:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
            jwk = self._keys().get(kid)
            if jwk is None:
                self._jwks = None  # key rotation: refetch once
                jwk = self._keys().get(kid)
            if jwk is None:
                raise HTTPException(401, "Unknown signing key.")
            claims = jwt.decode(token, RSAAlgorithm.from_jwk(json.dumps(jwk)), algorithms=["RS256"],
                                audience=self.s.identity_client_id, issuer=self.s.identity_issuer_url,
                                options={"require": ["exp", "iss", "aud", "sub"]})
        except jwt.PyJWTError as exc:
            raise HTTPException(401, "The sign-in token is not valid.") from exc
        if claims.get("nonce") != nonce:
            raise HTTPException(401, "The sign-in token does not match this request.")
        if claims.get("product") not in (None, self.s.identity_product_key) or not claims.get("tid"):
            raise HTTPException(401, "The sign-in token is not for this product.")
        return claims


def _serializer(settings: Settings, salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt=salt)


NO_ACCOUNT_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>No account yet</title><style>body{{font-family:system-ui,sans-serif;max-width:520px;margin:15vh auto;padding:0 20px;color:#1c2540}}a{{color:#2457d6}}</style></head>
<body><h2>No account in this product yet</h2><p>{message}</p><p><a href="{hub}">Back to your Aadi products</a></p></body></html>"""


def read_session(request: Request) -> dict | None:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    try:
        return _serializer(request.app.state.settings, "session").loads(raw, max_age=SESSION_SECONDS)
    except BadSignature:
        return None


def _set_cookie(resp, name: str, value: str, settings: Settings, max_age: int) -> None:
    resp.set_cookie(name, value, max_age=max_age, httponly=True, secure=settings.app_base_url.startswith("https"), samesite="lax", path="/")


def record_login(claims: dict) -> str | None:
    """Remember the person and find their account. Returns None when they have one, else the reason they cannot enter.
    The first person of a company becomes its administrator; everyone else needs an account an administrator created."""
    from aadi_org.service import OrgError, OrgService
    from app.org import CATALOG, M
    tid, sub = claims["tid"], claims["sub"]
    with database.session() as db:
        user = db.scalar(select(AppUser).where(AppUser.tenant_id == tid, AppUser.user_id == sub))
        if user is None:
            db.add(AppUser(tenant_id=tid, user_id=sub, email=claims.get("email", ""), name=claims.get("name", "")))
        else:
            user.email, user.name, user.last_login_at = claims.get("email", user.email), claims.get("name", user.name), utcnow()
        try:
            member = OrgService(db, M, CATALOG).resolve(tid, sub, claims.get("email", ""), claims.get("name", ""), identity_id=sub)
        except OrgError as e:
            db.commit()
            return e.message
        db.commit()
        return None if member is not None else "You do not have an account in Academic Video Creation yet. Ask your administrator to add you, then sign in again."


def create_router(settings: Settings, oidc: OIDCClient) -> APIRouter:
    router = APIRouter()

    @router.get("/auth/login")
    def login(tenant: str | None = None):
        state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
        resp = RedirectResponse(oidc.authorize_url(state, nonce, verifier, tenant), 303)
        _set_cookie(resp, TX_COOKIE, _serializer(settings, "tx").dumps({"s": state, "n": nonce, "v": verifier}), settings, TX_SECONDS)
        return resp

    @router.get("/auth/callback")
    def callback(request: Request, code: str = "", state: str = "", error: str = ""):
        if error:
            raise HTTPException(401, "Sign-in was cancelled or refused.")
        try:
            tx = _serializer(settings, "tx").loads(request.cookies.get(TX_COOKIE, ""), max_age=TX_SECONDS)
        except BadSignature as exc:
            raise HTTPException(400, "The sign-in request expired. Please try again.") from exc
        if not code or not secrets.compare_digest(tx["s"], state):
            raise HTTPException(400, "The sign-in response does not match the request.")
        tokens = oidc.exchange(code, tx["v"])
        claims = oidc.verify_id_token(tokens.get("id_token", ""), tx["n"])
        refusal = record_login(claims)
        if refusal:
            return HTMLResponse(NO_ACCOUNT_PAGE.format(message=html.escape(refusal), hub=html.escape(settings.identity_issuer_url + "/")), 403)
        session = {"sub": claims["sub"], "tid": claims["tid"], "email": claims.get("email", ""), "name": claims.get("name", ""),
                   "slug": claims.get("tenant_slug", "")}
        resp = RedirectResponse("/", 303)
        _set_cookie(resp, SESSION_COOKIE, _serializer(settings, "session").dumps(session), settings, SESSION_SECONDS)
        resp.delete_cookie(TX_COOKIE, path="/")
        return resp

    @router.get("/auth/logout")
    def logout():
        target = f"{settings.identity_issuer_url}/logout?" + urlencode(
            {"client_id": settings.identity_client_id, "post_logout_redirect_uri": settings.app_base_url + "/"})
        resp = RedirectResponse(target, 303)
        resp.delete_cookie(SESSION_COOKIE, path="/")
        return resp

    return router
