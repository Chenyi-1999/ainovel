import os
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from . import gateway
from .auth import COOKIE, check_origin, issue_session, require_auth, verify_password
from .db import Chapter, Job, Memory, Novel, Session, Setting, Usage, Version, PromptTemplate, PromptRevision, StoryEntity, StoryRelation, Foreshadow, initialize, serialize
from .dependencies import database
from .prompts import router as prompt_router, selected_snapshot
from .story import router as story_router, bump_context, fingerprint
from .skills import SKILLS
from .services import KINDS, assert_idle, get_or_404, save_edit, wake_worker


@asynccontextmanager
async def lifespan(app):
    initialize()
    yield


app = FastAPI(title="小说生产工作台", lifespan=lifespan, docs_url=None, redoc_url=None)
app.include_router(prompt_router)
app.include_router(story_router)


@app.middleware("http")
async def security_headers(request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        try:
            check_origin(request)
        except HTTPException as exc:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


class Login(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


login_attempts = {}


@app.get("/api/health")
def health(db=Depends(database)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/api/login")
def login(body: Login, request: Request, response: Response):
    identity = request.client.host if request.client else "unknown"
    attempts = [stamp for stamp in login_attempts.get(identity, []) if stamp > time.time() - 600]
    if len(attempts) >= 8:
        raise HTTPException(429, "登录尝试过于频繁，请 10 分钟后重试")
    if not verify_password(body.password):
        if len(login_attempts) > 10_000:
            login_attempts.clear()
        login_attempts[identity] = attempts + [time.time()]
        raise HTTPException(401, "密码不正确")
    login_attempts.pop(identity, None)
    response.set_cookie(COOKIE, issue_session(), httponly=True, samesite="strict", max_age=86400,
                        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true", path="/")
    return {"authenticated": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"authenticated": False}


@app.get("/api/me", dependencies=[Depends(require_auth)])
def me():
    return {"authenticated": True}


class NovelInput(BaseModel):
    title: str = Field(default="未命名小说", max_length=240)
    premise: str = Field(min_length=1, max_length=12000)
    genre: str = Field(default="", max_length=100)
    style: str = Field(default="", max_length=5000)
    planned_chapters: int = Field(default=100, ge=1, le=100000)


class NovelPatch(BaseModel):
    title: str | None = Field(default=None, max_length=240)
    premise: str | None = Field(default=None, min_length=1, max_length=12000)
    genre: str | None = Field(default=None, max_length=100)
    style: str | None = Field(default=None, max_length=5000)
    planned_chapters: int | None = Field(default=None, ge=1, le=100000)
    outline: dict | None = None


auth = [Depends(require_auth)]


@app.get("/api/novels", dependencies=auth)
def novels(db=Depends(database)):
    return [serialize(row) for row in db.scalars(select(Novel).order_by(Novel.updated_at.desc()))]


@app.post("/api/novels", dependencies=auth)
def create_novel(body: NovelInput, db=Depends(database)):
    row = Novel(**body.model_dump())
    db.add(row)
    db.commit()
    return serialize(row)


@app.get("/api/novels/{novel_id}", dependencies=auth)
def novel(novel_id: str, db=Depends(database)):
    return serialize(get_or_404(db, Novel, novel_id))


@app.patch("/api/novels/{novel_id}", dependencies=auth)
def patch_novel(novel_id: str, body: NovelPatch, db=Depends(database)):
    row = get_or_404(db, Novel, novel_id)
    assert_idle(db, novel_id)
    db.refresh(row, with_for_update=True)
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    bump_context(db, novel_id)
    db.commit()
    return serialize(row)


@app.delete("/api/novels/{novel_id}", dependencies=auth)
def delete_novel(novel_id: str, db=Depends(database)):
    row = get_or_404(db, Novel, novel_id)
    assert_idle(db, novel_id)
    # Explicit child deletion works identically under PostgreSQL and SQLite tests.
    ids = select(Chapter.id).where(Chapter.novel_id == novel_id)
    db.execute(delete(Version).where(Version.chapter_id.in_(ids)))
    prompt_ids = select(PromptTemplate.id).where(PromptTemplate.novel_id == novel_id)
    db.execute(delete(PromptRevision).where(PromptRevision.prompt_id.in_(prompt_ids)))
    for model in (StoryRelation, Foreshadow, StoryEntity, PromptTemplate, Memory, Usage, Job, Chapter):
        db.execute(delete(model).where(model.novel_id == novel_id))
    db.delete(row)
    db.commit()
    return {"deleted": True}


@app.get("/api/novels/{novel_id}/chapters", dependencies=auth)
def chapters(novel_id: str, db=Depends(database)):
    get_or_404(db, Novel, novel_id)
    return [serialize(row) for row in db.scalars(select(Chapter).where(Chapter.novel_id == novel_id).order_by(Chapter.number))]


class ChapterInput(BaseModel):
    title: str = Field(default="未命名章节", max_length=240)
    content: str = Field(default="", max_length=200000)


@app.post("/api/novels/{novel_id}/chapters", dependencies=auth)
def create_chapter(novel_id: str, body: ChapterInput, db=Depends(database)):
    get_or_404(db, Novel, novel_id)
    assert_idle(db, novel_id)
    number = (db.scalar(select(func.max(Chapter.number)).where(Chapter.novel_id == novel_id)) or 0) + 1
    row = Chapter(novel_id=novel_id, number=number, title=body.title, content=body.content)
    db.add(row)
    bump_context(db, novel_id)
    db.commit()
    return serialize(row)


class ChapterPatch(BaseModel):
    title: str | None = Field(default=None, max_length=240)
    content: str | None = Field(default=None, max_length=200000)
    revision: int | None = None


@app.patch("/api/chapters/{chapter_id}", dependencies=auth)
def patch_chapter(chapter_id: str, body: ChapterPatch, db=Depends(database)):
    row = get_or_404(db, Chapter, chapter_id)
    assert_idle(db, row.novel_id)
    # The row may have entered this session before waiting on the novel lock.
    # Reload under lock so competing PATCH requests compare the committed revision.
    db.refresh(row, with_for_update=True)
    if body.revision is not None and body.revision != row.revision:
        raise HTTPException(409, "章节已被更新，请刷新后编辑")
    save_edit(db, row, body.title if body.title is not None else row.title,
              body.content if body.content is not None else row.content)
    bump_context(db, row.novel_id)
    db.commit()
    return serialize(row)


@app.get("/api/chapters/{chapter_id}/versions", dependencies=auth)
def versions(chapter_id: str, db=Depends(database)):
    get_or_404(db, Chapter, chapter_id)
    return [serialize(row) for row in db.scalars(select(Version).where(Version.chapter_id == chapter_id).order_by(Version.revision.desc()))]


class JobInput(BaseModel):
    kind: Literal["outline", "write", "rewrite", "audit", "confirm"]
    count: int = Field(default=1, ge=1, le=20)
    instructions: str = Field(default="", max_length=6000)
    target_words: int = Field(default=2000, ge=300, le=6000)
    chapter_id: str | None = None
    selection: str | None = Field(default=None, max_length=20000)
    skill_id: str | None = None
    prompt_template_id: str | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)


@app.get("/api/skills", dependencies=auth)
def skills():
    return SKILLS


@app.post("/api/novels/{novel_id}/jobs", dependencies=auth)
def create_job(novel_id: str, body: JobInput, db=Depends(database)):
    book = get_or_404(db, Novel, novel_id)
    db.refresh(book, with_for_update=True)
    request_fingerprint = fingerprint(body.model_dump(exclude={"idempotency_key"}))
    if body.idempotency_key:
        existing = db.scalar(select(Job).where(Job.novel_id == novel_id, Job.idempotency_key == body.idempotency_key))
        if existing:
            if existing.request_fingerprint != request_fingerprint:
                raise HTTPException(409, "幂等键已用于不同任务参数")
            return serialize(existing)
    if body.skill_id is not None and body.skill_id != body.kind:
        raise HTTPException(422, "Skill与任务类型不匹配")
    assert_idle(db, novel_id)
    payload = body.model_dump()
    template = selected_snapshot(db, body.prompt_template_id, book, body.kind, body.instructions)
    if template:
        payload["prompt_snapshot"] = template
    if body.kind in ("confirm", "rewrite", "audit"):
        if not body.chapter_id:
            raise HTTPException(422, "请选择章节")
        chapter = get_or_404(db, Chapter, body.chapter_id)
        if chapter.novel_id != novel_id:
            raise HTTPException(422, "章节不属于本书")
        if not chapter.content.strip():
            raise HTTPException(422, "章节正文不能为空")
        if body.selection and body.selection not in chapter.content:
            raise HTTPException(422, "选段已发生变化，请重新选择")
        payload["expected_revision"] = chapter.revision
        if body.kind == "confirm":
            payload["content_hash"] = fingerprint(chapter.content)
            payload["context_revision"] = book.context_revision
    row = Job(novel_id=novel_id, kind=body.kind, count=body.count if body.kind == "write" else 1, payload=payload,
              idempotency_key=body.idempotency_key, request_fingerprint=request_fingerprint)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if body.idempotency_key:
            existing = db.scalar(select(Job).where(Job.novel_id == novel_id, Job.idempotency_key == body.idempotency_key))
            if existing and existing.request_fingerprint == request_fingerprint:
                return serialize(existing)
        raise HTTPException(409, "本书已有任务正在执行")
    wake_worker()
    return serialize(row)


@app.get("/api/novels/{novel_id}/jobs", dependencies=auth)
def jobs(novel_id: str, db=Depends(database)):
    get_or_404(db, Novel, novel_id)
    return [serialize(row) for row in db.scalars(select(Job).where(Job.novel_id == novel_id).order_by(Job.created_at.desc()).limit(100))]


@app.get("/api/jobs/{job_id}", dependencies=auth)
def job(job_id: str, db=Depends(database)):
    return serialize(get_or_404(db, Job, job_id))


@app.post("/api/jobs/{job_id}/cancel", dependencies=auth)
def cancel_job(job_id: str, db=Depends(database)):
    row = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if not row:
        raise HTTPException(404, "任务不存在")
    if row.status in ("pending", "running"):
        row.cancel_requested = True
        if row.status == "pending":
            row.status = "cancelled"
    db.commit()
    return serialize(row)


@app.post("/api/jobs/{job_id}/retry", dependencies=auth)
def retry_job(job_id: str, db=Depends(database)):
    row = get_or_404(db, Job, job_id)
    if row.status not in ("failed", "cancelled"):
        raise HTTPException(409, "只有失败或停止的任务可以重试")
    assert_idle(db, row.novel_id)
    db.refresh(row, with_for_update=True)
    if row.status not in ("failed", "cancelled"):
        raise HTTPException(409, "任务状态已变化，请刷新后重试")
    if row.payload.get("chapter_id"):
        chapter = get_or_404(db, Chapter, row.payload["chapter_id"])
        if chapter.revision != row.payload.get("expected_revision"):
            raise HTTPException(409, "章节已修改，请针对新正文创建任务")
    row.status, row.error, row.cancel_requested = "pending", "", False
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "本书已有任务正在执行")
    wake_worker()
    return serialize(row)


class SettingsPatch(BaseModel):
    base_url: str | None = Field(default=None, max_length=500)
    outline_model: str | None = Field(default=None, min_length=1, max_length=160)
    writing_model: str | None = Field(default=None, min_length=1, max_length=160)
    review_model: str | None = Field(default=None, min_length=1, max_length=160)
    memory_model: str | None = Field(default=None, min_length=1, max_length=160)
    temperature: float | None = Field(default=None, ge=0, le=2)
    input_price_per_million: float | None = Field(default=None, ge=0, le=10000)
    output_price_per_million: float | None = Field(default=None, ge=0, le=10000)


@app.get("/api/settings", dependencies=auth)
def settings():
    return {**gateway.settings(), "has_api_key": bool(os.getenv("LLM_API_KEY"))}


@app.patch("/api/settings", dependencies=auth)
def patch_settings(body: SettingsPatch, db=Depends(database)):
    value = body.model_dump(exclude_none=True)
    if "base_url" in value:
        try:
            value["base_url"] = gateway.validate_base_url(value["base_url"])
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    row = db.get(Setting, 1)
    if not row:
        row = Setting(id=1, value={})
        db.add(row)
    row.value = {**row.value, **value}
    db.commit()
    return settings()


@app.get("/api/models", dependencies=auth)
def models():
    try:
        return {"models": gateway.discover_models(),
                "source": "configured" if gateway.transport() == "claude_cli" else
                          ("catalog" if gateway.settings()["base_url"].startswith("https://ark.cn-beijing.volces.com/") else "provider")}
    except ValueError as exc:
        raise HTTPException(502, str(exc))


@app.get("/api/novels/{novel_id}/usage", dependencies=auth)
def usage(novel_id: str, db=Depends(database)):
    get_or_404(db, Novel, novel_id)
    rows = db.scalars(select(Usage).where(Usage.novel_id == novel_id).order_by(Usage.created_at.desc())).all()
    return {"input_tokens": sum(row.input_tokens for row in rows), "output_tokens": sum(row.output_tokens for row in rows),
            "estimated_cost": sum(row.estimated_cost for row in rows), "requests": len(rows),
            "records": [serialize(row) for row in rows[:100]]}


@app.get("/api/novels/{novel_id}/export", dependencies=auth)
def export(novel_id: str, format: Literal["txt", "md"] = "txt",
           from_chapter: int | None = Query(default=None, ge=1),
           to_chapter: int | None = Query(default=None, ge=1), db=Depends(database)):
    row = get_or_404(db, Novel, novel_id)
    if from_chapter is not None and to_chapter is not None and from_chapter > to_chapter:
        raise HTTPException(422, "起始章节不能大于结束章节")
    stmt = select(Chapter).where(Chapter.novel_id == novel_id)
    if from_chapter is not None:
        stmt = stmt.where(Chapter.number >= from_chapter)
    if to_chapter is not None:
        stmt = stmt.where(Chapter.number <= to_chapter)
    chapters = db.scalars(stmt.order_by(Chapter.number)).all()
    chunks = [row.title]
    for chapter in chapters:
        chunks.append(("## " if format == "md" else "") + f"第{chapter.number}章 {chapter.title}\n\n{chapter.content}")
    return PlainTextResponse("\n\n".join(chunks) + "\n", headers={
        "Content-Disposition": f'attachment; filename="novel-{novel_id}.{format}"'})
