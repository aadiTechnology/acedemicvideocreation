"""The Aadi-Test company in Academic Video Creation: the same 15 people (roles below), the three departments of the Matrix workbook, one class
with a science chapter and ONE APPROVED LESSON (refraction of light, English) so a developer can press "Make the video" straight away.
ALL NAMES ARE FICTIONAL. Keep PEOPLE identical to identity/app/test_tenant.py.

    python -m app.seed_aadi_test            add the company if it is missing (safe to repeat)
    python -m app.seed_aadi_test --reset    ERASES every row of every table (and the stored lesson and video files), then adds it. Asks you to type YES

The company id is the Aadi Identity company id, so Identity's "Aadi-Test" people land in it. People are added by email and linked on their
first sign-in (as an administrator adding someone would do). The lesson goes through the real API (import, review, approve), in-process."""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import sys
from pathlib import Path

from sqlalchemy import select, text

from app import db as database
from app.config import load_settings

TENANT_ID = "5ca1ab1e-aad1-4e57-8000-000000000001"  # the Aadi Identity company id of Aadi-Test
DOMAIN = "aadi-test.example.com"
SEED = Path(__file__).resolve().parent / "seed_data"

# first name: (full name, title, Academic role, department, manager first name)
PEOPLE = {
    "prajakta": ("Prajakta Kulkarni", "CEO", "admin", "Management", None),
    "akanksha": ("Akanksha Joshi", "Project Manager", "reviewer", "Software Development", "prajakta"),
    "aarti": ("Aarti Deshmukh", "Product Owner", "content_operator", "Software Development", "prajakta"),
    "kalyani": ("Kalyani Patil", "Team Lead", "content_operator", "Software Development", "akanksha"),
    "namrata": ("Namrata More", "Software Engineer", "production_operator", "Software Development", "kalyani"),
    "aman": ("Aman Shah", "Software Engineer", "viewer", "Software Development", "kalyani"),
    "anjali": ("Anjali Rao", "Software Engineer", "production_operator", "Software Development", "kalyani"),
    "prital": ("Prital Naik", "Software Engineer", "viewer", "Software Development", "kalyani"),
    "anushka": ("Anushka Iyer", "QA Engineer", "viewer", "Software Development", "kalyani"),
    "ankita": ("Ankita Sawant", "Software Engineer", "viewer", "Software Development", "kalyani"),
    "manasi": ("Manasi Gokhale", "Marketing Lead", "viewer", "Marketing & Sales", "prajakta"),
    "gayatri": ("Gayatri Pawar", "Marketing Executive", "viewer", "Marketing & Sales", "manasi"),
    "jyoti": ("Jyoti Menon", "Finance Manager", "viewer", "Marketing & Sales", "prajakta"),
    "dhande": ("Dhande Kamat", "Delivery Manager", "viewer", "Marketing & Sales", "prajakta"),
    "pravin": ("Pravin Dixit", "Sales Lead", "viewer", "Marketing & Sales", "prajakta"),
}
DEPARTMENTS = ("Management", "Software Development", "Marketing & Sales")


def email_of(first: str) -> str:
    return f"{first}@{DOMAIN}"


def _settings():
    """The running settings, but with the development sign-in so the seed can call the API as a person without a browser session."""
    return dataclasses.replace(load_settings(), auth_mode="dev", app_env="seed")


