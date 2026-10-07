"""No key is stored in database. Environment credentials have a fixed origin."""
import json
import os
from urllib.parse import urlsplit

import httpx

from . import claude_cli
from .db import Session, Setting, Usage


def settings():
    model = os.getenv("LLM_MODEL", "deepseek-v4-flash")
    default = {"base_url": os.getenv("LLM_BASE_URL", "https://agentrouter.org/v1").rstrip("/"),
               "outline_model": model, "writing_model": model, "review_model": model,
               "memory_model": model, "temperature": 0.8,
               "input_price_per_million": 0, "output_price_per_million": 0}
    with Session() as db:
        row = db.get(Setting, 1)
        if row:
            default.update(row.value)
    # Transport is a deployment decision, never writable through browser settings.
    default["transport"] = transport()
    return default


def transport():
    value = os.getenv("LLM_TRANSPORT", "http")
    if value not in ("http", "claude_cli"):
        raise ValueError("模型调用通道配置不支持")
    return value


def origin(url):
    parsed = urlsplit(url)
    return (parsed.scheme.lower(), parsed.hostname, parsed.port)


def validate_base_url(url):
    parsed = urlsplit(url)
    configured = os.getenv("LLM_BASE_URL", "https://agentrouter.org/v1")
    if (parsed.scheme not in ("http", "https") or parsed.username or parsed.password or
            parsed.query or parsed.fragment or not parsed.hostname):
        raise ValueError("接口地址格式不正确")
    if origin(url) != origin(configured):
        raise ValueError("接口域名须与服务器配置一致，以保护 API 密钥；请在服务器环境变量中修改供应商")
    return url.rstrip("/")


def headers(config):
    validate_base_url(config["base_url"])
    key = os.getenv("LLM_API_KEY", "")
    if not key:
        raise ValueError("服务器尚未配置模型 API 密钥")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def discover_models():
    config = settings()
    if config["transport"] == "claude_cli":
        # The CLI has no live model discovery endpoint. These are configured names.
        configured = [config[role + "_model"] for role in ("outline", "writing", "review", "memory")]
        declared = os.getenv("CLAUDE_AVAILABLE_MODELS", "").split(",")
        return sorted({value.strip()[:160] for value in configured + declared if value.strip()})
    try:
        response = httpx.get(config["base_url"] + "/models", headers=headers(config), timeout=25,
                             follow_redirects=False)
        response.raise_for_status()
        data = response.json()
        return sorted({row["id"][:160] for row in data.get("data", [])
                       if isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"]
                       and row.get("status") not in ("Shutdown", "Retiring")
                       and (urlsplit(config["base_url"]).hostname != "ark.cn-beijing.volces.com"
                            or "TextGeneration" in (row.get("task_type") or []))})
    except (httpx.HTTPError, ValueError, KeyError):
        raise ValueError("无法读取模型列表，请检查服务器的接口地址和密钥配置")


def complete(novel_id, job_id, purpose, prompt, system, max_tokens=6500):
    if len(prompt) + len(system) > 48000:
        raise ValueError("本章与上下文超过单次处理上限，请将过长章节拆分后重试")
    config = settings()
    role = {"outline": "outline", "write": "writing", "rewrite": "writing", "audit": "review", "confirm": "memory"}[purpose]
    model = config[role + "_model"]
    if config["transport"] == "claude_cli":
        return complete_cli(novel_id, job_id, purpose, prompt, system, max_tokens, config, model)
    body = {"model": model, "messages": [{"role": "system", "content": system},
                                           {"role": "user", "content": prompt}], "max_tokens": max_tokens}
    if urlsplit(config["base_url"]).hostname == "ark.cn-beijing.volces.com":
        body["max_completion_tokens"] = body.pop("max_tokens")
        if model.startswith("doubao-seed-"):
            body["thinking"] = {"type": "disabled"}
    # Reasoning model gateways may reject temperature; standard models receive it.
    if not model.startswith(("gpt-5", "o1", "o3", "o4")):
        body["temperature"] = config["temperature"]
    try:
        response = httpx.post(config["base_url"] + "/chat/completions", headers=headers(config),
                              json=body, timeout=httpx.Timeout(180, connect=15), follow_redirects=False)
        if response.status_code == 429:
            raise ValueError("模型接口限流，请稍后重试")
        if response.status_code in (401, 403):
            raise ValueError("模型接口认证失败，请检查服务器密钥或模型权限")
        if response.status_code == 404:
            try:
                error_code = response.json().get("error", {}).get("code")
            except (ValueError, AttributeError):
                error_code = None
            if error_code == "ModelNotOpen":
                raise ValueError("模型尚未开通，请在火山方舟控制台开通模型，或填写已开通的 Model ID / Endpoint ID")
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]
        content = choice["message"].get("content")
        usage = data.get("usage") or {}
        record_usage(novel_id, job_id, purpose, model, config,
                     usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
        if choice.get("finish_reason") == "length":
            raise ValueError("模型输出达到长度上限，未保存截断内容；请缩短目标篇幅后重试")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("模型没有返回可用正文，请重试")
        return content.strip()
    except httpx.TimeoutException:
        raise ValueError("模型接口响应超时，已保留原文；请重试")
    except httpx.ConnectError:
        raise ValueError("服务器无法连接模型网关，已保留原文；请检查服务器网络和接口地址")
    except (httpx.HTTPError, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError("模型接口返回异常，已保留原文；请检查模型配置后重试")


def complete_cli(novel_id, job_id, purpose, prompt, system, max_tokens, config, model):
    # Reuse the same origin and missing-key checks before invoking any process.
    headers(config)
    data, code = claude_cli.invoke(config["base_url"], os.environ["LLM_API_KEY"], model,
                                   prompt, system, max_tokens)
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    # Anthropic separates cached input from uncached input; all are input tokens.
    input_tokens = sum(token_count(usage.get(name)) for name in
                       ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    record_usage(novel_id, job_id, purpose, model, config, input_tokens, usage.get("output_tokens", 0))
    if (code != 0 or data.get("is_error") is not False or data.get("subtype") != "success"):
        raise claude_cli.failure(data.get("result", ""))
    if data.get("stop_reason") == "max_tokens" or token_count(usage.get("output_tokens")) >= max_tokens:
        raise ValueError("模型输出达到长度上限，未保存截断内容；请缩短目标篇幅后重试")
    content = data.get("result")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("模型没有返回可用正文，请重试")
    return content.strip()


def record_usage(novel_id, job_id, purpose, model, config, input_tokens, output_tokens):
    # Malformed provider counters must never leak response data in errors.
    input_tokens, output_tokens = token_count(input_tokens), token_count(output_tokens)
    with Session() as db:
        db.add(Usage(novel_id=novel_id, job_id=job_id, model=model, purpose=purpose,
                     input_tokens=input_tokens, output_tokens=output_tokens,
                     estimated_cost=(input_tokens * config["input_price_per_million"] +
                                     output_tokens * config["output_price_per_million"]) / 1_000_000))
        db.commit()


def parse_json(value):
    value = value.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        result = json.loads(value)
    except json.JSONDecodeError:
        raise ValueError("模型返回的结构化内容格式不正确，请重试")
    if not isinstance(result, dict):
        raise ValueError("模型返回的结构化内容必须是对象，请重试")
    return result


def token_count(value):
    try:
        return max(0, int(value or 0))
    except (ValueError, TypeError, OverflowError):
        return 0
