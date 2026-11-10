"""Academic Video Creation API."""

from __future__ import annotations

import logging
import threading
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import db as database
from app.config import Settings, load_settings
from app import oidc
from app.engine_client import EngineClient
from app.storage import make_store
from app.identity_client import IdentityClient, IdentityHooks
from aadi_org.router import create_org_router
from app.auth import principal
from app.org import CATALOG, M
from app.routers import assessment, lessons, slides, structure, versions, video

logger = logging.getLogger("academic")


def _move_existing(store) -> None:
    """Background, repeatable: videos still on the local volume go to the bucket; a local file is deleted only after its upload is confirmed."""
    from app.tools.move_to_b2 import move
    gen = database.get_db()
    try:
        session = next(gen)
        stats = move(store, session)
        logger.info("move-to-b2: %s", stats)
    except Exception:  # noqa: BLE001 - this must never stop the app
        logger.exception("move-to-b2 failed")
    finally:
        gen.close()


def create_app(settings: Settings | None = None, oidc_http=None, identity_http=None, engine_http=None, object_store=None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="Aadi Academic Video Creation", version="0.1.0")
    app.state.settings = settings
    app.state.engine = EngineClient(settings, engine_http)
    app.state.store = object_store if object_store is not None else make_store(settings)  # None: files stay on the local volume
    if settings.database_url:
        database.init_db(settings.database_url)
    if app.state.store is not None and settings.b2_move_on_start and settings.database_url:
        threading.Thread(target=_move_existing, args=(app.state.store,), name="move-to-b2", daemon=True).start()

    @app.middleware("http")
    async def correlation(request: Request, call_next):
        cid = request.headers.get("x-correlation-id") or uuid.uuid4().hex
        request.state.correlation_id = cid
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = cid
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logger.exception("unhandled error corr=%s", getattr(request.state, "correlation_id", "-"))
        return JSONResponse({"detail": "Something went wrong.", "correlation_id": getattr(request.state, "correlation_id", "")}, status_code=500)

    @app.get("/api/me")
    def me(request: Request):
        from app.auth import current_user
        user = current_user(request, principal(request))
        return {"user_id": user.user_id, "tenant_id": user.tenant_id, "email": user.email, "name": user.name, "roles": list(user.roles), "caps": sorted(user.caps),
                "hub_url": settings.identity_issuer_url + "/" if settings.auth_mode == "oidc" and settings.identity_issuer_url else ""}

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        try:
            with database.get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001
            return JSONResponse({"status": "database unavailable"}, status_code=503)
        return {"status": "ready"}

    if settings.auth_mode == "oidc":
        if not (settings.session_secret and settings.identity_issuer_url and settings.identity_client_id):
            logger.warning("OIDC sign-in is not configured: set SESSION_SECRET and the IDENTITY_* variables.")
        else:
            app.include_router(oidc.create_router(settings, oidc.OIDCClient(settings, oidc_http)))
    org_router = create_org_router(get_db=database.get_db, principal=principal, M=M, catalog=CATALOG, hooks=IdentityHooks(IdentityClient(settings, identity_http)))
    for router in (*structure.routers, lessons.router, org_router, versions.router, assessment.router, video.router, slides.router, slides.layouts_router):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
