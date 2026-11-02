"""Story facts stay attributable. Staleness is derived, never hidden by edits."""
import hashlib
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from .auth import require_auth
from .db import Chapter, Foreshadow, Job, Memory, Novel, StoryEntity, StoryRelation, serialize, uid
from .dependencies import database
from .services import assert_idle, get_or_404, KINDS

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])
MemoryKind = Literal["summary", "character", "setting", "timeline", "foreshadow"]
Visibility = Literal["unknown", "public", "characters", "author_only"]
EntityKind = Literal["character", "location", "organization", "item", "other"]


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def bump_context(db, novel_id):
    book = get_or_404(db, Novel, novel_id)
    book.context_revision += 1


def mutable_book(db, novel_id):
    get_or_404(db, Novel, novel_id)
    assert_idle(db, novel_id)
    book = db.get(Novel, novel_id)
    db.refresh(book, with_for_update=True)
    return book


def lock_revision(db, row, expected):
    db.refresh(row, with_for_update=True)
    if expected != row.revision:
        raise HTTPException(409, "内容已更新，请刷新后重试")


def memory_stale(db, memory):
    if memory.stale:
        return True
    if not memory.source_chapter_id:
        return False
    chapter = db.get(Chapter, memory.source_chapter_id)
    return not chapter or chapter.novel_id != memory.novel_id or chapter.status != "confirmed" or chapter.memory_dirty or \
        memory.source_revision != chapter.revision or not memory.evidence_quote or memory.evidence_quote not in chapter.content


def memory_data(db, row):
    return {**serialize(row), "stale": memory_stale(db, row)}


def retain_memory_revision(row):
    # Fixed fields prevent recursively embedding history in every new snapshot.
    fields = ("revision", "kind", "content", "source_chapter_id", "source_revision",
              "evidence_quote", "provenance", "visibility", "known_by_entity_ids", "stale")
    row.history = [*row.history, {key: getattr(row, key) for key in fields}]


def known_entities(db, novel_id, ids):
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "知情人物不能重复")
    for identity in ids:
        entity = get_or_404(db, StoryEntity, identity)
        if entity.novel_id != novel_id:
            raise HTTPException(422, "知情实体不属于本书")


def validate_source(db, novel_id, data, allow_draft=False):
    known_entities(db, novel_id, data.get("known_by_entity_ids", []))
    source = data.get("source_chapter_id")
    if not source:
        if data.get("source_revision") is not None or data.get("evidence_quote"):
            raise HTTPException(422, "无来源记忆不能附章节版本或正文证据")
        return
    chapter = get_or_404(db, Chapter, source)
    if chapter.novel_id != novel_id or (not allow_draft and (chapter.status != "confirmed" or chapter.memory_dirty)):
        raise HTTPException(422, "来源章节须为本书有效定稿")
    if data.get("source_revision") != chapter.revision:
        raise HTTPException(409, "来源正文版本已变化")
    quote = data.get("evidence_quote", "")
    if not quote or not quote.strip() or quote not in chapter.content:
        raise HTTPException(422, "证据必须是来源章节正文中的连续原句")


class MemoryInput(BaseModel):
    kind: MemoryKind
    content: str = Field(min_length=1, max_length=12000)
    source_chapter_id: str | None = None
    source_revision: int | None = Field(default=None, ge=1)
    evidence_quote: str = Field(default="", max_length=6000)
    provenance: Literal["manual", "extracted", "legacy"] = "manual"
    visibility: Visibility = "unknown"
    known_by_entity_ids: list[str] = Field(default_factory=list, max_length=100)


class MemoryPatch(BaseModel):
    revision: int = Field(ge=1)
    kind: MemoryKind | None = None
    content: str | None = Field(default=None, min_length=1, max_length=12000)
    source_chapter_id: str | None = None
    source_revision: int | None = Field(default=None, ge=1)
    evidence_quote: str | None = Field(default=None, max_length=6000)
    provenance: Literal["manual", "extracted", "legacy"] | None = None
    visibility: Visibility | None = None
    known_by_entity_ids: list[str] | None = Field(default=None, max_length=100)


