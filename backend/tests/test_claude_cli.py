"""No provider credentials or network: fake the CLI with a real local subprocess."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx
import pytest
from app import claude_cli, gateway, worker


def envelope(result='{"synopsis":"寻找古药"}', **changes):
    return {"type": "result", "subtype": "success", "is_error": False, "result": result,
            "usage": {"input_tokens": 12, "cache_creation_input_tokens": 5,
                      "cache_read_input_tokens": 7, "output_tokens": 8}, **changes}


@pytest.fixture
def fake_cli(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_TRANSPORT", "claude_cli")
    original = subprocess.Popen
    calls = []

    def install(data=None, script=None, exit_code=0, callback=None):
        source = tmp_path / "fake_cli.py"
        encoded = json.dumps(data or envelope(), ensure_ascii=False).encode("utf-8")
        source.write_text(script or ("import sys\n"
                                     "value = sys.stdin.buffer.read()\n"
                                     f"sys.stdout.buffer.write({encoded!r})\n"
                                     f"sys.exit({exit_code})\n"), encoding="utf-8")

        def launch(command, **kwargs):
            call = {"command": command, **kwargs}
            call["system"] = Path(command[-1]).read_text(encoding="utf-8")
            calls.append(call)
            process = original([sys.executable, str(source)], **kwargs)
            call["process"] = process
            if callback:
                callback()
            return process
        monkeypatch.setattr(claude_cli.subprocess, "Popen", launch)
        return calls
    return install


def job(client, novel, kind="outline"):
    response = client.post(f"/api/novels/{novel['id']}/jobs", json={"kind": kind})
    assert response.status_code == 200
    return response.json()["id"]


def test_cli_isolation_stdin_proxy_and_usage(client, novel, fake_cli, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://private-proxy.example:8080")
    monkeypatch.setenv("CLAUDE_CODE_API_KEY_HELPER", "unwanted-helper")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "unwanted-key")
    calls = fake_cli(script="import sys,json\nvalue=sys.stdin.buffer.read().decode('utf-8')\n"
                     "assert value == '第一章中文要求'\n"
                     f"sys.stdout.buffer.write({json.dumps(envelope()).encode()!r})\n")
    task = job(client, novel)
    client.patch("/api/settings", json={"outline_model": "glm-5.3", "input_price_per_million": 2,
                                        "output_price_per_million": 3})
    result = gateway.complete(novel["id"], task, "outline", "第一章中文要求", "中文作者", max_tokens=1234)
    assert gateway.parse_json(result)["synopsis"] == "寻找古药"
    call = calls[0]
    command, env = call["command"], call["env"]
    assert "第一章中文要求" not in command and "中文作者" not in command
    assert "test-secret-not-real" not in repr(command)
    assert call["system"] == "中文作者"
    assert command[command.index("--model") + 1] == "glm-5.3"
    assert command[command.index("--tools") + 1] == ""
    assert "--restricted" in command and "--no-session-persistence" in command
    assert command[command.index("--settings") + 1] == '{"disableAllHooks":true}'
    assert command[command.index("--max-turns") + 1] == "1"
    assert env["ANTHROPIC_BASE_URL"] == "https://co.agentrouter.org"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "test-secret-not-real" and env["ANTHROPIC_API_KEY"] == ""
    assert env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "1234"
    assert env["HTTPS_PROXY"] == "http://private-proxy.example:8080"
    assert "CLAUDE_CODE_API_KEY_HELPER" not in env
    assert not Path(call["cwd"]).exists()  # Temporary files removed after completion.
    assert call["start_new_session"] == (os.name == "posix")
    usage = client.get(f"/api/novels/{novel['id']}/usage").json()
    assert usage["input_tokens"] == 24 and usage["output_tokens"] == 8 and usage["requests"] == 1
    assert usage["estimated_cost"] == pytest.approx(0.000072)


@pytest.mark.parametrize("changes,exit_code,expected", [
    ({"is_error": True, "result": "unauthorized_client test-secret-not-real"}, 0, "认证失败"),
    ({"is_error": True, "subtype": "error_max_turns"}, 0, "调用失败"),
    ({}, 1, "调用失败"),
    ({"result": ""}, 0, "没有返回可用正文"),
    ({"stop_reason": "max_tokens"}, 0, "长度上限"),
    ({"usage": {"output_tokens": 100}}, 0, "长度上限"),
])
def test_cli_failure_and_truncation_records_spend(client, novel, fake_cli, changes, exit_code, expected):
    calls = fake_cli(envelope(**changes), exit_code=exit_code)
    with pytest.raises(ValueError, match=expected) as failure:
        gateway.complete(novel["id"], job(client, novel), "outline", "要求", "作者", max_tokens=100)
    assert "test-secret-not-real" not in str(failure.value)
    assert not Path(calls[0]["cwd"]).exists()
    assert client.get(f"/api/novels/{novel['id']}/usage").json()["requests"] == 1


def test_malformed_cli_output_does_not_leak_diagnostics(client, novel, fake_cli):
    fake_cli(script="import sys\nsys.stdin.buffer.read()\n"
                    "sys.stderr.write('401 invalid API test-secret-not-real')\n"
                    "sys.stdout.write('not JSON test-secret-not-real')\n")
    with pytest.raises(ValueError, match="认证失败") as error:
        gateway.complete(novel["id"], job(client, novel), "outline", "要求", "作者")
    assert "test-secret-not-real" not in str(error.value)
    assert client.get(f"/api/novels/{novel['id']}/usage").json()["requests"] == 0


def test_cli_timeout_kills_process_and_cleans_config(client, novel, fake_cli, monkeypatch):
    monkeypatch.setenv("CLAUDE_CLI_TIMEOUT", "1")
    calls = fake_cli(script="import sys,time\nsys.stdin.buffer.read()\ntime.sleep(30)\n")
    started = time.monotonic()
    with pytest.raises(ValueError, match="响应超时"):
        gateway.complete(novel["id"], job(client, novel), "outline", "要求", "作者")
    assert time.monotonic() - started < 8
    assert calls[0]["process"].poll() is not None
    assert not Path(calls[0]["cwd"]).exists()


def test_cli_output_is_bounded(client, novel, fake_cli, monkeypatch):
    monkeypatch.setattr(claude_cli, "OUTPUT_LIMIT", 1024)
    fake_cli(script="import sys\nsys.stdin.buffer.read()\nsys.stdout.buffer.write(b'x'*65536)\n")
    with pytest.raises(ValueError, match="超过处理上限"):
        gateway.complete(novel["id"], job(client, novel), "outline", "要求", "作者")


@pytest.mark.skipif(os.name != "posix", reason="Linux deployment process-group cleanup")
def test_timeout_kills_descendant_group(client, novel, fake_cli, monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CLI_TIMEOUT", "1")
    pid_file = tmp_path / "child-pid"
    calls = fake_cli(script="import sys,time,subprocess,pathlib\nsys.stdin.buffer.read()\n"
                     "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])\n"
                     f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid))\n"
                     "time.sleep(30)\n")
    with pytest.raises(ValueError, match="响应超时"):
        gateway.complete(novel["id"], job(client, novel), "outline", "要求", "作者")
    assert calls[0]["process"].poll() is not None
    pid = int(pid_file.read_text())
    # A killed child can remain a zombie until init reaps it; it must not run.
    for _ in range(20):
        status = Path(f"/proc/{pid}/stat")
        if not status.exists() or status.read_text().split()[2] == "Z":
            break
        time.sleep(0.05)
    else:
        pytest.fail("CLI descendant remains running after timeout")


def test_cli_config_validation_happens_before_process(client, novel, fake_cli, monkeypatch):
    calls = fake_cli()
    task = job(client, novel)
    with pytest.raises(ValueError, match="单次处理上限"):
        gateway.complete(novel["id"], task, "outline", "x" * 48000, "作者")
    monkeypatch.setenv("LLM_API_KEY", "")
    with pytest.raises(ValueError, match="尚未配置"):
        gateway.complete(novel["id"], task, "outline", "要求", "作者")
    assert calls == []


def test_cli_timeout_bound_keeps_two_calls_within_worker_lease(client, novel, fake_cli, monkeypatch):
    calls = fake_cli()
    monkeypatch.setenv("CLAUDE_CLI_TIMEOUT", "300")
    with pytest.raises(ValueError, match="1 至 240"):
        gateway.complete(novel["id"], job(client, novel), "outline", "要求", "作者")
    assert calls == []


def test_cli_models_are_configured_and_transport_read_only(client, fake_cli, monkeypatch):
    fake_cli()
    monkeypatch.setenv("CLAUDE_AVAILABLE_MODELS", "glm-5.3,deepseek-v4-flash")
    monkeypatch.setattr(gateway.httpx, "get", lambda *a, **k: pytest.fail("CLI must not discover models over HTTP"))
    models = client.get("/api/models").json()
    assert models == {"models": ["deepseek-v4-flash", "glm-5.3"], "source": "configured"}
    assert client.get("/api/settings").json()["transport"] == "claude_cli"
    # Unknown patch fields cannot override environment transport.
    assert client.patch("/api/settings", json={"transport": "http"}).json()["transport"] == "claude_cli"


def test_cli_real_gateway_preserves_worker_cancellation_fence(client, novel, fake_cli):
    content = "药师辨认古药，决定入城。" * 30
    task = job(client, novel, "write")
    calls = fake_cli(envelope(result=json.dumps({"title": "古药", "scenes": [{"id": 1, "content": content}]})),
                     callback=lambda: client.post(f"/api/jobs/{task}/cancel"))
    worker.run_job(*worker.claim_job())
    assert len(calls) == 1  # Existing checkpoint stops the subsequent audit call.
    assert client.get(f"/api/jobs/{task}").json()["status"] == "cancelled"
    assert client.get(f"/api/novels/{novel['id']}/chapters").json() == []
    assert client.get(f"/api/novels/{novel['id']}/usage").json()["requests"] == 1


def test_http_default_transport_and_shared_usage(client, novel, monkeypatch):
    monkeypatch.delenv("LLM_TRANSPORT", raising=False)
    monkeypatch.setattr(claude_cli, "invoke", lambda *a: pytest.fail("Default transport must remain HTTP"))
    captured = []
    def response(url, **kwargs):
        captured.append(kwargs)
        return httpx.Response(200, json={"choices": [{"message": {"content": "正文"}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": "bad-counter", "completion_tokens": 9}},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(gateway.httpx, "post", response)
    assert gateway.complete(novel["id"], job(client, novel), "outline", "要求", "作者") == "正文"
    assert captured[0]["headers"]["Authorization"] == "Bearer test-secret-not-real"
    usage = client.get(f"/api/novels/{novel['id']}/usage").json()
    assert usage["input_tokens"] == 0 and usage["output_tokens"] == 9 and usage["requests"] == 1
