"""What a product tells the kit about itself: its features, capabilities and default roles.

Every product supplies one ``ProductCatalog``. The kit stores roles per company as data, seeds them from these defaults, and
validates every change against the catalog, so a role can never hold a capability the product does not know."""
from __future__ import annotations

from dataclasses import dataclass, field

from aadi_org.caps import SCOPES, split

ORG_CAPABILITIES = [
    ("org.users.view", "See people and departments"),
    ("org.users.manage", "Add, change and suspend people"),
    ("org.departments.manage", "Create and change departments"),
    ("org.roles.manage", "Change what each role may do"),
    ("audit.view", "See the activity log"),
]


@dataclass(frozen=True)
class Capability:
    key: str                       # "<area>.<action>"
    label: str
    scopes: tuple[str, ...] = ()   # allowed scopes; empty = not scoped
    feature: str = ""              # groups capabilities in the roles screen


@dataclass(frozen=True)
class RoleDef:
    key: str
    name: str
    caps: tuple[str, ...] = ()
    description: str = ""
    all_capabilities: bool = False  # the administrator role: everything in the catalog


@dataclass
class ProductCatalog:
    product: str
    capabilities: list[Capability]
    roles: list[RoleDef]
    admin_role: str = "admin"
    default_role: str = ""  # role given to a person added without one; should be the least powerful (defaults to the last role listed)
    features: dict[str, str] = field(default_factory=dict)  # key -> label, for the roles screen

    def __post_init__(self) -> None:
        have = {c.key for c in self.capabilities}
        for key, label in ORG_CAPABILITIES:
            if key not in have:
                self.capabilities.append(Capability(key, label, (), "organization"))
        self.features.setdefault("organization", "People and roles")
        self.by_key = {c.key: c for c in self.capabilities}
        keys = {r.key for r in self.roles}
        if self.admin_role not in keys:
            raise ValueError(f"the catalog has no '{self.admin_role}' role")
        if self.default_role and self.default_role not in keys:
            raise ValueError(f"the catalog has no '{self.default_role}' role")
        bad = [f"{r.key}: {e}" for r in self.roles for e in self.problems(self.role_caps(r))]
        if bad:
            raise ValueError("invalid default roles: " + "; ".join(bad))

    def role_caps(self, role: RoleDef) -> list[str]:
        """Capabilities of a default role; the administrator holds everything (scoped ones at 'all')."""
        if role.all_capabilities or role.key == self.admin_role:
            return [f"{c.key}:all" if c.scopes else c.key for c in self.capabilities]
        return list(role.caps)

    def problems(self, caps: list[str]) -> list[str]:
        """Plain-words problems with a list of capabilities; empty when it is valid."""
        out: list[str] = []
        for cap in caps:
            base, scope = split(cap)
            c = self.by_key.get(base)
            if c is None:
                out.append(f"'{cap}' is not a capability of this product")
            elif scope is None and c.scopes:
                out.append(f"'{cap}' needs a scope: {', '.join(c.scopes)}")
            elif scope is not None and (not c.scopes or scope not in c.scopes or scope not in SCOPES):
                out.append(f"'{cap}' has a scope that {base} does not allow")
        return out

    def describe(self) -> dict:
        return {"product": self.product, "features": self.features, "admin_role": self.admin_role,
                "default_roles": [{"key": r.key, "name": r.name, "description": r.description} for r in self.roles],
                "capabilities": [{"key": c.key, "label": c.label, "scopes": list(c.scopes), "feature": c.feature or c.key.split(".")[0]} for c in self.capabilities]}