@router.get("/novels/{novel_id}/memories")
def memories(novel_id: str, db=Depends(database)):
    get_or_404(db, Novel, novel_id)
    return [memory_data(db, row) for row in db.scalars(select(Memory).where(Memory.novel_id == novel_id).order_by(Memory.created_at.desc()))]


@router.post("/novels/{novel_id}/memories")
def create_memory(novel_id: str, body: MemoryInput, db=Depends(database)):
    mutable_book(db, novel_id)
    data = body.model_dump()
    validate_source(db, novel_id, data)
    data["provenance"] = "manual"
    row = Memory(novel_id=novel_id, **data)
    db.add(row)
    bump_context(db, novel_id)
    db.commit()
    return memory_data(db, row)


@router.patch("/memories/{memory_id}")
def patch_memory(memory_id: str, body: MemoryPatch, db=Depends(database)):
    row = get_or_404(db, Memory, memory_id)
    mutable_book(db, row.novel_id)
    lock_revision(db, row, body.revision)
    updates = body.model_dump(exclude_unset=True, exclude={"revision", "provenance"})
    for key, value in updates.items():
        if value is None and key not in {"source_chapter_id", "source_revision"}:
            raise HTTPException(422, "记忆字段不能为空")
    data = {**serialize(row), **updates}
    validate_source(db, row.novel_id, data)
    retain_memory_revision(row)
    for key, value in updates.items():
        setattr(row, key, value)
    row.provenance = "manual"
    row.revision += 1
    bump_context(db, row.novel_id)
    db.commit()
    return memory_data(db, row)


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: str, db=Depends(database)):
    row = get_or_404(db, Memory, memory_id)
    mutable_book(db, row.novel_id)
    db.refresh(row, with_for_update=True)
    retain_memory_revision(row)
    row.stale = True  # References and evidence survive retirement.
    row.revision += 1
    bump_context(db, row.novel_id)
    db.commit()
    return {"deleted": True, "retired": True}


class MemoryCandidate(BaseModel):
    kind: MemoryKind
    content: str = Field(min_length=1, max_length=6000)
    evidence_quote: str = Field(min_length=1, max_length=6000)
    visibility: Visibility = "unknown"
    known_by_entity_ids: list[str] = Field(default_factory=list, max_length=100)


class ApplyMemory(BaseModel):
    expected_revision: int = Field(ge=1)
    memories: list[MemoryCandidate] = Field(min_length=1, max_length=24)


@router.post("/jobs/{job_id}/apply-memory")
def apply_memory(job_id: str, body: ApplyMemory, db=Depends(database)):
    job = get_or_404(db, Job, job_id)
    # Reject non-confirm jobs before locking the novel: outline workers lock
    # their job before updating the novel, so invalid requests cannot invert it.
    if job.kind != "confirm" or job.status != "succeeded" or job.cancel_requested:
        raise HTTPException(409, "只有成功的记忆提取任务可应用")
    book = get_or_404(db, Novel, job.novel_id)
    db.refresh(book, with_for_update=True)
    db.refresh(job, with_for_update=True)
    digest = fingerprint(body.model_dump())
    if job.result.get("applied"):
        if job.result.get("apply_fingerprint") != digest:
            raise HTTPException(409, "该候选已采用，不能以不同内容重复应用")
        return serialize(job)
    assert_idle(db, book.id)
    if job.kind != "confirm" or job.status != "succeeded" or job.cancel_requested:
        raise HTTPException(409, "只有成功的记忆提取任务可应用")
    chapter = get_or_404(db, Chapter, job.payload.get("chapter_id"))
    db.refresh(chapter, with_for_update=True)
    if chapter.novel_id != book.id or body.expected_revision != chapter.revision or body.expected_revision != job.payload.get("expected_revision"):
        raise HTTPException(409, "正文已修改，请重新提取记忆")
    if job.payload.get("context_revision") != book.context_revision or job.payload.get("content_hash") != fingerprint(chapter.content):
        raise HTTPException(409, "正文或作者设定已变化，请重新提取记忆")
    if db.scalar(select(Chapter.id).where(Chapter.novel_id == book.id, Chapter.number < chapter.number, Chapter.memory_dirty.is_(True))):
        raise HTTPException(409, "前文记忆已过期，请依次重新确认")
    if not any(item.kind == "summary" for item in body.memories):
        raise HTTPException(422, "必须包含章节摘要")
    rows = []
    for candidate in body.memories:
        data = {**candidate.model_dump(), "source_chapter_id": chapter.id, "source_revision": chapter.revision}
        validate_source(db, book.id, data, allow_draft=True)
        if not data["content"].strip():
            raise HTTPException(422, "记忆正文不能为空")
        rows.append(Memory(novel_id=book.id, provenance="extracted", **data))
    for old in db.scalars(select(Memory).where(Memory.source_chapter_id == chapter.id)):
        old.stale = True
    db.add_all(rows)
    db.flush()
    chapter.status, chapter.memory_dirty = "confirmed", False
    book.context_revision += 1
    job.result = {**job.result, "applied": True, "memory_count": len(rows), "memory_ids": [row.id for row in rows], "apply_fingerprint": digest}
    db.commit()
    return serialize(job)


