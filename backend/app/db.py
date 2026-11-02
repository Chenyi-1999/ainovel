"""Durable state. PostgreSQL is the source of truth; Redis only wakes the worker."""
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Novel(Base):
    __tablename__ = "novels"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(240), default="未命名小说")
    premise: Mapped[str] = mapped_column(Text)
    genre: Mapped[str] = mapped_column(String(100), default="")
    style: Mapped[str] = mapped_column(Text, default="")
    planned_chapters: Mapped[int] = mapped_column(Integer, default=100)
    outline: Mapped[dict] = mapped_column(JSON, default=dict)
    context_revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (UniqueConstraint("novel_id", "number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    memory_dirty: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Version(Base):
    __tablename__ = "versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Memory(Base):
    __tablename__ = "memories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"), index=True)
    source_chapter_id: Mapped[str | None] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    source_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_quote: Mapped[str] = mapped_column(Text, default="")
    provenance: Mapped[str] = mapped_column(String(20), default="manual")
    visibility: Mapped[str] = mapped_column(String(20), default="unknown")
    known_by_entity_ids: Mapped[list] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Job(Base):
    __tablename__ = "jobs"
    # Only one mutation-producing task per novel. This also serializes API races.
    __table_args__ = (Index("uq_active_novel_job", "novel_id", unique=True,
                           postgresql_where=text("status IN ('pending', 'running')"),
                           sqlite_where=text("status IN ('pending', 'running')")),
                      Index("uq_job_idempotency", "novel_id", "idempotency_key", unique=True))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current: Mapped[int] = mapped_column(Integer, default=0)
    count: Mapped[int] = mapped_column(Integer, default=1)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_token: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Setting(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class Usage(Base):
    __tablename__ = "usage"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    model: Mapped[str] = mapped_column(String(160))
    purpose: Mapped[str] = mapped_column(String(30))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    novel_id: Mapped[str | None] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(240))
    category: Mapped[str] = mapped_column(String(100))
    task_kind: Mapped[str] = mapped_column(String(30))
    genre_tags: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    source_label: Mapped[str] = mapped_column(String(100), default="用户原创")


class PromptRevision(Base):
    __tablename__ = "prompt_revisions"
    __table_args__ = (UniqueConstraint("prompt_id", "revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    prompt_id: Mapped[str] = mapped_column(ForeignKey("prompt_templates.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StoryEntity(Base):
    __tablename__ = "story_entities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(240))
    kind: Mapped[str] = mapped_column(String(30))
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)


class StoryRelation(Base):
    __tablename__ = "story_relations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"), index=True)
    source_entity_id: Mapped[str] = mapped_column(ForeignKey("story_entities.id"))
    target_entity_id: Mapped[str] = mapped_column(ForeignKey("story_entities.id"))
    label: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    basis: Mapped[str] = mapped_column(String(20))
    memory_id: Mapped[str | None] = mapped_column(ForeignKey("memories.id"), nullable=True)
    memory_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)


class Foreshadow(Base):
    __tablename__ = "foreshadows"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    novel_id: Mapped[str] = mapped_column(ForeignKey("novels.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    target_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    events: Mapped[list] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=1)


database_url = os.getenv("DATABASE_URL", "sqlite:///./ainovel.db")
engine = create_engine(database_url, pool_pre_ping=True, **(
    {"connect_args": {"check_same_thread": False}} if database_url.startswith("sqlite")
    else {"pool_size": 3, "max_overflow": 2}))
Session = sessionmaker(engine, expire_on_commit=False)


def initialize():
    from .migrations import check_schema
    check_schema(engine)
    from .prompts import seed_prompts
    with Session() as db:
        seed_prompts(db)
        db.commit()


def serialize(row):
    return {column.name: (value.isoformat() if isinstance(value, datetime) else value)
            for column in row.__table__.columns
            for value in [getattr(row, column.name)]}