def seed(settings=None) -> bool:
    """Adds the company if it is missing. Returns True when something was added."""
    from fastapi.testclient import TestClient

    from aadi_org.service import OrgService
    from app.main import create_app
    from app.org import CATALOG, M

    s = settings or _settings()
    with database.session() as db:
        svc = OrgService(db, M, CATALOG)
        if db.scalar(select(M.Member).where(M.Member.tenant_id == TENANT_ID)):
            return False
        svc.ensure_roles(TENANT_ID)
        dept = {n: svc.create_department(TENANT_ID, "seed", n)["id"] for n in DEPARTMENTS}
        roles = {r.key: r.id for r in db.scalars(select(M.Role).where(M.Role.tenant_id == TENANT_ID))}
        made: dict[str, str] = {}
        for first, (name, title, role, dname, mgr) in PEOPLE.items():
            out = svc.create_member(TENANT_ID, "seed", email_of(first), name, roles[role], title, dept[dname], made.get(mgr) if mgr else None)
            made[first] = out["id"]
        db.commit()
    app = create_app(s)
    h = {"X-Dev-Tenant": TENANT_ID, "X-Dev-User": "seed", "X-Dev-Email": f"seed-runner@{DOMAIN}"}  # not a member: nobody gets linked to the seed run
    with TestClient(app) as c:
        def post(path, body, roles):
            r = c.post("/api" + path, json=body, headers={**h, "X-Dev-Roles": roles})
            assert r.status_code in (200, 201), (path, r.status_code, r.text)
            return r.json()

        cls = post("/classes", {"name": "Class 10"}, "admin")
        sub = post("/subjects", {"class_id": cls["id"], "name": "Science"}, "admin")
        ch = post("/chapters", {"subject_id": sub["id"], "number": 10, "title": "Light: Reflection and Refraction"}, "admin")
        top = post("/topics", {"chapter_id": ch["id"], "title": "Refraction of light"}, "admin")
        lesson = post("/lessons", {"topic_id": top["id"], "title": "Refraction of light", "expected_duration_minutes": 2, "learning_objectives": ["Explain refraction"],
                                   "languages": ["en-IN"]}, "content_operator")
        vid = lesson["versions"][0]["id"]
        files = [("files", ("lesson.csv", (SEED / "refraction" / "lesson.csv").read_bytes(), "text/csv")),
                 ("files", ("lesson_plan.json", (SEED / "refraction" / "lesson_plan.json").read_bytes(), "application/json"))]
        r = c.post(f"/api/lesson-versions/{vid}/import", files=files, headers={**h, "X-Dev-Roles": "content_operator"})
        assert r.status_code == 200, r.text
        post(f"/lesson-versions/{vid}/review", {"action": "submit"}, "content_operator")
        post(f"/lesson-versions/{vid}/review", {"action": "approve"}, "reviewer")
    with database.session() as db:  # the development sign-in makes a member for the seed runner; remove it so only the 15 people remain
        from sqlalchemy import delete

        db.execute(delete(M.Member).where(M.Member.tenant_id == TENANT_ID, M.Member.user_id == "seed"))
        from app.models import AppUser, UserRole

        db.execute(delete(AppUser).where(AppUser.tenant_id == TENANT_ID, AppUser.user_id == "seed"))
        db.execute(delete(UserRole).where(UserRole.tenant_id == TENANT_ID, UserRole.user_id == "seed"))
        db.commit()
    return True


def wipe(db, storage_dir: str | None = None) -> dict:
    """Deletes every row of every table (except the migration marker and the maintenance log) and the stored lesson and video files on the local volume."""
    from sqlalchemy import delete

    from app.models import Base
    from app.org import M  # noqa: F401  (the kit's tables are part of the same metadata)

    counts = {}
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in ("alembic_version", "maintenance_runs"):
            continue
        counts[table.name] = db.execute(delete(table)).rowcount
    root = Path(storage_dir or os.environ.get("STORAGE_LOCAL_DIR", "./storage"))
    removed = 0
    if root.is_dir():
        for child in root.iterdir():
            shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)
            removed += 1
    return {**{k: v for k, v in counts.items() if v}, "stored_items_removed": removed}


def maintenance_once(maintenance_id: str, settings=None) -> dict | None:
    """Wipe and seed once per id (restarting with the same id does nothing). Returns what was done, or None when this id already ran."""
    with database.session() as db:
        if db.execute(text("SELECT 1 FROM maintenance_runs WHERE id = :i"), {"i": maintenance_id}).first():
            db.rollback()
            return None
        s = settings or load_settings()
        counts = wipe(db, s.storage_dir)
        db.commit()
    seeded = seed(dataclasses.replace(s, auth_mode="dev", app_env="seed"))
    with database.session() as db:
        db.execute(text("INSERT INTO maintenance_runs (id, note) VALUES (:i, :n)"), {"i": maintenance_id, "n": json.dumps({"wiped": counts, "seeded": seeded})})
        db.commit()
    return {"wiped": counts, "seeded": seeded}


def run_if_requested() -> None:
    """Called when the app starts: the one-time maintenance, only when all three variables are set (it then runs once per id)."""
    if os.environ.get("APP_MAINTENANCE") == "reset-and-seed-aadi-test" and os.environ.get("APP_MAINTENANCE_CONFIRM") == "ERASE-ALL-DATA" and os.environ.get("APP_MAINTENANCE_ID"):
        out = maintenance_once(os.environ["APP_MAINTENANCE_ID"])
        print("Maintenance:", "already done for this id" if out is None else out, flush=True)


def main(argv: list[str]) -> None:
    settings = load_settings()
    if settings.is_production and os.environ.get("APP_ALLOW_TEST_SEED") != "yes":
        raise SystemExit("Refusing to seed in production. Set APP_ALLOW_TEST_SEED=yes only on purpose.")
    database.init_db(settings.database_url)
    if "--reset" in argv:
        if "--yes" not in argv and input("This ERASES everything in this database and the stored files. Type YES to continue: ").strip() != "YES":
            raise SystemExit("Cancelled. Nothing was changed.")
        with database.session() as db:
            print("Erased:", wipe(db, settings.storage_dir))
            db.commit()
    added = seed(_settings())
    print("Aadi-Test added." if added else "Aadi-Test is already there; nothing to do.", "Sign in through Aadi Identity with any Aadi-Test person.")


if __name__ == "__main__":
    main(sys.argv[1:])
