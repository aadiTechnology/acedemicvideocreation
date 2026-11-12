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
    video_engine_auth: str = "key"  # key (shared X-Engine-Key) | auto (Identity token, key as fallback) | token (Identity token only)
    video_engine_client_id: str = ""  # Identity service client for calling the Video Engine (client_credentials)
    video_engine_client_secret: str = ""
    identity_product_secret: str = ""  # lets this product enrol its people in Aadi Identity (set with `python -m app.cli set-product-secret` on Identity)
    storage_dir: str = ""
    storage_provider: str = "local"   # "local" (a volume) or "b2" (Backblaze B2, S3-compatible)
    b2_endpoint: str = ""
    b2_key_id: str = ""
    b2_application_key: str = ""
    b2_bucket: str = ""
    b2_region: str = ""
    b2_url_expiry: int = 900          # seconds a playback or download link stays valid
    b2_move_on_start: bool = False    # on start, move videos still on the local volume into the bucket (background, repeatable)

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
        identity_product_secret=e.get("IDENTITY_PRODUCT_SECRET", "").strip(),
        video_engine_url=e.get("VIDEO_ENGINE_URL", "").rstrip("/"),
        video_engine_api_key=e.get("VIDEO_ENGINE_API_KEY", ""),
        video_engine_timeout=float(e.get("VIDEO_ENGINE_TIMEOUT_SECONDS", "30")),
        video_engine_auth=e.get("VIDEO_ENGINE_AUTH", "key").strip().lower() or "key",
        video_engine_client_id=e.get("VIDEO_ENGINE_CLIENT_ID", "").strip(),
        video_engine_client_secret=e.get("VIDEO_ENGINE_CLIENT_SECRET", "").strip(),
        storage_dir=e.get("STORAGE_LOCAL_DIR", "./storage"),
        storage_provider=e.get("STORAGE_PROVIDER", "local").strip().lower(),
        b2_endpoint=e.get("B2_ENDPOINT", "").strip(),
        b2_key_id=e.get("B2_KEY_ID", "").strip(),
        b2_application_key=e.get("B2_APPLICATION_KEY", "").strip(),
        b2_bucket=e.get("B2_BUCKET", "").strip(),
        b2_region=e.get("B2_REGION", "").strip(),
        b2_url_expiry=int(e.get("B2_URL_EXPIRY_SECONDS", "900")),
        b2_move_on_start=e.get("B2_MOVE_EXISTING_ON_START", "1").strip().lower() in ("1", "true", "yes"),
    )
    if s.video_engine_auth not in ("key", "auto", "token"):
        raise RuntimeError("VIDEO_ENGINE_AUTH must be key, auto or token.")
    if s.video_engine_auth != "key" and not (s.identity_issuer_url and s.video_engine_client_id and s.video_engine_client_secret):
        raise RuntimeError("VIDEO_ENGINE_AUTH=auto or token needs IDENTITY_ISSUER_URL, VIDEO_ENGINE_CLIENT_ID and VIDEO_ENGINE_CLIENT_SECRET.")
    if s.storage_provider not in ("local", "b2"):
        raise RuntimeError("STORAGE_PROVIDER must be local or b2.")
    if s.storage_provider == "b2" and not (s.b2_endpoint and s.b2_key_id and s.b2_application_key and s.b2_bucket):
        raise RuntimeError("STORAGE_PROVIDER=b2 needs B2_ENDPOINT, B2_KEY_ID, B2_APPLICATION_KEY and B2_BUCKET.")
    if s.is_production and s.auth_mode == "dev":
        raise RuntimeError("AUTH_MODE=dev is not allowed when APP_ENV=production.")
    return s
