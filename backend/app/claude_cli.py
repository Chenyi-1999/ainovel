"""One isolated, tool-free official Claude Code process per completion.

Only the CLI speaks the provider protocol. Credentials travel in its environment,
prompts through stdin, and neither raw CLI diagnostics nor provider errors escape.
The Docker image supplies a pinned CLI and has no managed Claude configuration.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time


OUTPUT_LIMIT = 2 * 1024 * 1024
ERROR_LIMIT = 64 * 1024


def _kill(process):
    # A new POSIX session gives this invocation its own group, including children.
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def _run(command, env, directory, prompt, timeout):
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, cwd=directory, env=env,
                                   start_new_session=os.name == "posix")
    except OSError:
        raise ValueError("Claude Code 调用程序不可用，请检查服务器镜像配置") from None
    overflow = threading.Event()
    output, errors = bytearray(), bytearray()

    def read(stream, target, limit):
        try:
            while chunk := stream.read(8192):
                remaining = limit - len(target)
                target.extend(chunk[:max(0, remaining)])
                if len(chunk) > remaining:
                    overflow.set()
        except OSError:
            overflow.set()
        finally:
            stream.close()

    def write():
        try:
            process.stdin.write(prompt.encode("utf-8"))
            process.stdin.flush()
        except OSError:
            pass  # An early CLI failure may close stdin before accepting the prompt.
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass

    threads = [threading.Thread(target=read, args=(process.stdout, output, OUTPUT_LIMIT), daemon=True),
               threading.Thread(target=read, args=(process.stderr, errors, ERROR_LIMIT), daemon=True),
               threading.Thread(target=write, daemon=True)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout
    try:
        while process.poll() is None:
            if overflow.is_set():
                raise ValueError("Claude Code 返回内容超过处理上限，未保存；请缩短目标篇幅")
            if time.monotonic() >= deadline:
                raise ValueError("模型接口响应超时，已保留原文；请重试")
            time.sleep(0.05)
    finally:
        if os.name == "posix" or process.poll() is None:
            # Also reap any descendants which outlive a normally exiting CLI.
            _kill(process)
        for thread in threads:
            thread.join(timeout=5)
    if overflow.is_set() or any(thread.is_alive() for thread in threads):
        raise ValueError("Claude Code 返回内容超过处理上限，未保存；请缩短目标篇幅")
    return bytes(output), bytes(errors), process.returncode


def invoke(base_url, key, model, prompt, system, max_tokens):
    try:
        timeout = int(os.getenv("CLAUDE_CLI_TIMEOUT", "180"))
        # A write plus audit has two calls under the worker's ten-minute lease.
        if not 1 <= timeout <= 240:
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError("Claude Code 超时配置须为 1 至 240 秒") from None
    # Never inherit login helpers, plugins, CLI credentials or arbitrary SDK options.
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL",
               "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY",
               "https_proxy", "http_proxy", "all_proxy", "no_proxy", "NODE_EXTRA_CA_CERTS"}
    env = {name: value for name, value in os.environ.items() if name in allowed}
    with tempfile.TemporaryDirectory(prefix="ainovel-claude-") as directory:
        os.chmod(directory, 0o700)
        root = Path(directory)
        config = root / "config"
        config.mkdir(mode=0o700)
        system_file = root / "system.txt"
        system_file.write_text(system, encoding="utf-8")
        system_file.chmod(0o600)
        env.update({"HOME": directory, "CLAUDE_CONFIG_DIR": str(config),
                    "ANTHROPIC_BASE_URL": base_url.removesuffix("/v1"),
                    "ANTHROPIC_AUTH_TOKEN": key, "ANTHROPIC_API_KEY": "",
                    "ANTHROPIC_MODEL": model, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                    "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(max_tokens),
                    "API_TIMEOUT_MS": str(timeout * 1000)})
        command = [os.getenv("CLAUDE_CLI_PATH", "claude"), "-p", "--model", model,
                   "--output-format", "json", "--input-format", "text", "--restricted",
                   "--tools", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                   "--no-session-persistence", "--max-turns", "1", "--disable-slash-commands",
                   "--settings", '{"disableAllHooks":true}', "--system-prompt-file", str(system_file)]
        raw, diagnostic, code = _run(command, env, directory, prompt, timeout)
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("type") != "result":
            raise ValueError()
    except (ValueError, UnicodeDecodeError):
        # Detect common failure classes without exposing stderr, tokens or URLs.
        raise failure(diagnostic) from None
    return data, code


def failure(diagnostic=b""):
    value = diagnostic.lower() if isinstance(diagnostic, bytes) else str(diagnostic).lower().encode()
    if any(marker in value for marker in (b"unauthorized", b"authentication", b"invalid api", b"401", b"403")):
        return ValueError("模型接口认证失败，请检查服务器密钥或模型权限")
    if b"429" in value or b"rate_limit" in value:
        return ValueError("模型接口限流，请稍后重试")
    return ValueError("Claude Code 模型调用失败，已保留原文；请检查模型权限、接口地址和服务器网络")