class EntityInput(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    kind: EntityKind
    aliases: list[str] = Field(default_factory=list, max_length=100)
    description: str = Field(default="", max_length=12000)


class EntityPatch(BaseModel):
    revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=240)
    kind: EntityKind | None = None
    aliases: list[str] | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=12000)


@router.get("/novels/{novel_id}/entities")
def entities(novel_id: str, db=Depends(database)):
    get_or_404(db, Novel, novel_id)
    return [serialize(row) for row in db.scalars(select(StoryEntity).where(StoryEntity.novel_id == novel_id).order_by(StoryEntity.name))]


@router.post("/novels/{novel_id}/entities")
def create_entity(novel_id: str, body: EntityInput, db=Depends(database)):
    mutable_book(db, novel_id)
    row = StoryEntity(novel_id=novel_id, **body.model_dump())
    db.add(row)
    bump_context(db, novel_id)
    db.commit()
    return serialize(row)


@router.patch("/entities/{entity_id}")
def patch_entity(entity_id: str, body: EntityPatch, db=Depends(database)):
    row = get_or_404(db, StoryEntity, entity_id)
    mutable_book(db, row.novel_id)
    lock_revision(db, row, body.revision)
    for key, value in body.model_dump(exclude_none=True, exclude={"revision"}).items():
        setattr(row, key, value)
    row.revision += 1
    bump_context(db, row.novel_id)
    db.commit()
    return serialize(row)


@router.delete("/entities/{entity_id}")
def delete_entity(entity_id: str, db=Depends(database)):
    row = get_or_404(db, StoryEntity, entity_id)
    mutable_book(db, row.novel_id)
    if db.scalar(select(StoryRelation.id).where(or_(StoryRelation.source_entity_id == entity_id, StoryRelation.target_entity_id == entity_id))):
        raise HTTPException(409, "实体仍被关系引用，请先移除关系")
    if any(entity_id in item.known_by_entity_ids for item in db.scalars(select(Memory).where(Memory.novel_id == row.novel_id))):
        raise HTTPException(409, "实体仍被记忆知情列表引用")
    bump_context(db, row.novel_id)
    db.delete(row)
    db.commit()
    return {"deleted": True}


def basis_memory(db, novel_id, basis, memory_id):
    if basis == "author":
        if memory_id:
            raise HTTPException(422, "作者设定不应冒用正文来源")
        return None
    if not memory_id:
        raise HTTPException(422, "正文事实必须关联有效章节记忆")
    memory = get_or_404(db, Memory, memory_id)
    if memory.novel_id != novel_id or not memory.source_chapter_id or memory_stale(db, memory):
        raise HTTPException(422, "来源记忆须为本书有效正文事实")
    return memory


