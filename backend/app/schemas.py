from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Language = Literal["en-IN", "hi-IN", "mr-IN"]


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ClassIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    sort_order: int = 0


class ClassOut(_Out, ClassIn):
    id: str


class SubjectIn(BaseModel):
    class_id: str
    name: str = Field(min_length=1, max_length=120)


class SubjectOut(_Out, SubjectIn):
    id: str


class ChapterIn(BaseModel):
    subject_id: str
    number: int = Field(ge=1, le=999)
    title: str = Field(min_length=1, max_length=200)


class ChapterOut(_Out, ChapterIn):
    id: str


class TopicIn(BaseModel):
    chapter_id: str
    title: str = Field(min_length=1, max_length=200)
    sort_order: int = 0


class TopicOut(_Out, TopicIn):
    id: str


class LessonCreate(BaseModel):
    topic_id: str
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    learning_objectives: list[str] = []
    target_audience: str = Field(default="", max_length=200)
    expected_duration_minutes: int = Field(default=5, ge=1, le=120)
    source_references: list[str] = []
    languages: list[Language] = []


class LessonUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    learning_objectives: list[str] | None = None
    target_audience: str | None = Field(default=None, max_length=200)
    expected_duration_minutes: int | None = Field(default=None, ge=1, le=120)
    source_references: list[str] | None = None


class VersionOut(_Out):
    id: str
    lesson_id: str
    language: str
    review_status: str
    publication_status: str | None = None


class VersionCreate(BaseModel):
    language: Language


class LessonOut(_Out):
    id: str
    topic_id: str
    title: str
    description: str
    learning_objectives: list[str]
    target_audience: str
    expected_duration_minutes: int
    source_references: list[str]
    created_at: datetime
    versions: list[VersionOut] = []


class LessonRow(LessonOut):
    """List row with the academic path for display."""

    class_name: str
    subject_name: str
    chapter_number: int
    chapter_title: str
    topic_title: str
