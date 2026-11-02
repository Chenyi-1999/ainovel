import os
import re

import redis
from fastapi import HTTPException
from sqlalchemy import case, literal, or_, select

from .db import Chapter, Job, Memory, Novel, Version

KINDS = {"summary", "character", "setting", "timeline", "foreshadow"}


def get_or_404(db, model, row_id):
    row = db.get(model, row_id)
    if not row:
        raise HTTPException(404, "内容不存在")
    return row


def assert_idle(db, novel_id):
    # Serialize task creation with edits to close the check-then-write race.
    db.scalar(select(Novel).where(Novel.id == novel_id).with_for_update())
    if db.scalar(select(Job.id).where(Job.novel_id == novel_id, Job.status.in_(["pending", "running"]))):
        raise HTTPException(409, "本书有正在执行的任务，请等待完成或停止任务后编辑")


def invalidate_from(db, chapter):
    later = db.scalars(select(Chapter).where(Chapter.novel_id == chapter.novel_id,
                                           Chapter.number >= chapter.number)).all()
    ids = [row.id for row in later]
    for row in later:
        row.memory_dirty = True
    chapter.status = "draft"
    for memory in db.scalars(select(Memory).where(Memory.source_chapter_id.in_(ids))).all():
        memory.stale = True


def save_edit(db, chapter, title, content):
    if title == chapter.title and content == chapter.content:
        return
    db.add(Version(chapter_id=chapter.id, revision=chapter.revision,
                   title=chapter.title, content=chapter.content))
    chapter.title, chapter.content = title, content
    chapter.revision += 1
    invalidate_from(db, chapter)


def retrieve_memory(db, novel_id, query, limit=18, before_number=None):
    stmt = select(Memory).outerjoin(Chapter, Memory.source_chapter_id == Chapter.id).where(
        Memory.novel_id == novel_id, Memory.stale.is_(False), Memory.provenance != "legacy",
        or_(Memory.visibility == "public",
            (Memory.provenance == "manual") & Memory.source_chapter_id.is_(None) &
            (Memory.kind == "setting") & (Memory.visibility == "unknown")),
        or_(Memory.source_chapter_id.is_(None),
            (Chapter.status == "confirmed") & Chapter.memory_dirty.is_(False) &
            (Memory.source_revision == Chapter.revision) & (Memory.evidence_quote != "")))
    if before_number is not None:
        stmt = stmt.where(or_(Memory.source_chapter_id.is_(None), Chapter.number < before_number))
    # Score BEFORE limiting: an ancient relevant fact must remain accessible after
    # thousands of new chapters. Bound terms and returned rows, not novel history.
    candidates = re.findall(r"[A-Za-z0-9_]{2,}", query)
    for segment in re.findall(r"[\u4e00-\u9fff]+", query):
        candidates.extend(segment[i:i+2] for i in range(len(segment)-1))
    terms = list(dict.fromkeys(candidates))[:32]
    score = literal(0)
    for term in terms:
        score = score + case((Memory.content.contains(term, autoescape=True), 1), else_=0)
    ranked = db.scalars(stmt.order_by(score.desc(), Memory.created_at.desc()).limit(max(60, limit * 4))).all()
    # Reserve slots for author settings and recent canonical summaries, preventing
    # keyword-heavy character facts from crowding out narrative continuity.
    manual = db.scalars(stmt.where(Memory.source_chapter_id.is_(None))
                        .order_by(score.desc(), Memory.created_at.desc()).limit(min(2, limit))).all()
    summaries = db.scalars(stmt.where(Memory.kind == "summary")
                           .order_by(Memory.created_at.desc()).limit(min(3, max(0, limit-len(manual))))).all()
    selected = []
    seen = set()
    reserved = list({row.id: row for row in [*manual, *summaries]}.values())
    for row in [*ranked[:max(0, limit-len(reserved))], *reserved, *ranked]:
        if row.id not in seen:
            selected.append(row)
            seen.add(row.id)
        if len(selected) >= limit:
            break
    return [{"kind": row.kind, "content": row.content,
             "source_chapter_id": row.source_chapter_id,
             "source_revision": row.source_revision, "evidence_quote": row.evidence_quote,
             "source_number": db.get(Chapter, row.source_chapter_id).number if row.source_chapter_id else None}
            for row in selected if not row.source_chapter_id or row.evidence_quote in db.get(Chapter, row.source_chapter_id).content]


def wake_worker():
    try:
        client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"),
                                      socket_connect_timeout=1, socket_timeout=1)
        client.lpush("ainovel:wakeup", "1")
        client.ltrim("ainovel:wakeup", 0, 99)
    except redis.RedisError:
        pass  # The database job remains durable and the worker polls it.
