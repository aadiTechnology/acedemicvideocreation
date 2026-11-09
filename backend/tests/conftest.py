"""Tests need PostgreSQL. Start a local one, for example:
docker run -d --name academic-test-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=academic_test -p 15441:5432 postgres:16-alpine
Override with ACADEMIC_TEST_DATABASE_URL.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app import migrate
from app.config import Settings, _normalise_url
from app.main import create_app

TEST_URL = _normalise_url(os.environ.get("ACADEMIC_TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:15441/academic_test"))


def make_settings(**over) -> Settings:
    base = dict(app_env="test", database_url=TEST_URL, auth_mode="dev", app_base_url="http://testserver", session_secret="test-secret",
                identity_issuer_url="", identity_client_id="", identity_client_secret="", identity_product_key="academics",
                video_engine_url="", video_engine_api_key="", video_engine_timeout=5.0)
    base.update(over)
    return Settings(**base)


@pytest.fixture(scope="session", autouse=True)
def database():
    eng = create_engine(TEST_URL)
    try:
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        pytest.skip("PostgreSQL test database is not reachable", allow_module_level=True)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    migrate.upgrade(TEST_URL)
    yield eng


@pytest.fixture(autouse=True)
def clean(database):
    with database.begin() as c:
        c.execute(text("TRUNCATE lesson_versions, lessons, topics, chapters, subjects, school_classes, user_roles, app_users CASCADE"))


@pytest.fixture()
def client():
    with TestClient(create_app(make_settings())) as c:
        yield c


def as_tenant(tenant: str, user: str = "u1") -> dict:
    return {"X-Dev-Tenant": tenant, "X-Dev-User": user}
