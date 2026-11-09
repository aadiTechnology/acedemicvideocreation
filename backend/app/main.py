"""Academic Video Creation API."""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import db as database
from app.config import Settings, load_settings
from app import oidc
from app.routers import admin, lessons, structure

logger = logging.getLogger("academic")


def create_app(settings: Settings | None = None, oidc_http=None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="Aadi Academic Video Creation", version="0.1.0")
    app.state.settings = settings
    if settings.database_url:
        database.init_db(settings.database_url)

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
    for router in (*structure.routers, lessons.router, admin.router):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
