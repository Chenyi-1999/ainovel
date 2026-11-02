import json
from datetime import timedelta

from sqlalchemy import select

from app import gateway, worker
from app.auth import COOKIE
from app.db import Chapter, Job, Memory, Session, now
from app.services import retrieve_memory

CONTENT = "药师在山门前辨认出失传的药草。他没有贸然吞服，而是记下叶脉的走向，决定入城查访。" * 8


def model_success(novel_id, job_id, purpose, prompt, system, **kwargs):
    if purpose == "write":
        return json.dumps({"title": "山门古药", "content": CONTENT}, ensure_ascii=False)
    if purpose == "audit":
        return json.dumps({"report": "没有严重冲突", "content": ""}, ensure_ascii=False)
    if purpose == "confirm":
        return json.dumps({"memories": [{"kind": "summary", "content": "药师记下叶脉，决定入城查访。", "evidence_quote": "决定入城查访", "visibility": "public"},
                                       {"kind": "character", "content": "药师谨慎，不贸然试药。", "evidence_quote": "他没有贸然吞服", "visibility": "public"}]}, ensure_ascii=False)
    if purpose == "outline":
        return json.dumps({"title": "古药", "synopsis": "药师追查身世", "volumes": []}, ensure_ascii=False)
    return "修改后的选段"


def submit(client, novel, kind, **kwargs):
    response = client.post(f"/api/novels/{novel['id']}/jobs", json={"kind": kind, **kwargs})
    assert response.status_code == 200, response.text
    return response.json()


def run():
    claimed = worker.claim_job()
    assert claimed
    worker.run_job(*claimed)


def apply_candidates(client, task):
    job = client.get(f"/api/jobs/{task['id']}").json()
    result = job["result"]
    response = client.post(f"/api/jobs/{task['id']}/apply-memory", json={"expected_revision": result["expected_revision"], "memories": result["memory_candidates"]})
    assert response.status_code == 200, response.text
    return response.json()


def get_chapters(client, novel):
    return client.get(f"/api/novels/{novel['id']}/chapters").json()


