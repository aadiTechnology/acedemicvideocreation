"""Academic data model. Every table carries tenant_id (the Aadi Identity company UUID) and a UUID primary key."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

LANGUAGES = ("en-IN", "hi-IN", "mr-IN")
REVIEW_STATUSES = ("draft", "in_review", "changes_required", "approved", "rejected")


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Tenanted:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppUser(Tenanted, Base):
    """A person who has signed in. user_id is the Aadi Identity user id (claim sub)."""

    __tablename__ = "app_users"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_app_user"),)
    user_id: Mapped[str] = mapped_column(String(64))
    email: Mapped[str] = mapped_column(String(200), default="")
    name: Mapped[str] = mapped_column(String(200), default="")
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserRole(Tenanted, Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "role", name="uq_user_role"),)
    user_id: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(32))


class SchoolClass(Tenanted, Base):
    __tablename__ = "school_classes"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_class_name"),)
    name: Mapped[str] = mapped_column(String(80))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Subject(Tenanted, Base):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("class_id", "name", name="uq_subject_name"),)
    class_id: Mapped[str] = mapped_column(ForeignKey("school_classes.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(120))


class Chapter(Tenanted, Base):
    __tablename__ = "chapters"
    __table_args__ = (UniqueConstraint("subject_id", "number", name="uq_chapter_number"),)
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))


class Topic(Tenanted, Base):
    __tablename__ = "topics"
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Lesson(Tenanted, Base):
    __tablename__ = "lessons"
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    learning_objectives: Mapped[list] = mapped_column(JSON, default=list)
    target_audience: Mapped[str] = mapped_column(String(200), default="")
    expected_duration_minutes: Mapped[int] = mapped_column(Integer, default=5)
    source_references: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class LessonVersion(Tenanted, Base):
    """One language version of a lesson: own narration (Sprint 5), review status and, later, video output."""

    __tablename__ = "lesson_versions"
    __table_args__ = (
        UniqueConstraint("lesson_id", "language", name="uq_lesson_language"),
        Index("ix_lesson_versions_status", "tenant_id", "review_status"),
    )
    lesson_id: Mapped[str] = mapped_column(ForeignKey("lessons.id", ondelete="RESTRICT"), index=True)
    language: Mapped[str] = mapped_column(String(8))
    review_status: Mapped[str] = mapped_column(String(24), default="draft")
    publication_status: Mapped[str | None] = mapped_column(String(24), nullable=True)  # reserved for a future student portal
    # imported content (Sprint 5): the canonical package is kept on disk; slides/lesson_plan are its normalized form
    slides: Mapped[list] = mapped_column(JSON, default=list)
    lesson_plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    package_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    package_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    package_filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    imported_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewEvent(Tenanted, Base):
    """History of review status changes. Approval is separate from video completion."""

    __tablename__ = "review_events"
    version_id: Mapped[str] = mapped_column(ForeignKey("lesson_versions.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(24))
    from_status: Mapped[str] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24))
    note: Mapped[str] = mapped_column(Text, default="")
    actor_id: Mapped[str] = mapped_column(String(64))