def reference_stale(db, basis, memory_id, revision):
    if basis == "author":
        return False
    memory = db.get(Memory, memory_id) if memory_id else None
    return not memory or memory.revision != revision or memory_stale(db, memory)


class RelationInput(BaseModel):
    source_entity_id: str
    target_entity_id: str
    label: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=12000)
    basis: Literal["author", "chapter"] = "author"
    memory_id: str | None = None


class RelationPatch(BaseModel):
    revision: int = Field(ge=1)
    revalidate_source: bool = False
    source_entity_id: str | None = None
    target_entity_id: str | None = None
    label: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=12000)
    basis: Literal["author", "chapter"] | None = None
    memory_id: str | None = None


def relation_data(db, row):
    return {**serialize(row), "stale": reference_stale(db, row.basis, row.memory_id, row.memory_revision)}


def validate_relation(db, novel_id, data):
    validate_endpoints(db, novel_id, data)
    memory = basis_memory(db, novel_id, data["basis"], data.get("memory_id"))
    return memory.revision if memory else None


def validate_endpoints(db, novel_id, data):
    for key in ("source_entity_id", "target_entity_id"):
        entity = get_or_404(db, StoryEntity, data[key])
        if entity.novel_id != novel_id:
            raise HTTPException(422, "关系端点不属于本书")


@router.get("/novels/{novel_id}/relations")
def relations(novel_id: str, db=Depends(database)):
    get_or_404(db, Novel, novel_id)
    return [relation_data(db, row) for row in db.scalars(select(StoryRelation).where(StoryRelation.novel_id == novel_id))]


@router.post("/novels/{novel_id}/relations")
def create_relation(novel_id: str, body: RelationInput, db=Depends(database)):
    mutable_book(db, novel_id)
    data = body.model_dump()
    row = StoryRelation(novel_id=novel_id, memory_revision=validate_relation(db, novel_id, data), **data)
    db.add(row)
    bump_context(db, novel_id)
    db.commit()
    return relation_data(db, row)


@router.patch("/relations/{relation_id}")
def patch_relation(relation_id: str, body: RelationPatch, db=Depends(database)):
    row = get_or_404(db, StoryRelation, relation_id)
    mutable_book(db, row.novel_id)
    lock_revision(db, row, body.revision)
    updates = body.model_dump(exclude_unset=True, exclude={"revision", "revalidate_source"})
    data = {**serialize(row), **updates}
    validate_endpoints(db, row.novel_id, data)
    # Editing a label/description must never silently revalidate old evidence.
    # Repeating the same source in a form submission is not an acknowledgement.
    source_changed = data.get("memory_id") != row.memory_id or data["basis"] != row.basis
    if source_changed or body.revalidate_source:
        row.memory_revision = validate_relation(db, row.novel_id, data)
    for key, value in updates.items():
        if value is None and key != "memory_id":
            raise HTTPException(422, "关系字段不能为空")
        setattr(row, key, value)
    row.revision += 1
    bump_context(db, row.novel_id)
    db.commit()
    return relation_data(db, row)


@router.delete("/relations/{relation_id}")
def delete_relation(relation_id: str, db=Depends(database)):
    row = get_or_404(db, StoryRelation, relation_id)
    mutable_book(db, row.novel_id)
    bump_context(db, row.novel_id)
    db.delete(row)
    db.commit()
    return {"deleted": True}


class ForeshadowEvent(BaseModel):
    id: str | None = None
    state: Literal["planted", "progressing", "resolved", "abandoned"]
    note: str = Field(default="", max_length=6000)
    memory_id: str | None = None
    basis: Literal["author", "chapter"] = "author"
    memory_revision: int | None = None


class ForeshadowInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=12000)
    target_chapter: int | None = Field(default=None, ge=1, le=100000)
    events: list[ForeshadowEvent] = Field(default_factory=list, max_length=500)