def test_auth_origin_and_secret_boundaries(client):
    settings = client.get("/api/settings").json()
    assert settings["has_api_key"] and "test-secret-not-real" not in json.dumps(settings)
    assert client.post("/api/novels", json={"premise": "测试"}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.patch("/api/settings", json={"base_url": "https://evil.example/v1"}).status_code == 422
    client.cookies.set(COOKIE, "bad-token", domain="testserver.local", path="/")
    assert client.get("/api/novels").status_code == 401


def test_draft_confirmation_and_edit_invalidate_canon(client, novel, monkeypatch):
    monkeypatch.setattr(gateway, "complete", model_success)
    submit(client, novel, "write", count=2)
    run()
    chapters = get_chapters(client, novel)
    assert len(chapters) == 2 and all(row["status"] == "draft" for row in chapters)
    assert client.get(f"/api/novels/{novel['id']}/memories").json() == []
    for row in chapters:
        task = submit(client, novel, "confirm", chapter_id=row["id"])
        run()
        assert client.get(f"/api/jobs/{task['id']}").json()["result"]["applied"] is False
        apply_candidates(client, task)
    assert len(client.get(f"/api/novels/{novel['id']}/memories").json()) == 4
    changed = client.patch(f"/api/chapters/{chapters[0]['id']}", json={"content": CONTENT + "他改变了计划。", "revision": 1})
    assert changed.status_code == 200 and changed.json()["revision"] == 2
    memories = client.get(f"/api/novels/{novel['id']}/memories").json()
    assert all(row["stale"] for row in memories)
    with Session() as db:
        assert retrieve_memory(db, novel["id"], "药师") == []
    assert client.get(f"/api/chapters/{chapters[0]['id']}/versions").json()[0]["content"] == CONTENT
    task = submit(client, novel, "confirm", chapter_id=chapters[1]["id"])
    run()
    assert client.get(f"/api/novels/{novel['id']}/jobs").json()[0]["status"] == "failed"


def test_partial_batch_retry_resumes_without_duplicates(client, novel, monkeypatch):
    attempts = 0
    def flaky(*args, **kwargs):
        nonlocal attempts
        if args[2] == "write":
            attempts += 1
            if attempts == 2:
                raise ValueError("模型接口限流，请稍后重试")
        return model_success(*args, **kwargs)
    monkeypatch.setattr(gateway, "complete", flaky)
    task = submit(client, novel, "write", count=3)
    run()
    failed = client.get(f"/api/jobs/{task['id']}").json()
    assert failed["status"] == "failed" and failed["current"] == 1
    assert len(get_chapters(client, novel)) == 1
    monkeypatch.setattr(gateway, "complete", model_success)
    assert client.post(f"/api/jobs/{task['id']}/retry").status_code == 200
    run()
    assert [row["number"] for row in get_chapters(client, novel)] == [1, 2, 3]
    assert client.get(f"/api/jobs/{task['id']}").json()["status"] == "succeeded"


def test_cancel_discards_inflight_output_and_edit_guard(client, novel, monkeypatch):
    task = submit(client, novel, "write")
    assert client.patch(f"/api/novels/{novel['id']}", json={"title": "新名"}).status_code == 409
    assert client.post(f"/api/novels/{novel['id']}/jobs", json={"kind": "write"}).status_code == 409
    calls = []
    def cancelled(*args, **kwargs):
        calls.append(args[2])
        response = client.post(f"/api/jobs/{task['id']}/cancel")
        assert response.status_code == 200
        return model_success(*args, **kwargs)
    monkeypatch.setattr(gateway, "complete", cancelled)
    run()
    assert calls == ["write"]  # Cancellation stops subsequent review model calls.
    assert get_chapters(client, novel) == []
    assert client.get(f"/api/jobs/{task['id']}").json()["status"] == "cancelled"
    assert client.patch(f"/api/novels/{novel['id']}", json={"title": "新名"}).status_code == 200


def test_lease_fences_old_worker_and_recovers(client, novel, monkeypatch):
    monkeypatch.setattr(gateway, "complete", model_success)
    task = submit(client, novel, "write")
    old_claim = worker.claim_job()
    with Session() as db:
        row = db.get(Job, task["id"])
        row.lease_until = now() - timedelta(seconds=1)
        db.commit()
    new_claim = worker.claim_job()
    assert old_claim[0] == new_claim[0] and old_claim[1] != new_claim[1]
    worker.run_job(*old_claim)
    assert get_chapters(client, novel) == []
    worker.run_job(*new_claim)
    assert len(get_chapters(client, novel)) == 1


def test_rewrite_is_proposal_and_revision_guard(client, novel, monkeypatch):
    monkeypatch.setattr(gateway, "complete", model_success)
    submit(client, novel, "write")
    run()
    chapter = get_chapters(client, novel)[0]
    task = submit(client, novel, "rewrite", chapter_id=chapter["id"], selection="决定入城查访")
    run()
    result = client.get(f"/api/jobs/{task['id']}").json()["result"]
    assert "修改后的选段" in result["content"]
    assert get_chapters(client, novel)[0]["content"] == CONTENT
    assert client.patch(f"/api/chapters/{chapter['id']}", json={"content": result["content"], "revision": 0}).status_code == 409
    assert client.patch(f"/api/chapters/{chapter['id']}", json={"content": result["content"], "revision": 1}).status_code == 200
    assert client.post(f"/api/jobs/{task['id']}/retry").status_code == 409


def test_invalid_memory_leaves_draft_unchanged(client, novel, monkeypatch):
    monkeypatch.setattr(gateway, "complete", model_success)
    submit(client, novel, "write")
    run()
    chapter = get_chapters(client, novel)[0]
    monkeypatch.setattr(gateway, "complete", lambda *args, **kwargs: '{"memories":[{"kind":"unknown","content":"幻觉"}]}')
    task = submit(client, novel, "confirm", chapter_id=chapter["id"])
    run()
    assert client.get(f"/api/jobs/{task['id']}").json()["status"] == "failed"
    assert get_chapters(client, novel)[0]["status"] == "draft"
    assert client.get(f"/api/novels/{novel['id']}/memories").json() == []


def test_old_chapter_context_excludes_future_canon(client, novel, monkeypatch):
    monkeypatch.setattr(gateway, "complete", model_success)
    submit(client, novel, "write", count=2)
    run()
    chapters = get_chapters(client, novel)
    task = submit(client, novel, "confirm", chapter_id=chapters[1]["id"])
    run()
    apply_candidates(client, task)
    with Session() as db:
        ctx = worker.context(db, db.get(worker.Novel, novel["id"]), "", before_number=2)
        assert ctx["canonical_memory"] == []
        assert all(row["number"] < 2 for row in ctx["recent_chapters"])


def test_context_budget_bounds_growing_novel(client, novel):
    with Session() as db:
        book = db.get(worker.Novel, novel["id"])
        book.outline = {"huge_outline": "设定" * 100000}
        book.premise = "故事" * 6000
        book.style = "风格" * 2500
        for index in range(24):
            db.add(Memory(novel_id=novel["id"], kind="setting", content="设定药草" * 2500))
        db.commit()
        packet = worker.context(db, book, "写作要求" * 1500)
        assert len(worker.dump(packet)) <= 24000
        assert packet["instructions"] == "写作要求" * 1500


def test_retrieval_recalls_ancient_fact_beyond_recent_window(client, novel):
    with Session() as db:
        ancient = Memory(novel_id=novel["id"], kind="setting", content="千年前的紫荆药草只在月圆开放。",
                         created_at=now() - timedelta(days=1000))
        db.add(ancient)
        for index in range(650):
            db.add(Memory(novel_id=novel["id"], kind="timeline", content=f"第 {index} 天进城采购普通物品。"))
        db.commit()
        results = retrieve_memory(db, novel["id"], "紫荆药草")
        assert any("月圆" in item["content"] for item in results)
        assert len(results) <= 18


def test_outline_export_and_delete(client, novel, monkeypatch):
    monkeypatch.setattr(gateway, "complete", model_success)
    task = submit(client, novel, "outline")
    run()
    assert client.get(f"/api/novels/{novel['id']}").json()["outline"]["synopsis"] == "药师追查身世"
    submit(client, novel, "write")
    run()
    for format in ("txt", "md"):
        response = client.get(f"/api/novels/{novel['id']}/export?format={format}")
        assert response.status_code == 200 and CONTENT in response.text
        assert "没有严重冲突" not in response.text
        assert "attachment" in response.headers["content-disposition"]
    assert client.delete(f"/api/novels/{novel['id']}").status_code == 200
    assert client.get(f"/api/jobs/{task['id']}").status_code == 404


def test_manual_chapters_and_selected_export(client, novel):
    first = client.post(f"/api/novels/{novel['id']}/chapters", json={}).json()
    second = client.post(f"/api/novels/{novel['id']}/chapters", json={"title": "入城", "content": "只导出第二章的文字"}).json()
    assert first["number"] == 1 and first["content"] == "" and first["status"] == "draft"
    assert second["number"] == 2
    assert client.get(f"/api/novels/{novel['id']}/memories").json() == []
    response = client.get(f"/api/novels/{novel['id']}/export?from_chapter=2&to_chapter=2")
    assert "只导出第二章的文字" in response.text and "第1章" not in response.text
    assert client.get(f"/api/novels/{novel['id']}/export?from_chapter=2&to_chapter=1").status_code == 422
