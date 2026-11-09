"""Migrations must work on a database that already holds data (production), not only on an empty one."""

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app import migrate
from tests.conftest import TEST_URL


def _cfg() -> Config:
    cfg = Config(str(migrate.ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(migrate.ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_URL)
    return cfg


def test_upgrade_to_head_keeps_existing_rows_and_backfills_defaults(database):
    with database.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    command.upgrade(_cfg(), "0002")
    with database.begin() as c:
        c.execute(text("INSERT INTO school_classes (id, tenant_id, created_at, name, sort_order) VALUES ('c1','t1',now(),'Class 7',0)"))
        c.execute(text("INSERT INTO subjects (id, tenant_id, created_at, class_id, name) VALUES ('s1','t1',now(),'c1','Science')"))
        c.execute(text("INSERT INTO chapters (id, tenant_id, created_at, subject_id, number, title) VALUES ('ch1','t1',now(),'s1',1,'Plants')"))
        c.execute(text("INSERT INTO topics (id, tenant_id, created_at, chapter_id, title, sort_order) VALUES ('t1x','t1',now(),'ch1','Photo',0)"))
        c.execute(text("INSERT INTO lessons (id, tenant_id, created_at, topic_id, title, description, learning_objectives, target_audience,"
                       " expected_duration_minutes, source_references, updated_at) VALUES ('l1','t1',now(),'t1x','L','','[]','',5,'[]',now())"))
        c.execute(text("INSERT INTO lesson_versions (id, tenant_id, created_at, lesson_id, language, review_status) VALUES ('v1','t1',now(),'l1','en-IN','draft')"))
    command.upgrade(_cfg(), "head")
    with database.connect() as c:
        row = c.execute(text("SELECT slides::text, review_note, review_status FROM lesson_versions WHERE id='v1'")).one()
    assert row == ("[]", "", "draft")
