"""Settings from environment variables. Names are documented in .env.example; values never live in git."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _normalise_url(url: str) -> str:
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    auth_mode: str  # "oidc" (Aadi Identity) or "dev" (local development only)
    app_base_url: str
    session_secret: str
    identity_issuer_url: str
    identity_client_id: str
    identity_client_secret: str
    identity_product_key: str
    video_engine_url: str
    video_engine_api_key: str
    video_engine_timeout: float
    storage_dir: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def load_settings(env=None) -> Settings:
    e = os.environ if env is None else env
    s = Settings(
        app_env=e.get("APP_ENV", "development"),
        database_url=_normalise_url(e.get("DATABASE_URL", "")),
        auth_mode=e.get("AUTH_MODE", "oidc"),
        app_base_url=e.get("APP_BASE_URL", "http://localhost:5174").rstrip("/"),
        session_secret=e.get("SESSION_SECRET", ""),
        identity_issuer_url=e.get("IDENTITY_ISSUER_URL", "").rstrip("/"),
        identity_client_id=e.get("IDENTITY_CLIENT_ID", ""),
        identity_client_secret=e.get("IDENTITY_CLIENT_SECRET", ""),
        identity_product_key=e.get("IDENTITY_PRODUCT_KEY", "academics"),
        video_engine_url=e.get("VIDEO_ENGINE_URL", "").rstrip("/"),
        video_engine_api_key=e.get("VIDEO_ENGINE_API_KEY", ""),
        video_engine_timeout=float(e.get("VIDEO_ENGINE_TIMEOUT_SECONDS", "30")),
        storage_dir=e.get("STORAGE_LOCAL_DIR", "./storage"),
    )
    if s.is_production and s.auth_mode == "dev":
        raise RuntimeError("AUTH_MODE=dev is not allowed when APP_ENV=production.")
    return s