class ForeshadowPatch(BaseModel):
    revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=12000)
    target_chapter: int | None = Field(default=None, ge=1, le=100000)
    events: list[ForeshadowEvent] | None = Field(default=None, max_length=500)


def prepare_events(db, novel_id, incoming, old=None):
    old = old or []
    data = [event.model_dump() for event in incoming]
    if len(data) < len(old) or data[:len(old)] != old:
        raise HTTPException(409, "已有伏笔事件不可修改或移除；请追加新事件")
    seen = {event["id"] for event in old}
    for event in data[len(old):]:
        event["id"] = event["id"] or uid()
        if event["id"] in seen:
            raise HTTPException(422, "伏笔事件ID重复")
        seen.add(event["id"])
        memory = basis_memory(db, novel_id, event["basis"], event["memory_id"])
        event["memory_revision"] = memory.revision if memory else None
    return data


def foreshadow_data(db, row):
    events, valid = [], []
    for event in row.events:
        stale = reference_stale(db, event["basis"], event.get("memory_id"), event.get("memory_revision"))
        events.append({**event, "stale": stale})
        if not stale:
            valid.append(event)
    return {**serialize(row), "events": events, "status": valid[-1]["state"] if valid else "planned", "needs_review": any(event["stale"] for event in events)}


@router.get("/novels/{novel_id}/foreshadows")
def foreshadows(novel_id: str, db=Depends(database)):
    get_or_404(db, Novel, novel_id)
    return [foreshadow_data(db, row) for row in db.scalars(select(Foreshadow).where(Foreshadow.novel_id == novel_id))]


@router.post("/novels/{novel_id}/foreshadows")
def create_foreshadow(novel_id: str, body: ForeshadowInput, db=Depends(database)):
    mutable_book(db, novel_id)
    data = body.model_dump(exclude={"events"})
    row = Foreshadow(novel_id=novel_id, events=prepare_events(db, novel_id, body.events), **data)
    db.add(row)
    bump_context(db, novel_id)
    db.commit()
    return foreshadow_data(db, row)


@router.patch("/foreshadows/{foreshadow_id}")
def patch_foreshadow(foreshadow_id: str, body: ForeshadowPatch, db=Depends(database)):
    row = get_or_404(db, Foreshadow, foreshadow_id)
    mutable_book(db, row.novel_id)
    lock_revision(db, row, body.revision)
    if body.events is not None:
        row.events = prepare_events(db, row.novel_id, body.events, row.events)
    for key, value in body.model_dump(exclude_unset=True, exclude={"revision", "events"}).items():
        if value is None and key != "target_chapter":
            raise HTTPException(422, "伏笔字段不能为空")
        setattr(row, key, value)
    row.revision += 1
    bump_context(db, row.novel_id)
    db.commit()
    return foreshadow_data(db, row)


@router.delete("/foreshadows/{foreshadow_id}")
def delete_foreshadow(foreshadow_id: str, db=Depends(database)):
    row = get_or_404(db, Foreshadow, foreshadow_id)
    mutable_book(db, row.novel_id)
    bump_context(db, row.novel_id)
    db.delete(row)
    db.commit()
    return {"deleted": True}


@router.get("/novels/{novel_id}/graph")
def graph(novel_id: str, before_chapter: int | None = Query(default=None, ge=1), include_stale: bool = False, db=Depends(database)):
    get_or_404(db, Novel, novel_id)
    edges = []
    for row in db.scalars(select(StoryRelation).where(StoryRelation.novel_id == novel_id)):
        edge = relation_data(db, row)
        if edge["stale"] and not include_stale:
            continue
        if row.basis == "chapter" and before_chapter is not None:
            memory = db.get(Memory, row.memory_id)
            chapter = db.get(Chapter, memory.source_chapter_id) if memory and memory.source_chapter_id else None
            if not chapter or chapter.number >= before_chapter:
                continue
        edges.append(edge)
    return {"nodes": entities(novel_id, db), "edges": edges, "cutoff": before_chapter}
