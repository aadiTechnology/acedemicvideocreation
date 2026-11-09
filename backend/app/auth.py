"""Current user. Sprint 4 ships the dependency with a local-development mode; OIDC sign-in (Aadi Identity) is Sprint 4b."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    tenant_id: str
    email: str = ""
    roles: tuple[str, ...] = field(default_factory=tuple)


def current_user(request: Request) -> CurrentUser:
    settings = request.app.state.settings
    if settings.auth_mode == "dev":
        # Local development only (refused when APP_ENV=production). Headers let tests act as different tenants.
        h = request.headers
        return CurrentUser(
            user_id=h.get("x-dev-user", "dev-user"),
            tenant_id=h.get("x-dev-tenant", "dev-tenant"),
            email="dev@example.test",
            roles=("content_operator", "reviewer", "production_operator"),
        )
    raise HTTPException(status_code=401, detail="Not signed in.")
