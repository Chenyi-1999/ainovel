"""One low-memory worker; durable leases fence even accidental duplicate workers.

Each chapter commit and its progress increment share one transaction. A retry
resumes the remaining count. Cancellation discards uncommitted model output.
"""
import json
import os
import time
from datetime import timedelta

import redis
from sqlalchemy import delete, func, select

from . import gateway
from .db import Chapter, Job, Memory, Novel, Session, initialize, now, uid
from .services import KINDS, retrieve_memory

SYSTEM = "你是一名严谨的中文小说作者。遵循用户的题材、设定和风格，保持因果与人物一致。记忆中人物状态随剧情变化，较新来源章节的事实优先；无来源记忆是作者手动设定。只输出所要求的内容，不添加聊天说明。"
JSON_SYSTEM = SYSTEM + " 当要求 JSON 时，仅输出合法 JSON 对象，不要 Markdown 代码围栏。"


class Superseded(Exception):
    pass


class Cancelled(Exception):
    pass


def checkpoint(job):
    with Session() as db:
        live = db.get(Job, job.id)
        if not live or live.owner_token != job.owner_token or live.status != "running":
            raise Superseded()
        if live.cancel_requested:
            raise Cancelled()


def claim_job():
    with Session() as db:
        # A crashed worker is recovered after its lease. A new token fences old callers.
        expired = db.scalars(select(Job).where(Job.status == "running", Job.lease_until < now())
                             .with_for_update(skip_locked=True)).all()
        for row in expired:
            row.status = "cancelled" if row.cancel_requested else "pending"
        db.flush()
        job = db.scalar(select(Job).where(Job.status == "pending").order_by(Job.created_at)
                        .with_for_update(skip_locked=True).limit(1))
        if not job:
            db.commit()
            return None
        job.status = "running"
        job.owner_token = uid()
        job.lease_until = now() + timedelta(minutes=10)
        db.commit()
        return job.id, job.owner_token


def lock_job(db, job_id, token):
    row = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if not row or row.owner_token != token or row.status != "running":
        raise Superseded()
    return row


def context(db, novel, instructions, before_number=None):
    stmt = select(Chapter).where(Chapter.novel_id == novel.id)
    if before_number is not None:
        stmt = stmt.where(Chapter.number < before_number)
    recent = db.scalars(stmt.order_by(Chapter.number.desc()).limit(3)).all()
    packet = {"title": novel.title, "premise": novel.premise[:4000], "genre": novel.genre, "style": novel.style[:1500],
            "outline_excerpt": dump(novel.outline)[:6500],
            "canonical_memory": retrieve_memory(db, novel.id, instructions + " " + novel.premise, 8, before_number),
            "recent_chapters": [{"number": row.number, "title": row.title, "status": row.status,
                                 "memory_dirty": row.memory_dirty, "ending": row.content[-800:]} for row in reversed(recent)],
            "instructions": instructions}
    for memory in packet["canonical_memory"]:
        memory["content"] = memory["content"][:800]
    # Stable character budget, independent of total novel length. User instructions
    # and premise have priority; least relevant recalled facts are removed first.
    while len(dump(packet)) > 24000 and packet["canonical_memory"]:
        packet["canonical_memory"].pop()
    while len(dump(packet)) > 24000 and packet["recent_chapters"]:
        packet["recent_chapters"].pop(0)
    if len(dump(packet)) > 24000:
        packet["outline_excerpt"] = packet["outline_excerpt"][:max(0, 24000 - len(dump(packet)) + len(packet["outline_excerpt"]) - 100)]
    if len(dump(packet)) > 24000:
        raise ValueError("写作要求或设定的编码内容过长，请缩短后重试")
    return packet


def dump(value):
    return json.dumps(value, ensure_ascii=False)


