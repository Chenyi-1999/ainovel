"""Regression cases for provenance, optimistic edits and declarative job inputs."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, inspect, select, text

from app import gateway, worker
from app.db import Chapter, Job, Memory, Novel, PromptRevision, Session, StoryRelation
from app.migrations import check_schema, migrate
from app.services import retrieve_memory
from app.story import MemoryCandidate
from test_workflow import CONTENT, apply_candidates, model_success, run, submit


def create_chapter(client, novel, content=CONTENT):
    response = client.post(f"/api/novels/{novel['id']}/chapters", json={"title": "山门", "content": content})
    assert response.status_code == 200, response.text
    return response.json()


def extract(client, novel, chapter, monkeypatch):
    monkeypatch.setattr(gateway, "complete", model_success)
    task = submit(client, novel, "confirm", chapter_id=chapter["id"])
    run()
    return client.get(f"/api/jobs/{task['id']}").json()


def apply_body(task):
    return {"expected_revision": task["result"]["expected_revision"], "memories": task["result"]["memory_candidates"]}


def entity(client, novel, name):
    response = client.post(f"/api/novels/{novel['id']}/entities", json={"name": name, "kind": "character"})
    assert response.status_code == 200, response.text
    return response.json()


def test_prompt_safe_preview_revisions_import_and_builtin(client, novel):
    prompts = client.get("/api/prompts").json()
    assert len(prompts) >= 7 and {item["task_kind"] for item in prompts} == {"outline", "write", "rewrite", "audit", "confirm"}
    builtin = prompts[0]
    assert client.patch(f"/api/prompts/{builtin['id']}", json={"revision": 1, "body": "变更"}).status_code == 409
    assert client.delete(f"/api/prompts/{builtin['id']}").status_code == 409
    bad = client.post("/api/prompts", json={"name": "危险", "task_kind": "write", "body": "{{__import__('os')}}"})
    assert bad.status_code == 422
    created = client.post("/api/prompts", json={"name": "私人文风", "task_kind": "write", "body": "{{title}} · {{instructions}}", "novel_id": novel["id"]}).json()
    preview = client.post(f"/api/prompts/{created['id']}/preview", json={"novel_id": novel["id"], "instructions": "慢镜头"}).json()
    assert preview["rendered"] == "药师 · 慢镜头" and preview["variables"]["title"] == "药师"
    changed = client.patch(f"/api/prompts/{created['id']}", json={"revision": 1, "body": "new {{style}}"})
    assert changed.status_code == 200 and changed.json()["revision"] == 2
    assert client.patch(f"/api/prompts/{created['id']}", json={"revision": 1, "body": "lost"}).status_code == 409
    versions = client.get(f"/api/prompts/{created['id']}/versions").json()
    assert [row["revision"] for row in versions] == [2, 1]
    assert versions[-1]["snapshot"]["body"] == created["body"]
    exported = client.get("/api/prompts/export").json()
    report = client.post("/api/prompts/import", json=exported).json()
    assert report["dry_run"] and report["conflicts"]
    assert client.post("/api/prompts/import?dry_run=false", json=exported).status_code == 409
    fresh = {"schema_version": 1, "prompts": [{"name": "导入原创", "task_kind": "audit", "body": "检查 {{title}}"}]}
    assert client.post("/api/prompts/import", json=fresh).json()["valid_count"] == 1
    assert client.post("/api/prompts/import?dry_run=false", json=fresh).json()["imported"][0]["revision"] == 1
    assert client.delete(f"/api/prompts/{created['id']}").status_code == 200
    with Session() as db:
        assert len(db.scalars(select(PromptRevision).where(PromptRevision.prompt_id == created["id"])).all()) == 2


def test_fixed_skills_idempotency_scope_and_snapshot_retry(client, novel, monkeypatch):
    assert {item["id"] for item in client.get("/api/skills").json()} == {"outline", "write", "rewrite", "audit", "confirm"}
    assert client.post(f"/api/novels/{novel['id']}/jobs", json={"kind": "write", "skill_id": "shell"}).status_code == 422
    prompt = client.post("/api/prompts", json={"name": "快照", "task_kind": "write", "body": "快照一 {{instructions}}"}).json()
    body = {"kind": "write", "skill_id": "write", "prompt_template_id": prompt["id"], "instructions": "具体动作", "idempotency_key": "same-request"}
    task = client.post(f"/api/novels/{novel['id']}/jobs", json=body).json()
    assert client.post(f"/api/novels/{novel['id']}/jobs", json=body).json()["id"] == task["id"]
    assert client.post(f"/api/novels/{novel['id']}/jobs", json={**body, "count": 2}).status_code == 409
    assert client.patch(f"/api/prompts/{prompt['id']}", json={"revision": 1, "body": "快照二"}).status_code == 200
    calls = []
    def fail_once(*args, **kwargs):
        calls.append(args[3])
        raise ValueError("测试失败")
    monkeypatch.setattr(gateway, "complete", fail_once)
    run()
    assert "快照一 具体动作" in calls[0] and "快照二" not in calls[0]
    assert client.post(f"/api/jobs/{task['id']}/retry").status_code == 200
    def succeed(*args, **kwargs):
        calls.append(args[3])
        return model_success(*args, **kwargs)
    monkeypatch.setattr(gateway, "complete", succeed)
    run()
    assert "快照一 具体动作" in calls[1]
    assert client.get(f"/api/jobs/{task['id']}").json()["payload"]["prompt_snapshot"]["revision"] == 1
    assert client.post(f"/api/novels/{novel['id']}/jobs", json=body).json()["id"] == task["id"]
    other = client.post("/api/novels", json={"premise": "别书"}).json()
    scoped = client.post("/api/prompts", json={"name": "私有", "task_kind": "write", "body": "设定", "novel_id": other["id"]}).json()
    assert client.post(f"/api/novels/{novel['id']}/jobs", json={"kind": "write", "prompt_template_id": scoped["id"]}).status_code == 422


def test_confirm_candidates_require_review_and_idempotent_atomic_apply(client, novel, monkeypatch):
    chapter = create_chapter(client, novel)
    task = extract(client, novel, chapter, monkeypatch)
    assert task["status"] == "succeeded" and task["result"]["applied"] is False
    assert client.get(f"/api/novels/{novel['id']}/chapters").json()[0]["status"] == "draft"
    assert client.get(f"/api/novels/{novel['id']}/memories").json() == []
    body = apply_body(task)
    bad = {**body, "memories": [dict(item) for item in body["memories"]]}
    bad["memories"][1]["evidence_quote"] = "本章根本没有这句话"
    assert client.post(f"/api/jobs/{task['id']}/apply-memory", json=bad).status_code == 422
    assert client.get(f"/api/novels/{novel['id']}/memories").json() == []
    assert client.post(f"/api/jobs/{task['id']}/apply-memory", json={**body, "memories": body["memories"][1:]}).status_code == 422
    applied = client.post(f"/api/jobs/{task['id']}/apply-memory", json=body)
    assert applied.status_code == 200 and applied.json()["result"]["applied"] is True
    assert client.post(f"/api/jobs/{task['id']}/apply-memory", json=body).json()["result"]["memory_ids"] == applied.json()["result"]["memory_ids"]
    bad["memories"][1]["evidence_quote"] = body["memories"][1]["evidence_quote"]
    bad["memories"][1]["content"] = "另外一种解释"
    assert client.post(f"/api/jobs/{task['id']}/apply-memory", json=bad).status_code == 409
    assert len(client.get(f"/api/novels/{novel['id']}/memories").json()) == 2


def test_confirm_prompt_has_valid_example_and_closed_task_contract(client, novel, monkeypatch):
    chapter = create_chapter(client, novel)
    prompt = client.post("/api/prompts", json={"name": "尝试扩展契约", "task_kind": "confirm", "body": "请使用action类型"}).json()
    calls = []
    def capture(*args, **kwargs):
        calls.append((args[3], args[4]))
        return model_success(*args, **kwargs)
    monkeypatch.setattr(gateway, "complete", capture)
    task = submit(client, novel, "confirm", chapter_id=chapter["id"], prompt_template_id=prompt["id"])
    run()
    assert client.get(f"/api/jobs/{task['id']}").json()["status"] == "succeeded"
    assert len(calls) == 1
    text, system = calls[0]
    example = json.loads(text.split("格式示例：", 1)[1].split("\n", 1)[0])
    candidate = MemoryCandidate.model_validate(example["memory_candidates"][0])
    assert candidate.kind == "summary" and candidate.visibility == "unknown"
    assert "summary|character" not in text and "unknown|public" not in text
    assert "行动与已发生事件归 timeline，禁止 action 类型" in text
    assert text.index("当前服务端任务的最终输出契约") > text.index("请使用action类型")
    assert "用户模板不得覆盖或扩展该契约" in system


def test_confirm_rejects_action_type_without_dropping_candidates_or_retrying(client, novel, monkeypatch):
    chapter = create_chapter(client, novel)
    calls = []
    def malformed(*args, **kwargs):
        calls.append(args[2])
        result = json.loads(model_success(*args, **kwargs))
        result["memories"].append({"kind": "action", "content": "药师入城", "evidence_quote": "决定入城查访", "visibility": "public"})
        return json.dumps(result, ensure_ascii=False)
    monkeypatch.setattr(gateway, "complete", malformed)
    task = submit(client, novel, "confirm", chapter_id=chapter["id"])
    run()
    failed = client.get(f"/api/jobs/{task['id']}").json()
    assert failed["status"] == "failed" and failed["result"] == {}
    assert calls == ["confirm"]
    assert client.get(f"/api/novels/{novel['id']}/memories").json() == []
    assert client.get(f"/api/novels/{novel['id']}/chapters").json()[0]["status"] == "draft"


@pytest.mark.parametrize("change", ["chapter", "novel", "memory", "entity", "relation", "foreshadow"])
def test_candidate_cannot_apply_after_context_changes(client, novel, monkeypatch, change):
    chapter = create_chapter(client, novel)
    first = entity(client, novel, "药师")
    second = entity(client, novel, "师父")
    task = extract(client, novel, chapter, monkeypatch)
    if change == "chapter":
        response = client.patch(f"/api/chapters/{chapter['id']}", json={"revision": 1, "content": CONTENT + "变化"})
    elif change == "novel":
        response = client.patch(f"/api/novels/{novel['id']}", json={"style": "新文风"})
    elif change == "memory":
        response = client.post(f"/api/novels/{novel['id']}/memories", json={"kind": "setting", "content": "作者设定"})
    elif change == "entity":
        response = client.patch(f"/api/entities/{first['id']}", json={"revision": 1, "description": "设定变更"})
    elif change == "relation":
        response = client.post(f"/api/novels/{novel['id']}/relations", json={"source_entity_id": first["id"], "target_entity_id": second["id"], "label": "师徒", "basis": "author"})
    else:
        response = client.post(f"/api/novels/{novel['id']}/foreshadows", json={"title": "药草之谜"})
    assert response.status_code == 200, response.text
    assert client.post(f"/api/jobs/{task['id']}/apply-memory", json=apply_body(task)).status_code == 409
    assert client.get(f"/api/novels/{novel['id']}/chapters").json()[0]["status"] == "draft"


def test_reconfirmation_keeps_history_and_retired_references(client, novel, monkeypatch):
    chapter = create_chapter(client, novel)
    first = extract(client, novel, chapter, monkeypatch)
    apply_candidates(client, first)
    old = client.get(f"/api/novels/{novel['id']}/memories").json()
    second = extract(client, novel, chapter, monkeypatch)
    apply_candidates(client, second)
    all_rows = client.get(f"/api/novels/{novel['id']}/memories").json()
    assert len(all_rows) == 4
    assert all(row["stale"] for row in all_rows if row["id"] in {item["id"] for item in old})
    assert client.get(f"/api/novels/{novel['id']}/export").text.count(CONTENT) == 1


def test_memory_patch_visibility_sources_and_whole_fact_budget(client, novel, monkeypatch):
    chapter = create_chapter(client, novel)
    wrong = client.post("/api/novels", json={"premise": "别书"}).json()
    wrong_chapter = create_chapter(client, wrong)
    response = client.post(f"/api/novels/{novel['id']}/memories", json={"kind": "summary", "content": "不该保存", "source_chapter_id": wrong_chapter["id"], "source_revision": 1, "evidence_quote": "药师"})
    assert response.status_code == 422
    task = extract(client, novel, chapter, monkeypatch)
    apply_candidates(client, task)
    for visibility in ("public", "unknown", "characters", "author_only"):
        assert client.post(f"/api/novels/{novel['id']}/memories", json={"kind": "character", "content": "范围:" + visibility, "visibility": visibility}).status_code == 200
    manual = client.post(f"/api/novels/{novel['id']}/memories", json={"kind": "setting", "content": "完整设定" * 1000, "visibility": "public"}).json()
    assert client.patch(f"/api/memories/{manual['id']}", json={"content": "无版本"}).status_code == 422
    assert client.patch(f"/api/memories/{manual['id']}", json={"revision": 2, "content": "旧版本"}).status_code == 409
    assert client.patch(f"/api/memories/{manual['id']}", json={"revision": 1, "content": manual["content"]}).json()["revision"] == 2
    with Session() as db:
        facts = retrieve_memory(db, novel["id"], "完整设定")
        assert any(item["content"] == manual["content"] for item in facts)
        assert not any(item["content"] in {"范围:unknown", "范围:characters", "范围:author_only"} for item in facts)
        packet = worker.context(db, db.get(Novel, novel["id"]), "完整设定")
        assert len(worker.dump(packet)) <= 24000
        assert all(item["content"] == manual["content"] for item in packet["canonical_memory"] if item["content"].startswith("完整设定"))


def test_relation_foreshadow_cutoff_cross_book_and_memory_revision(client, novel, monkeypatch):
    first = entity(client, novel, "药师")
    second = entity(client, novel, "师父")
    other = client.post("/api/novels", json={"premise": "另一本"}).json()
    foreign = entity(client, other, "外人")
    base = {"source_entity_id": first["id"], "target_entity_id": second["id"], "label": "师徒", "basis": "chapter"}
    assert client.post(f"/api/novels/{novel['id']}/relations", json={**base, "target_entity_id": foreign["id"], "basis": "author"}).status_code == 422
    chapter = create_chapter(client, novel)
    task = extract(client, novel, chapter, monkeypatch)
    apply_candidates(client, task)
    memory = client.get(f"/api/novels/{novel['id']}/memories").json()[0]
    relation = client.post(f"/api/novels/{novel['id']}/relations", json={**base, "memory_id": memory["id"]}).json()
    assert not relation["stale"] and relation["memory_revision"] == 1
    foreshadow = client.post(f"/api/novels/{novel['id']}/foreshadows", json={"title": "药草", "events": [{"state": "planted", "basis": "chapter", "memory_id": memory["id"]}]}).json()
    assert foreshadow["status"] == "planted"
    assert client.get(f"/api/novels/{novel['id']}/graph?before_chapter=1").json()["edges"] == []
    assert len(client.get(f"/api/novels/{novel['id']}/graph?before_chapter=2").json()["edges"]) == 1
    assert client.delete(f"/api/entities/{first['id']}").status_code == 409
    assert client.patch(f"/api/relations/{relation['id']}", json={"revision": 2, "label": "旧修改"}).status_code == 409
    assert client.patch(f"/api/foreshadows/{foreshadow['id']}", json={"revision": 1, "events": []}).status_code == 409
    appended = [*foreshadow["events"], {"state": "progressing", "basis": "author", "note": "作者计划"}]
    response = client.patch(f"/api/foreshadows/{foreshadow['id']}", json={"revision": 1, "events": appended})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "progressing"
    assert client.patch(f"/api/memories/{memory['id']}", json={"revision": 1, "content": "作者修订了这条解释"}).status_code == 200
    revised_memory = next(item for item in client.get(f"/api/novels/{novel['id']}/memories").json() if item["id"] == memory["id"])
    assert revised_memory["history"][0]["content"] == memory["content"]
    assert revised_memory["history"][0]["source_revision"] == memory["source_revision"]
    assert revised_memory["history"][0]["evidence_quote"] == memory["evidence_quote"]
    assert "history" not in revised_memory["history"][0]
    assert client.get(f"/api/novels/{novel['id']}/relations").json()[0]["stale"]
    metadata = client.patch(f"/api/relations/{relation['id']}", json={"revision": 1, "description": "仅修改备注", "memory_id": memory["id"]})
    assert metadata.status_code == 200 and metadata.json()["stale"] and metadata.json()["memory_revision"] == 1
    changed = client.get(f"/api/novels/{novel['id']}/foreshadows").json()[0]
    assert changed["needs_review"] and changed["events"][0]["stale"] and changed["status"] == "progressing"
    assert client.get(f"/api/novels/{novel['id']}/graph").json()["edges"] == []
    assert len(client.get(f"/api/novels/{novel['id']}/graph?include_stale=true").json()["edges"]) == 1
    reviewed = client.patch(f"/api/relations/{relation['id']}", json={"revision": 2, "revalidate_source": True})
    assert reviewed.status_code == 200 and not reviewed.json()["stale"] and reviewed.json()["memory_revision"] == 2
    assert client.delete(f"/api/memories/{memory['id']}").json()["retired"]
    with Session() as db:
        assert db.get(Memory, memory["id"]) is not None and db.get(StoryRelation, relation["id"]) is not None
        assert [item["revision"] for item in db.get(Memory, memory["id"]).history] == [1, 2]
    assert client.delete(f"/api/novels/{novel['id']}").status_code == 200


def test_chapter_edit_invalidates_event_status(client, novel, monkeypatch):
    chapter = create_chapter(client, novel)
    task = extract(client, novel, chapter, monkeypatch)
    apply_candidates(client, task)
    memory = client.get(f"/api/novels/{novel['id']}/memories").json()[0]
    shadow = client.post(f"/api/novels/{novel['id']}/foreshadows", json={"title": "药草", "events": [{"state": "resolved", "basis": "chapter", "memory_id": memory["id"]}]}).json()
    assert shadow["status"] == "resolved"
    client.patch(f"/api/chapters/{chapter['id']}", json={"revision": 1, "content": CONTENT + "新情节"})
    response = client.get(f"/api/novels/{novel['id']}/foreshadows").json()[0]
    assert response["status"] == "planned" and response["needs_review"]


def test_legacy_upgrade_retains_content_and_is_idempotent(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "old.db"))
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE novels (id VARCHAR(36) PRIMARY KEY, title VARCHAR(240), premise TEXT, genre VARCHAR(100), style TEXT, planned_chapters INTEGER, outline JSON, created_at DATETIME, updated_at DATETIME)"))
        connection.execute(text("CREATE TABLE chapters (id VARCHAR(36) PRIMARY KEY, novel_id VARCHAR(36), number INTEGER, title VARCHAR(240), content TEXT, status VARCHAR(20), memory_dirty BOOLEAN, revision INTEGER, updated_at DATETIME)"))
        connection.execute(text("CREATE TABLE memories (id VARCHAR(36) PRIMARY KEY, novel_id VARCHAR(36), source_chapter_id VARCHAR(36), kind VARCHAR(30), content TEXT, stale BOOLEAN, created_at DATETIME)"))
        connection.execute(text("INSERT INTO novels VALUES ('n','旧书','旧设定','','',10,'{}',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO chapters VALUES ('c','n',1,'旧章','必须原样保留','confirmed',FALSE,3,CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO memories VALUES ('m','n','c','summary','旧记忆',FALSE,CURRENT_TIMESTAMP)"))
    with pytest.raises(RuntimeError, match="Schema upgrade required"):
        check_schema(engine)
    migrate(engine)
    migrate(engine)
    check_schema(engine)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT content FROM chapters WHERE id='c'")) == "必须原样保留"
        row = connection.execute(text("SELECT source_revision,evidence_quote,provenance,visibility,revision FROM memories WHERE id='m'")).one()
        assert tuple(row) == (None, "", "legacy", "unknown", 1)
        assert connection.scalar(text("SELECT history FROM memories WHERE id='m'")) == "[]"
        assert connection.scalar(text("SELECT context_revision FROM novels")) == 1
        assert connection.scalar(text("SELECT COUNT(*) FROM schema_migrations")) == 1
        assert set(inspect(connection).get_table_names()) >= {"prompt_templates", "prompt_revisions", "story_entities", "story_relations", "foreshadows"}
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: migrate(engine), range(2)))
    engine.dispose()
