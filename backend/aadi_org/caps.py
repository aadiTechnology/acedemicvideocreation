"""Capability model. A capability is "<area>.<action>", optionally with a scope: "sprint.view:team".

Scopes, widest first: all > team > assigned > own. Roles are data (stored per company) and code only ever checks
capabilities, never role names. What "team", "assigned" and "own" mean is product data, so each product resolves scopes itself;
this module only answers "which is the widest scope this person holds for a capability".

Extracted from Aadi Project Tracker's perms.py and core.py so every product answers the question the same way."""
from __future__ import annotations

from typing import Iterable

SCOPES = ("all", "team", "assigned", "own")


class PermissionDenied(Exception):
    def __init__(self, message: str = "Your role does not allow this action.", code: str = "FORBIDDEN") -> None:
        super().__init__(message)
        self.message, self.code = message, code


def split(cap: str) -> tuple[str, str | None]:
    base, _, scope = cap.partition(":")
    return base, (scope or None)


class Access:
    """What one person may do, from the capabilities of their role."""

    def __init__(self, caps: Iterable[str]) -> None:
        self.caps = frozenset(caps)

    def scope(self, cap: str) -> str | None:
        """The widest scope held for ``cap``; an unscoped capability returns "all"; not held returns None."""
        for s in SCOPES:
            if f"{cap}:{s}" in self.caps:
                return s
        return "all" if cap in self.caps else None

    def has(self, cap: str) -> bool:
        return self.scope(cap) is not None

    def require(self, cap: str) -> str:
        s = self.scope(cap)
        if s is None:
            raise PermissionDenied()
        return s

    def __repr__(self) -> str:  # pragma: no cover
        return f"Access({len(self.caps)} capabilities)"
