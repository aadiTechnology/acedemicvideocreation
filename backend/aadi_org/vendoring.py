"""A product carries a pinned copy of the kit (so a build never needs the private repository). ``tools/vendor.py install`` writes
KIT_MANIFEST.json beside the copy: the kit version and a SHA-256 for every file. A product test calls ``verify`` so a hand edit
of the copy, or a copy that does not match its recorded version, fails the build instead of drifting silently."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

MANIFEST = "KIT_MANIFEST.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()  # line endings must not matter


def build(folder: Path, version: str, pattern: str = "*.py") -> dict:
    files = {p.name: digest(p) for p in sorted(folder.glob(pattern)) if p.is_file()}
    return {"kit": "aadi-org-kit", "version": version, "files": files}


def verify(folder: Path | str, expected_version: str | None = None) -> list[str]:
    """Problems with a vendored copy; empty when it is exactly the recorded kit version."""
    folder = Path(folder)
    mf = folder / MANIFEST
    if not mf.is_file():
        return [f"{MANIFEST} is missing: install the kit with tools/vendor.py"]
    rec = json.loads(mf.read_text(encoding="utf-8"))
    problems = []
    if expected_version and rec.get("version") != expected_version:
        problems.append(f"the copy is kit {rec.get('version')} but this product expects {expected_version}")
    now = {p.name: digest(p) for p in folder.glob("*.py")}
    for name, h in rec["files"].items():
        if name not in now:
            problems.append(f"{name} is missing from the copy")
        elif now[name] != h:
            problems.append(f"{name} was edited: change the kit and install it again, never edit the copy")
    problems += [f"{n} is not part of kit {rec.get('version')}" for n in now if n not in rec["files"]]
    return problems
