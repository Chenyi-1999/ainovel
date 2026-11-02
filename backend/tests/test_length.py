"""Length is a storage contract, with one existing bounded repair opportunity."""
import json
from datetime import timedelta

import pytest

from app import gateway, worker
from app.db import Job, Session, now
from app.length import count_body_words, next_scene_budget, require_replacements, scene_count, word_bounds
from test_workflow import get_chapters, run, submit


def answer(content, purpose, count=1, index=1):
    parts = [content[index * len(content) // count:(index + 1) * len(content) // count] for index in range(count)]
    entries = [{"id": index, "content": part} for index, part in enumerate(parts, 1)]
    return json.dumps({"title": "标题不计入" * 20, "scenes": [{"id": index, "content": content}]} if purpose == "write"
                      else {"report": "模型声称已达标", "replacements": entries if content else []}, ensure_ascii=False)


def result(client, task):
    return client.get(f"/api/jobs/{task['id']}").json()


def test_unicode_codepoints_and_whitespace_contract():
    # Supplementary-plane characters are one codepoint; combining marks count
    # separately, as do punctuation, letters and digits. This is not UTF-16 len.
    body = "中，A1😀𠀀e\u0301"
    assert count_body_words(" \n\r\t\u00a0\u3000" + body + "\v\f") == 8
    assert word_bounds(301) == (271, 331)
    assert word_bounds(4800) == (4320, 5280)
    assert word_bounds(6000) == (5400, 6600)


@pytest.mark.parametrize("target,count", [(300, 1), (800, 1), (801, 2), (2000, 3), (4800, 6), (6000, 8)])
def test_section_count_bounds_model_calls(target, count):
    assert scene_count(target) == count


@pytest.mark.parametrize("target,actual,remaining,expected", [
    (4800, 0, 6, 800), (4800, 500, 5, 860), (4800, 5000, 3, 200),
    (4800, 0, 1, 4800), (301, 50, 1, 251), (301, 5000, 1, 200)])
def test_dynamic_section_budget_is_bounded_guidance(target, actual, remaining, expected):
    assert next_scene_budget(target, actual, remaining) == expected


@pytest.mark.parametrize("scenes", [None, "正文", ["正文"],
    [{"id": True, "content": "正文"}], [{"id": 1.0, "content": "正文"}],
    [{"id": 0, "content": "正文"}], [{"id": 3, "content": "正文"}],
    [{"id": 1, "content": "正文"}, {"id": 1, "content": "重复"}],
    [{"id": 1, "content": "正文"}, {"id": 2, "content": " \n\t"}],
    [{"id": 1, "content": "正文"}, {"id": 2, "content": 12}],
    [{"id": 1, "content": "正文", "text": "双来源"}, {"id": 2, "content": "正文"}]])
def test_section_contract_rejects_invalid_or_ambiguous_entries(scenes):
    with pytest.raises(ValueError):
        require_replacements(scenes, 2)


def test_section_contract_orders_ids_without_changing_original_text():
    parts = require_replacements([{"id": 2, "content": " 第二节\n"}, {"id": 1, "content": "\n首节 "}], 2)
    assert "\n\n".join(parts[index] for index in range(1, 3)) == "\n首节 \n\n 第二节\n"


def test_partial_section_repair_preserves_others_and_total_is_only_hard_budget(client, novel, monkeypatch):
    originals = [f"{index}" * 500 for index in range(1, 7)]
    calls = []
    def model(*args, **kwargs):
        calls.append((args[2], args[3], args[4], kwargs["max_tokens"]))
        if args[2] == "write":
            index = json.loads(args[3].rsplit("\n", 1)[1])["section_id"]
            return json.dumps({"title": "章节" if index == 1 else "后续标题不采用",
                               "scenes": [{"id": index, "content": originals[index - 1]}]})
        return json.dumps({"report": "扩写第二节", "replacements": [{"id": 2, "content": "修" * 2300}]})
    monkeypatch.setattr(gateway, "complete", model)
    monkeypatch.setattr(worker, "template_instruction", lambda job: "创作风格标记。")
    task = submit(client, novel, "write", target_words=4800)
    run()
    completed = result(client, task)
    assert completed["status"] == "succeeded"
    assert [call[0] for call in calls] == ["write"] * 6 + ["audit"]
    assigned = [800, 860, 950, 1100, 1400, 2300]
    assert [call[3] for call in calls] == [min(18000, budget * 3 + 5000) for budget in assigned] + [18000]
    assert all("创作风格标记" in call[1] and "4320–5280" in call[2] for call in calls)
    packet = json.loads(calls[-1][1].rsplit("\n", 1)[1])
    assert packet["draft_words"] == 3000 and packet["target_deficit"] == 1800
    assert [scene["actual_words"] for scene in packet["scenes"]] == [500] * 6
    assert [scene["content"] for scene in packet["scenes"]] == originals
    originals[1] = "修" * 2300
    assert get_chapters(client, novel)[0]["content"] == "\n\n".join(originals)
    stats = completed["result"]["last_length"]
    assert stats["scene_budgets"] == assigned and stats["final_words"] == 4800
    assert stats["final_scene_words"] == [500, 2300, 500, 500, 500, 500]
    assert stats["generation_calls"] == 6 and stats["model_calls"] == 7
    assert get_chapters(client, novel)[0]["title"] == "章节"
    for index, call in enumerate(calls[:-1], 1):
        packet = json.loads(call[1].rsplit("\n", 1)[1])
        assert packet["previous_scenes"] == [{"id": prior, "content": originals[prior - 1] if prior != 2 else "2" * 500}
                                              for prior in range(1, index)]
        assert ("末节：" if index == 6 else "首节：" if index == 1 else "中间节：") in call[2]


@pytest.mark.parametrize("first_size", [4800, 6000])
def test_early_large_section_still_gets_all_parts_and_one_final_audit(client, novel, monkeypatch, first_size):
    calls = []
    def model(*args, **kwargs):
        calls.append(args[2])
        if args[2] == "write":
            packet = json.loads(args[3].rsplit("\n", 1)[1])
            index = packet["section_id"]
            if index > 1:
                assert packet["section_target_words"] == 200
            return answer("文" * (first_size if index == 1 else 10), "write", index=index)
        # One complete audit patch compresses the oversized whole, with no retry.
        return json.dumps({"report": "压缩全文", "replacements": [{"id": index, "content": "修" * 800}
                                                                   for index in range(1, 7)]})
    monkeypatch.setattr(gateway, "complete", model)
    task = submit(client, novel, "write", target_words=4800)
    run()
    assert result(client, task)["status"] == "succeeded"
    assert calls == ["write"] * 6 + ["audit"]
    assert count_body_words(get_chapters(client, novel)[0]["content"]) == 4800


def test_maximum_batch_has_bounded_180_calls_and_no_intermediate_chapter(client, novel, monkeypatch):
    calls = []
    def model(*args, **kwargs):
        calls.append(args[2])
        # Only previously finished chapters may be visible during generation.
        assert len(get_chapters(client, novel)) == (len(calls) - 1) // 9
        if args[2] == "write":
            packet = json.loads(args[3].rsplit("\n", 1)[1])
            assert packet["section_count"] == 8 and packet["section_target_words"] == 750
            assert kwargs["max_tokens"] == 7250
            return answer("文" * 750, "write", index=packet["section_id"])
        assert kwargs["max_tokens"] == 18000
        return answer("", "audit")
    monkeypatch.setattr(gateway, "complete", model)
    task = submit(client, novel, "write", target_words=6000, count=20)
    run()
    completed = result(client, task)
    assert completed["status"] == "succeeded" and completed["current"] == 20
    assert calls == (["write"] * 8 + ["audit"]) * 20
    assert all(item["generation_calls"] == 8 and item["model_calls"] == 9 for item in completed["result"]["lengths"])
    skill = next(item for item in client.get("/api/skills").json() if item["id"] == "write")
    assert skill["max_calls"] == 180 and "重试另计" in skill["description"]


def test_each_section_and_audit_renews_lease_beyond_original_ten_minutes(client, novel, monkeypatch):
    clock = [now()]
    monkeypatch.setattr(worker, "now", lambda: clock[0])
    calls = []
    task = submit(client, novel, "write", target_words=4800)
    def model(*args, **kwargs):
        calls.append(args[2])
        with Session() as db:
            live = db.get(Job, task["id"])
            assert live.lease_until.replace(tzinfo=None) == (clock[0] + timedelta(minutes=10)).replace(tzinfo=None)
        assert worker.claim_job() is None
        clock[0] += timedelta(minutes=4)
        if args[2] == "write":
            return answer("文" * 800, "write", index=json.loads(args[3].rsplit("\n", 1)[1])["section_id"])
        return answer("", "audit")
    monkeypatch.setattr(gateway, "complete", model)
    run()
    assert result(client, task)["status"] == "succeeded" and len(calls) == 7


@pytest.mark.parametrize("cancel_after", [1, 3, 6])
def test_cancel_between_sections_stops_all_further_calls(client, novel, monkeypatch, cancel_after):
    task = submit(client, novel, "write", target_words=4800)
    calls = []
    def model(*args, **kwargs):
        calls.append(args[2])
        if len(calls) == cancel_after:
            assert client.post(f"/api/jobs/{task['id']}/cancel").status_code == 200
        return answer("文" * 800, "write", index=len(calls))
    monkeypatch.setattr(gateway, "complete", model)
    run()
    assert result(client, task)["status"] == "cancelled"
    assert calls == ["write"] * cancel_after and get_chapters(client, novel) == []


def test_takeover_between_sections_fences_old_owner_before_next_call(client, novel, monkeypatch):
    task = submit(client, novel, "write", target_words=4800)
    calls, replacement = [], []
    def model(*args, **kwargs):
        calls.append(args[2])
        if len(calls) == 2:
            with Session() as db:
                live = db.get(Job, task["id"])
                live.lease_until = now() - timedelta(seconds=1)
                db.commit()
            replacement.append(worker.claim_job())
        return answer("文" * 800, "write", index=len(calls))
    monkeypatch.setattr(gateway, "complete", model)
    run()
    live = result(client, task)
    assert live["status"] == "running" and live["current"] == 0 and live["result"] == {}
    assert replacement[0][0] == task["id"] and calls == ["write", "write"]
    assert get_chapters(client, novel) == []


@pytest.mark.parametrize("change", [
    {"scenes": []}, {"scenes": [{"id": 1, "content": "错误编号"}]},
    {"scenes": [{"id": 1, "content": "整章"}, {"id": 2, "content": "双节"}]}, {"title": " \n"}])
def test_later_generation_requires_exact_current_section_and_nonempty_title(client, novel, monkeypatch, change):
    calls = []
    def model(*args, **kwargs):
        calls.append(args[2])
        payload = json.loads(answer("文" * 800, "write", index=len(calls)))
        if len(calls) == 2:
            payload.update(change)
        return json.dumps(payload)
    monkeypatch.setattr(gateway, "complete", model)
    task = submit(client, novel, "write", target_words=4800)
    run()
    assert result(client, task)["status"] == "failed"
    assert calls == ["write", "write"] and get_chapters(client, novel) == []


@pytest.mark.parametrize("phase,extra", [("write", {"content": "双来源"}), ("write", {"scenes": []}),
    ("audit", {"content": "双来源"}), ("audit", {"scenes": []}),
    ("audit", {"replacements": [{"id": 1, "content": " \n"}]}),
    ("audit", {"replacements": [{"id": 2, "content": "未知编号"}]}),
    ("audit", {"replacements": [{"id": 1, "content": "重复"}, {"id": 1, "content": "重复"}]})])
def test_malformed_sections_fail_without_commit(client, novel, monkeypatch, phase, extra):
    calls = []
    def model(*args, **kwargs):
        calls.append(args[2])
        payload = json.loads(answer("文" * 500 if args[2] == "write" else "", args[2]))
        if args[2] == phase:
            payload.update(extra)
        return json.dumps(payload)
    monkeypatch.setattr(gateway, "complete", model)
    task = submit(client, novel, "write", target_words=500)
    run()
    failed = result(client, task)
    assert failed["status"] == "failed" and failed["current"] == 0
    assert calls == (["write"] if phase == "write" else ["write", "audit"])
    assert get_chapters(client, novel) == []


@pytest.mark.parametrize("draft_size", [50, 700])
def test_review_repairs_short_or_long_draft_once(client, novel, monkeypatch, draft_size):
    calls = []
    final = "\n".join(["中，A1😀" * 20] * 5)  # 500 codepoints, excluding newlines.
    def model(*args, **kwargs):
        calls.append((args[2], args[3]))
        return answer("文" * draft_size if args[2] == "write" else final, args[2])
    monkeypatch.setattr(gateway, "complete", model)
    task = submit(client, novel, "write", target_words=500)
    run()
    completed = result(client, task)
    assert completed["status"] == "succeeded"
    assert [purpose for purpose, _ in calls] == ["write", "audit"]
    assert all("Unicode 码点" in prompt and "450–550" in prompt for _, prompt in calls)
    assert f"首稿实测 {draft_size} 字" in calls[1][1]
    assert "必须扩写" in calls[1][1] if draft_size < 450 else "必须压缩" in calls[1][1]
    chapters = get_chapters(client, novel)
    assert chapters[0]["content"] == final
    measured = completed["result"]["last_length"]
    assert measured == {"target_words": 500, "min_words": 450, "max_words": 550,
                        "draft_words": draft_size, "final_words": 500, "review_revised": True,
                        "counting_method": "non_whitespace_codepoints", "chapter_id": chapters[0]["id"],
                        "scene_budgets": [500], "draft_scene_words": [draft_size], "final_scene_words": [500],
                        "generation_calls": 1, "model_calls": 2}
    assert completed["result"]["lengths"] == [measured]


@pytest.mark.parametrize("actual,success", [(270, False), (271, True), (331, True), (332, False)])
def test_exact_inclusive_nonround_boundaries(client, novel, monkeypatch, actual, success):
    calls = []
    def model(*args, **kwargs):
        calls.append(args[2])
        return answer("文" * actual if args[2] == "write" else "", args[2])
    monkeypatch.setattr(gateway, "complete", model)
    task = submit(client, novel, "write", target_words=301)
    run()
    completed = result(client, task)
    assert calls == ["write", "audit"]
    assert completed["status"] == ("succeeded" if success else "failed")
    assert len(get_chapters(client, novel)) == int(success)
    if not success:
        assert "目标 301 字" in completed["error"] and f"实际 {actual} 字" in completed["error"]
        assert "271–331" in completed["error"] and completed["current"] == 0


@pytest.mark.parametrize("revision", ["", "文" * 120])
def test_report_claim_cannot_make_short_output_succeed(client, novel, monkeypatch, capsys, revision):
    calls = []
    def model(*args, **kwargs):
        calls.append(args[2])
        if args[2] == "write":
            index = json.loads(args[3].rsplit("\n", 1)[1])["section_id"]
            part = "文" * ((index * 1279 // 6) - ((index - 1) * 1279 // 6))
            return answer(part, "write", index=index)
        return answer(revision, "audit", count=6)
    monkeypatch.setattr(gateway, "complete", model)
    task = submit(client, novel, "write", target_words=4800)
    run()
    failed = result(client, task)
    assert failed["status"] == "failed" and failed["result"] == {}
    assert "目标 4800 字" in failed["error"] and "4320–5280" in failed["error"]
    assert f"实际 {len(revision) if revision else 1279} 字" in failed["error"]
    assert calls == ["write"] * 6 + ["audit"] and get_chapters(client, novel) == []
    logs = [json.loads(line.split(": ", 1)[1]) for line in capsys.readouterr().out.splitlines()
            if line.startswith("Chapter length metadata: ") and '"phase": "section"' not in line]
    assert logs[0]["phase"] == "draft" and logs[0]["actual_words"] == 1279
    assert logs[-1]["phase"] == "final" and logs[-1]["actual_words"] == (len(revision) if revision else 1279)


@pytest.mark.parametrize("revision", ["文" * 40, "文" * 449, "文" * 551])
def test_out_of_range_review_keeps_valid_draft_and_reports_rejection(client, novel, monkeypatch, revision):
    draft = "文" * 500
    monkeypatch.setattr(gateway, "complete", lambda *args, **kwargs: answer(draft if args[2] == "write" else revision, args[2]))
    task = submit(client, novel, "write", target_words=500)
    run()
    completed = result(client, task)
    assert completed["status"] == "succeeded"
    assert get_chapters(client, novel)[0]["content"] == draft
    measured = completed["result"]["last_length"]
    assert measured["final_words"] == measured["draft_words"] == 500
    assert measured["review_revised"] is False
    assert "审稿篇幅修订未采用" in completed["result"]["report"]
    assert f"修订实测 {count_body_words(revision)} 字" in completed["result"]["report"]


def test_length_failure_batch_retry_preserves_progress_and_statistics(client, novel, monkeypatch):
    writes = 0
    def model(*args, **kwargs):
        nonlocal writes
        if args[2] == "write":
            writes += 1
        return answer("文" * (500 if writes == 1 else 100), args[2])
    monkeypatch.setattr(gateway, "complete", model)
    task = submit(client, novel, "write", target_words=500, count=3)
    run()
    failed = result(client, task)
    first_id = get_chapters(client, novel)[0]["id"]
    assert failed["status"] == "failed" and failed["current"] == 1
    assert failed["result"]["chapter_ids"] == [first_id]
    assert failed["result"]["last_length"]["chapter_id"] == first_id
    assert writes == 2
    monkeypatch.setattr(gateway, "complete", lambda *args, **kwargs: answer("文" * 500 if args[2] == "write" else "", args[2]))
    assert client.post(f"/api/jobs/{task['id']}/retry").status_code == 200
    run()
    completed = result(client, task)
    chapters = get_chapters(client, novel)
    assert completed["status"] == "succeeded" and completed["current"] == 3
    assert [item["number"] for item in chapters] == [1, 2, 3] and chapters[0]["id"] == first_id
    assert [item["chapter_id"] for item in completed["result"]["lengths"]] == [item["id"] for item in chapters]


def test_cancelled_short_draft_does_not_trigger_repair(client, novel, monkeypatch):
    task = submit(client, novel, "write", target_words=500)
    calls = []
    def model(*args, **kwargs):
        calls.append(args[2])
        assert client.post(f"/api/jobs/{task['id']}/cancel").status_code == 200
        return answer("文" * 20, args[2])
    monkeypatch.setattr(gateway, "complete", model)
    run()
    assert result(client, task)["status"] == "cancelled"
    assert calls == ["write"] and get_chapters(client, novel) == []


def test_cancel_during_section_repair_discards_complete_output(client, novel, monkeypatch):
    task = submit(client, novel, "write", target_words=500)
    calls = []
    def model(*args, **kwargs):
        calls.append(args[2])
        if args[2] == "audit":
            assert client.post(f"/api/jobs/{task['id']}/cancel").status_code == 200
        return answer("文" * (100 if args[2] == "write" else 500), args[2])
    monkeypatch.setattr(gateway, "complete", model)
    run()
    assert result(client, task)["status"] == "cancelled"
    assert calls == ["write", "audit"] and get_chapters(client, novel) == []


def test_storage_boundary_rechecks_body_not_reported_statistics(client, novel, monkeypatch):
    monkeypatch.setattr(worker, "produce", lambda *args: {"title": "测试", "content": "文" * 100,
                                                         "report": "声称达标", "length": {"final_words": 500}})
    task = submit(client, novel, "write", target_words=500)
    run()
    failed = result(client, task)
    assert failed["status"] == "failed" and "实际 100 字" in failed["error"]
    assert failed["current"] == 0 and get_chapters(client, novel) == []


def test_existing_short_chapter_confirm_and_rewrite_keep_their_contracts(client, novel, monkeypatch):
    chapter = client.post(f"/api/novels/{novel['id']}/chapters", json={"title": "短章", "content": "原有短章。"}).json()
    calls = []
    def model(*args, **kwargs):
        calls.append(args[2])
        if args[2] == "confirm":
            return json.dumps({"memory_candidates": [{"kind": "summary", "content": "短章摘要", "evidence_quote": "原有短章。"}]}, ensure_ascii=False)
        return "改写短章。"
    monkeypatch.setattr(gateway, "complete", model)
    confirm = submit(client, novel, "confirm", chapter_id=chapter["id"], target_words=6000)
    run()
    assert result(client, confirm)["status"] == "succeeded"
    rewrite = submit(client, novel, "rewrite", chapter_id=chapter["id"], target_words=6000)
    run()
    assert result(client, rewrite)["status"] == "succeeded"
    assert result(client, rewrite)["result"]["content"] == "改写短章。"
    assert get_chapters(client, novel)[0]["content"] == "原有短章。"
    assert calls == ["confirm", "rewrite"]
