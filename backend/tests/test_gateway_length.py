"""Provider budgets and stop metadata, with HTTP fully mocked."""
import json

import httpx
import pytest

from app import gateway
from test_workflow import get_chapters, run, submit


@pytest.mark.parametrize("purpose", ["write", "audit"])
@pytest.mark.parametrize("reason", ["stop", "length"])
@pytest.mark.parametrize("ark", [False, True])
def test_http_budget_and_length_stop(client, novel, monkeypatch, capsys, purpose, reason, ark):
    monkeypatch.setenv("LLM_TRANSPORT", "http")
    if ark:
        monkeypatch.setenv("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    requests = []
    def response(url, **kwargs):
        requests.append(kwargs["json"])
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "choices": [{"message": {"content": "private-body"}, "finish_reason": reason}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 674}})
    monkeypatch.setattr(gateway.httpx, "post", response)
    if reason == "length":
        with pytest.raises(ValueError, match="长度上限"):
            gateway.complete(novel["id"], None, purpose, "private-prompt", "private-system", max_tokens=18000)
    else:
        assert gateway.complete(novel["id"], None, purpose, "private-prompt", "private-system", max_tokens=18000) == "private-body"
    assert requests[0]["max_completion_tokens" if ark else "max_tokens"] == 18000
    assert ("max_tokens" if ark else "max_completion_tokens") not in requests[0]
    logged = capsys.readouterr().out
    metadata = json.loads(logged.split("LLM completion metadata: ")[1])
    assert metadata == {"purpose": purpose, "max_tokens": 18000, "finish_reason": reason, "output_tokens": 674}
    assert "private-" not in logged and "test-secret-not-real" not in logged
    usage = client.get(f"/api/novels/{novel['id']}/usage").json()
    assert usage["requests"] == 1 and usage["output_tokens"] == 674


def test_provider_finish_reason_is_not_logged_verbatim(capsys):
    gateway.completion_metadata("write", 18000, "private-provider-string", "bad-counter")
    logged = capsys.readouterr().out
    assert "private-provider-string" not in logged
    assert '"finish_reason": "unknown"' in logged and '"output_tokens": 0' in logged


@pytest.mark.parametrize("truncated_phase", [None, "write", "audit"])
def test_http_worker_status_distinguishes_stop_and_length(client, novel, monkeypatch, truncated_phase):
    monkeypatch.setenv("LLM_TRANSPORT", "http")
    calls = []
    def response(url, **kwargs):
        body = kwargs["json"]
        phase = "write" if len(calls) < 6 else "audit"
        calls.append(body)
        content = ({"title": "章节", "scenes": [{"id": len(calls), "content": "文" * 800}]}
                   if phase == "write" else {"report": "符合要求", "replacements": []})
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "choices": [{"message": {"content": json.dumps(content)},
                         "finish_reason": "length" if phase == truncated_phase else "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 100}})
    monkeypatch.setattr(gateway.httpx, "post", response)
    task = submit(client, novel, "write", target_words=4800)
    run()
    completed = client.get(f"/api/jobs/{task['id']}").json()
    assert completed["status"] == ("failed" if truncated_phase else "succeeded")
    assert len(calls) == (1 if truncated_phase == "write" else 7)
    assert all(call["max_tokens"] == (7400 if index < 6 else 18000) for index, call in enumerate(calls))
    assert len(get_chapters(client, novel)) == int(truncated_phase is None)
    if truncated_phase:
        assert "长度上限" in completed["error"]