def write_chapter(job, ctx, number):
    prompt = (f"根据以下小说资料写第 {number} 章，目标约 {job.payload.get('target_words', 2000)} 个中文字。"
              "先自行规划本章冲突、行动、转折和结尾钩子，再给出完整正文。草稿仅作衔接参考；有效记忆为正式设定。"
              "标题不要包含章号，正文不要包含标题、提纲、审稿说明。返回 JSON {\"title\":\"章节标题\",\"content\":\"完整正文\"}。\n" + dump(ctx))
    output = gateway.parse_json(gateway.complete(job.novel_id, job.id, "write", prompt, JSON_SYSTEM,
                                                 max_tokens=min(18000, job.payload.get("target_words", 2000) * 3 + 5000)))
    title, content = output.get("title"), output.get("content")
    if not isinstance(title, str) or not isinstance(content, str) or len(content.strip()) < 100:
        raise ValueError("模型返回的章节正文不完整，请重试")
    checkpoint(job)
    # One bounded review-and-repair call; no recursive model loop.
    review = gateway.parse_json(gateway.complete(job.novel_id, job.id, "audit",
        "审查下列章节是否存在严重的设定冲突、人物行为矛盾、与前文重复。必要时直接修订，最多修订一次。"
        "若无需修订 content 返回空字符串。若修订则返回完整正文，不能只返回片段。"
        "JSON {\"report\":\"简短审稿结论\",\"content\":\"完整修订正文或空字符串\"}。\n" +
        dump({"context": ctx, "title": title, "content": content}), JSON_SYSTEM,
        max_tokens=min(18000, job.payload.get("target_words", 2000) * 3 + 5000)))
    revision = review.get("content", "")
    if revision:
        if not isinstance(revision, str) or len(revision.strip()) < 100:
            raise ValueError("审稿修订结果不完整，未保存；请重试")
        content = revision
    return title[:240].strip(), content.strip(), str(review.get("report", ""))[:8000]


def produce(job, novel, ctx, chapter, number):
    if job.kind == "outline":
        result = gateway.parse_json(gateway.complete(job.novel_id, job.id, "outline",
            "根据几句话创作可用于连载的大纲。返回 JSON：title（书名）、synopsis（故事简介）、world（世界观），"
            "characters（人物数组，每项 name/role/motivation/arc），main_conflict（主线冲突），"
            "volumes（分卷数组，每项 title/summary/arc），chapter_outline（前十章数组，每项 number/title/summary）。"
            "不要一次列出全书全部章节，保留后续发展空间。\n" + dump({**ctx, "planned_chapters": novel.planned_chapters}),
            JSON_SYSTEM, max_tokens=14000))
        if not isinstance(result.get("synopsis"), str) or not result["synopsis"].strip():
            raise ValueError("大纲缺少故事简介，请重试")
        return result
    if job.kind == "write":
        title, content, report = write_chapter(job, ctx, number)
        return {"title": title, "content": content, "report": report}
    if job.kind == "confirm":
        result = gateway.parse_json(gateway.complete(job.novel_id, job.id, "confirm",
            "从章节定稿提取明确发生的事实，不推测后续发展。返回 JSON {\"memories\":[{\"kind\":\"summary|character|setting|timeline|foreshadow\",\"content\":\"事实\"}]}。"
            "必须包含 summary 类型的章节摘要。人物状态、时间线、设定和伏笔按有依据的事实提取，总计最多 24 条，每条最多 1800 字。\n" +
            dump({"chapter_number": chapter.number, "title": chapter.title, "content": chapter.content}),
            JSON_SYSTEM, max_tokens=12000))
        memories = result.get("memories")
        if not isinstance(memories, list) or not 1 <= len(memories) <= 24:
            raise ValueError("记忆提取结果不完整，未确认定稿；请重试")
        if any(not isinstance(item, dict) or item.get("kind") not in KINDS or
               not isinstance(item.get("content"), str) or not item["content"].strip() or len(item["content"]) > 6000
               for item in memories) or not any(item["kind"] == "summary" for item in memories):
            raise ValueError("记忆格式或摘要不完整，未确认定稿；请重试")
        return result
    if job.kind == "audit":
        report = gateway.complete(job.novel_id, job.id, "audit",
            "审查本章的设定一致性、人物行动合理性、重复内容、情节推进和语言。指出具体问题并给修改建议，无需重写正文。\n" +
            dump({"context": ctx, "title": chapter.title, "content": chapter.content}), SYSTEM, max_tokens=8000)
        return {"report": report}
    if job.kind == "rewrite":
        selection = job.payload.get("selection")
        content = gateway.complete(job.novel_id, job.id, "rewrite",
            ("仅重写给定选段，返回替换选段正文，不返回全章。" if selection else "重写本章，返回完整正文，不含标题。") +
            "保持前后衔接和有效设定，不添加解释。\n" + dump({"context": ctx, "title": chapter.title,
            "content": chapter.content, "selection": selection}), SYSTEM, max_tokens=18000)
        if selection:
            content = chapter.content.replace(selection, content, 1)
        return {"title": chapter.title, "content": content, "expected_revision": chapter.revision}
    raise ValueError("任务类型不支持")


