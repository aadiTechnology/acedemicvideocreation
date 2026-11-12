"""The Aadi-Test company: people with roles, departments, an approved lesson, and the one-time maintenance."""
from sqlalchemy import func, select

from app import db as database
from app import seed_aadi_test as st
from app.org import M
from app.models import Lesson, LessonVersion
from tests.conftest import TEST_URL, make_settings


def run_seed():
    settings = make_settings()
    return st.seed(settings)


def test_seed_adds_people_departments_and_an_approved_lesson(client):
    assert run_seed() is True
    with database.session() as db:
        members = db.scalars(select(M.Member).where(M.Member.tenant_id == st.TENANT_ID)).all()
        assert len(members) == 15 and all(m.status == "invited" and m.user_id is None for m in members)  # linked on first sign-in
        roles = {r.id: r.key for r in db.scalars(select(M.Role).where(M.Role.tenant_id == st.TENANT_ID))}
        by_email = {m.email: roles[m.role_id] for m in members}
        assert by_email["prajakta@aadi-test.example.com"] == "admin" and by_email["akanksha@aadi-test.example.com"] == "reviewer"
        assert by_email["namrata@aadi-test.example.com"] == "production_operator" and by_email["aman@aadi-test.example.com"] == "viewer"
        assert db.scalar(select(func.count()).select_from(M.Department).where(M.Department.tenant_id == st.TENANT_ID)) == 3
        v = db.scalar(select(LessonVersion).where(LessonVersion.tenant_id == st.TENANT_ID))
        assert v.review_status == "approved" and v.package_path and db.scalar(select(func.count()).select_from(Lesson)) == 1


def test_seed_is_repeatable_and_a_person_links_on_first_sign_in(client):
    assert run_seed() is True
    assert run_seed() is False
    from aadi_org.service import OrgService
    from app.org import CATALOG
    with database.session() as db:
        m = OrgService(db, M, CATALOG).resolve(st.TENANT_ID, "identity-user-1", "Prajakta@aadi-test.example.com", "Prajakta Kulkarni", identity_id="identity-user-1")
        assert m is not None and m.status == "active" and m.user_id == "identity-user-1"
        db.commit()


def test_maintenance_wipes_and_runs_once_per_id(client):
    run_seed()
    s = make_settings()
    first = st.maintenance_once("run-1", s)
    assert first and first["seeded"] is True and first["wiped"]["lessons"] == 1
    assert st.maintenance_once("run-1", s) is None
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(Lesson)) == 1
    assert st.maintenance_once("run-2", s)["seeded"] is True
