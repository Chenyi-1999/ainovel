#!/usr/bin/env python3
"""Run a live end-to-end smoke check against an AINovel deployment.

This creates one clearly named smoke novel. It leaves that novel in place by
default; pass --cleanup only when deletion of this script's novel is intended.
The script never reads the server's model/API credentials.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError as exc:  # pragma: no cover - depends on deployment venv
    raise SystemExit("httpx is required; run this script with the backend virtualenv Python") from exc


TERMINAL_JOBS = {"succeeded", "failed", "cancelled"}
PASSWORD_LABEL = re.compile(r"^\s*[^:\r\n]{1,80}\s*[:：]\s*(.*?)\s*$")


class SmokeFailure(RuntimeError):
    pass


def read_password(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise SmokeFailure(f"Cannot read login password file: {path}") from exc
    for line in text.splitlines():
        match = PASSWORD_LABEL.match(line)
        if match and match.group(1):
            return match.group(1).strip()
    raise SmokeFailure("Password file has no non-empty label: password line")


def safe_request(client: httpx.Client, method: str, route: str, **kwargs: Any) -> httpx.Response:
    """Make an API call without surfacing response bodies or exception details."""
    try:
        response = client.request(method, route, **kwargs)
    except httpx.RequestError as exc:
        raise SmokeFailure(f"Network error calling {route} ({type(exc).__name__})") from None
    if not response.is_success:
        # Server/provider error bodies can include prompt or credential details.
        raise SmokeFailure(f"API call {method} {route} returned HTTP {response.status_code}")
    return response


def json_response(response: httpx.Response, label: str) -> Any:
    try:
        return response.json()
    except ValueError:
        raise SmokeFailure(f"{label} returned invalid JSON") from None


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def job(client: httpx.Client, novel_id: str, kind: str, *, timeout: float,
        **payload: Any) -> dict[str, Any]:
    body = {"kind": kind, **payload}
    created = json_response(safe_request(client, "POST", f"/api/novels/{novel_id}/jobs", json=body),
                            f"Create {kind} job")
    job_id = created.get("id")
    require(isinstance(job_id, str) and job_id, f"Create {kind} job returned no job ID")
    deadline = time.monotonic() + timeout
    while True:
        current = json_response(safe_request(client, "GET", f"/api/jobs/{job_id}"), f"Read {kind} job")
        status = current.get("status")
        if status in TERMINAL_JOBS:
            require(status == "succeeded", f"{kind} job ended with status {status!r}")
            return current
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            # Cancellation is best effort; the timeout is still reported safely.
            try:
                client.post(f"/api/jobs/{job_id}/cancel")
            except httpx.RequestError:
                pass
            raise SmokeFailure(f"{kind} job did not finish within {timeout:g} seconds")
        time.sleep(min(2.0, remaining))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Deployment origin, for example http://127.0.0.1:18110")
    parser.add_argument("--password-file", type=Path, required=True,
                        help="Local login file containing a label: password line")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for JSON evidence and exported TXT")
    parser.add_argument("--job-timeout", type=float, default=320,
                        help="Maximum seconds to wait for each model job (default: 320)")
    parser.add_argument("--cleanup", action="store_true",
                        help="Delete only the smoke novel created by this run after evidence has been captured")
    args = parser.parse_args()
    if args.job_timeout <= 0:
        parser.error("--job-timeout must be positive")

    base_url = args.base_url.rstrip("/") + "/"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_path = args.output_dir / f"ainovel-smoke-{stamp}.json"
    sample_path = args.output_dir / f"ainovel-smoke-{stamp}.txt"
    evidence: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "status": "running",
        "checks": [],
        "artifacts": {"evidence_json": str(evidence_path), "sample_txt": str(sample_path)},
    }
    novel_id: str | None = None

    def record(name: str, **details: Any) -> None:
        evidence["checks"].append({"name": name, "status": "passed", **details})

    def get_json(client: httpx.Client, route: str) -> Any:
        return json_response(safe_request(client, "GET", route), route)

    try:
        password = read_password(args.password_file)
        with httpx.Client(base_url=base_url, timeout=httpx.Timeout(30), follow_redirects=False,
                          headers={"Origin": base_url.rstrip("/")}) as client:
            health = get_json(client, "/api/health")
            require(health.get("status") == "ok", "Health endpoint did not report ok")
            record("health")

            json_response(safe_request(client, "POST", "/api/login", json={"password": password}), "Login")
            password = ""  # Drop the local reference once the session cookie is established.
            require(get_json(client, "/api/me").get("authenticated") is True, "Login session was not authenticated")
            record("login")

            title = f"验收样章-{stamp}"
            novel = json_response(safe_request(client, "POST", "/api/novels", json={
                "title": title,
                "premise": "一名谨慎的边城药师发现药材与城中旧案相连，必须在追查真相时守住救人的底线。",
                "genre": "悬疑奇幻",
                "style": "中文通俗小说，情节清楚，人物行动有因果，避免重复铺陈。",
                "planned_chapters": 20,
            }), "Create smoke novel")
            novel_id = novel.get("id")
            require(isinstance(novel_id, str) and novel_id, "Smoke novel creation returned no ID")
            evidence["novel"] = {"id": novel_id, "initial_title": title, "kept_by_default": not args.cleanup}
            record("create_smoke_novel", novel_id=novel_id)

            outline_job = job(client, novel_id, "outline", timeout=args.job_timeout)
            outline = outline_job.get("result") or {}
            require(isinstance(outline, dict) and bool(outline.get("synopsis")), "Outline result has no synopsis")
            record("outline", title=outline.get("title"), synopsis_characters=len(outline["synopsis"]))

            first_job = job(client, novel_id, "write", timeout=args.job_timeout,
                            target_words=1000,
                            instructions="写一个完整的开篇章节，建立药师、旧案线索和一个具体悬念。")
            first_ids = (first_job.get("result") or {}).get("chapter_ids") or []
            require(bool(first_ids), "First write returned no chapter IDs")
            chapters = get_json(client, f"/api/novels/{novel_id}/chapters")
            first = next((item for item in chapters if item.get("id") == first_ids[0]), None)
            require(first is not None and len((first.get("content") or "").strip()) >= 100,
                    "First chapter is missing or shorter than 100 characters")
            record("write_first_chapter", chapter_id=first["id"], number=first["number"],
                   characters=len(first["content"]))

            confirm_job = job(client, novel_id, "confirm", timeout=args.job_timeout,
                              chapter_id=first["id"])
            memories = get_json(client, f"/api/novels/{novel_id}/memories")
            first_memories = [item for item in memories if item.get("source_chapter_id") == first["id"]]
            require(confirm_job.get("status") == "succeeded" and first_memories,
                    "Chapter confirmation produced no saved memories")
            record("confirm_first_chapter", memory_count=len(first_memories))

            selection = first["content"].strip()[:100]
            require(len(selection) >= 30, "First chapter is too short to select a passage")
            rewrite_job = job(client, novel_id, "rewrite", timeout=args.job_timeout,
                              chapter_id=first["id"], selection=selection,
                              instructions="让选段更具体、自然，并保持事件事实不变。")
            proposal = rewrite_job.get("result") or {}
            proposed_content = proposal.get("content")
            require(isinstance(proposed_content, str) and len(proposed_content.strip()) >= 100,
                    "Rewrite job returned no complete chapter proposal")
            # The rewrite endpoint only proposes; explicitly save with revision guard.
            saved = json_response(safe_request(client, "PATCH", f"/api/chapters/{first['id']}", json={
                "content": proposed_content, "revision": first["revision"],
            }), "Save rewrite proposal")
            require(saved.get("revision", 0) > first["revision"] and saved.get("content") == proposed_content,
                    "Saving rewrite did not persist the proposal as a new revision")
            require(saved.get("memory_dirty") is True,
                    "Editing the confirmed chapter did not mark its canon memory dirty")
            versions = get_json(client, f"/api/chapters/{first['id']}/versions")
            require(any(version.get("revision") == first["revision"] and
                        version.get("content") == first["content"] and
                        version.get("title") == first["title"] for version in versions),
                    "Original chapter revision was not preserved in chapter versions")
            record("rewrite_and_version", chapter_id=first["id"], revision=saved["revision"],
                   version_count=len(versions), characters=len(proposed_content))

            # Edits dirty canon; re-confirm before asking for the next chapter.
            second_confirm = job(client, novel_id, "confirm", timeout=args.job_timeout,
                                 chapter_id=first["id"])
            require(second_confirm.get("status") == "succeeded", "Edited chapter could not be confirmed")
            confirmed_chapters = get_json(client, f"/api/novels/{novel_id}/chapters")
            confirmed_first = next((item for item in confirmed_chapters if item.get("id") == first["id"]), None)
            require(confirmed_first is not None and confirmed_first.get("memory_dirty") is False and
                    confirmed_first.get("status") == "confirmed",
                    "Reconfirming the edited chapter did not restore confirmed canon state")
            memories = get_json(client, f"/api/novels/{novel_id}/memories")
            first_memories = [item for item in memories if item.get("source_chapter_id") == first["id"]]
            require(first_memories and all(item.get("stale") is False for item in first_memories),
                    "Reconfirmed chapter has no active, non-stale memories")
            record("reconfirm_after_edit", memory_count=len(first_memories))

            second_job = job(client, novel_id, "write", timeout=args.job_timeout,
                             target_words=600,
                             instructions="承接上一章已经发生的事实和人物状态，推进旧案线索并留下新的行动目标。")
            second_ids = (second_job.get("result") or {}).get("chapter_ids") or []
            require(bool(second_ids), "Second write returned no chapter IDs")
            chapters = get_json(client, f"/api/novels/{novel_id}/chapters")
            second = next((item for item in chapters if item.get("id") == second_ids[0]), None)
            require(second is not None and second.get("number") > first["number"] and
                    len((second.get("content") or "").strip()) >= 100,
                    "Second chapter is missing, out of order, or shorter than 100 characters")
            record("write_second_chapter", chapter_id=second["id"], number=second["number"],
                   characters=len(second["content"]), confirmed_memory_count=len(first_memories))

            audit_job = job(client, novel_id, "audit", timeout=args.job_timeout,
                            chapter_id=second["id"])
            audit_result = audit_job.get("result") or {}
            require(isinstance(audit_result.get("report"), str) and bool(audit_result["report"].strip()),
                    "Audit job returned no report")
            record("audit", chapter_id=second["id"], report_characters=len(audit_result["report"]))

            exported_response = safe_request(client, "GET", f"/api/novels/{novel_id}/export", params={"format": "txt"})
            exported = exported_response.text
            require(exported.startswith(title + "\n\n第1章 "), "TXT export did not include novel title and first chapter")
            require(proposed_content in exported, "TXT export does not contain the saved first chapter rewrite")
            require(second["content"] in exported, "TXT export does not contain the stored second chapter body")
            # Preserve HTTP bytes; text-mode writes translate LF on Windows.
            sample_path.write_bytes(exported_response.content)
            # Compare byte-for-byte with a second export to catch truncation/encoding issues.
            exported_again = safe_request(client, "GET", f"/api/novels/{novel_id}/export",
                                          params={"format": "txt"}).content
            require(sample_path.read_bytes() == exported_again, "Saved sample TXT differs from the API export")
            record("export_copy", characters=len(exported), bytes=sample_path.stat().st_size,
                   path=str(sample_path))

            usage = get_json(client, f"/api/novels/{novel_id}/usage")
            model_names = sorted({row.get("model") for row in usage.get("records", [])
                                  if isinstance(row.get("model"), str) and row.get("model")})
            require(usage.get("requests", 0) > 0, "No model usage records were saved")
            evidence["usage"] = {
                "requests": usage.get("requests"),
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "estimated_cost": usage.get("estimated_cost"),
                "models": model_names,
            }
            evidence["novel"]["final_title"] = (get_json(client, f"/api/novels/{novel_id}") or {}).get("title")

            if args.cleanup:
                safe_request(client, "DELETE", f"/api/novels/{novel_id}")
                evidence["novel"]["deleted_by_cleanup"] = True
                record("cleanup_own_smoke_novel")
            evidence["status"] = "passed"
    except SmokeFailure as exc:
        evidence["status"] = "failed"
        evidence["error"] = str(exc)
        print(f"Smoke verification failed: {exc}", file=sys.stderr)
    except Exception as exc:  # Keep unexpected failures useful without exposing repr/credentials.
        evidence["status"] = "failed"
        evidence["error"] = f"Unexpected error ({type(exc).__name__})"
        print(evidence["error"], file=sys.stderr)
    finally:
        evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
        evidence["novel_id"] = novel_id
        evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": evidence["status"], "novel_id": novel_id,
                          "evidence_json": str(evidence_path), "sample_txt": str(sample_path),
                          "usage": evidence.get("usage")}, ensure_ascii=False, indent=2))
    return 0 if evidence["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