def run_job(job_id, token):
    try:
        while True:
            with Session() as db:
                job = lock_job(db, job_id, token)
                if job.cancel_requested:
                    job.status = "cancelled"
                    db.commit()
                    return
                if job.current >= job.count:
                    job.status = "succeeded"
                    db.commit()
                    return
                job.lease_until = now() + timedelta(minutes=10)
                novel = db.get(Novel, job.novel_id)
                chapter = db.get(Chapter, job.payload.get("chapter_id")) if job.payload.get("chapter_id") else None
                ctx = context(db, novel, job.payload.get("instructions", ""), chapter.number if chapter else None)
                if chapter and chapter.revision != job.payload["expected_revision"]:
                    raise ValueError("章节已修改，请重新创建任务")
                if job.kind == "confirm" and db.scalar(select(Chapter.id).where(
                        Chapter.novel_id == job.novel_id, Chapter.number < chapter.number,
                        Chapter.memory_dirty.is_(True))):
                    raise ValueError("前面的章节记忆已过期，请先依次重新确认定稿")
                number = (db.scalar(select(func.max(Chapter.number)).where(Chapter.novel_id == job.novel_id)) or 0) + 1
                db.commit()
            result = produce(job, novel, ctx, chapter, number)
            with Session() as db:
                live = lock_job(db, job_id, token)
                if live.cancel_requested:
                    live.status = "cancelled"
                    db.commit()
                    return
                if live.kind == "outline":
                    book = db.get(Novel, live.novel_id)
                    book.outline = result
                    if book.title == "未命名小说" and isinstance(result.get("title"), str):
                        book.title = result["title"][:240]
                    live.result = result
                elif live.kind == "write":
                    chapter = Chapter(novel_id=live.novel_id, number=number, title=result["title"], content=result["content"])
                    db.add(chapter)
                    db.flush()
                    ids = list(live.result.get("chapter_ids", [])) + [chapter.id]
                    live.result = {"chapter_ids": ids, "report": result["report"]}
                elif live.kind == "confirm":
                    chapter = db.get(Chapter, live.payload["chapter_id"])
                    if chapter.revision != live.payload["expected_revision"]:
                        raise ValueError("章节已修改，未保存旧版本记忆")
                    db.execute(delete(Memory).where(Memory.source_chapter_id == chapter.id))
                    for item in result["memories"]:
                        db.add(Memory(novel_id=live.novel_id, source_chapter_id=chapter.id,
                                      kind=item["kind"], content=item["content"].strip()))
                    chapter.status, chapter.memory_dirty = "confirmed", False
                    live.result = {"chapter_id": chapter.id, "memory_count": len(result["memories"])}
                else:
                    live.result = result  # Rewrites remain proposals until an explicit edit.
                live.current += 1
                live.status = "succeeded" if live.current >= live.count else "running"
                live.lease_until = now() + timedelta(minutes=10)
                db.commit()
                if live.status == "succeeded":
                    return
    except Superseded:
        return
    except Exception as exc:
        with Session() as db:
            try:
                live = lock_job(db, job_id, token)
            except Superseded:
                return
            live.status = "cancelled" if live.cancel_requested or isinstance(exc, Cancelled) else "failed"
            # Only our controlled ValueError messages reach the browser.
            live.error = str(exc)[:500] if isinstance(exc, ValueError) else "任务处理失败，已保留已保存内容；请重试"
            db.commit()


def main():
    initialize()
    client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"),
                                  socket_connect_timeout=2, socket_timeout=4)
    while True:
        try:
            claimed = claim_job()
            if claimed:
                run_job(*claimed)
            else:
                try:
                    client.brpop("ainovel:wakeup", timeout=2)
                except redis.RedisError:
                    time.sleep(2)
        except Exception:
            # No response bodies or credentials appear in worker logs.
            print("Worker temporarily unavailable; retrying database connection.", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
