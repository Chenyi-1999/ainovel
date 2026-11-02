"""Offline, atomic import of a private declarative prompt catalog.

No upstream Python, template DSL, URLs or model APIs are ever executed here.
Catalog IDs are immutable: identical rows are skipped; conflicts never overwrite.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import inspect, text

from .db import PromptTemplate, Session
from .migrations import SCHEMA_VERSION
from .prompts import CATEGORIES, PromptInput, snapshot, source_label


class CatalogError(ValueError):
    def __init__(self, message, status=422, report=None):
        super().__init__(message)
        self.status, self.report = status, report


class CatalogEntry(PromptInput):
    id: str


class CatalogPack(BaseModel):
    schema_version: Literal[1]
    catalog_version: Literal[1]
    prompts: list[dict] = Field(max_length=1000)
    sources: list[dict] = Field(max_length=100)


SOURCE_FIELDS = {
    "project", "repository", "commit", "key", "path", "license", "original_name",
    "original_category", "original_body", "raw_sha256", "parameters", "blocks",
    "compatibility", "adapter_note",
}


def verify_hash(body, expected, location):
    if not isinstance(body, str) or not isinstance(expected, str) or hashlib.sha256(body.encode("utf-8")).hexdigest() != expected:
        raise CatalogError(f"{location}: SHA256不匹配")


def validate_pack(raw):
    """Validate every entry before obtaining a write transaction."""
    try:
        pack = CatalogPack.model_validate(raw)
        prepared, seen = [], set()
        for index, item in enumerate(pack.prompts):
            entry = CatalogEntry.model_validate(item)
            identity = UUID(entry.id)
            if identity.version != 5 or str(identity) != entry.id:
                raise CatalogError(f"prompts[{index}]: id必须为规范UUIDv5")
            if entry.id in seen:
                raise CatalogError(f"prompts[{index}]: 重复ID")
            seen.add(entry.id)
            info = entry.source_info
            if SOURCE_FIELDS - info.keys():
                raise CatalogError(f"prompts[{index}]: 来源信息缺字段 {', '.join(sorted(SOURCE_FIELDS - info.keys()))}")
            if info["project"] not in ("MuMuAINovel", "Ai-Novel Lite"):
                raise CatalogError(f"prompts[{index}]: 未支持的来源项目")
            if info["compatibility"] not in ("adapted", "reference_only") or (entry.task_kind == "reference") != (info["compatibility"] == "reference_only"):
                raise CatalogError(f"prompts[{index}]: 来源兼容性与任务类型不一致")
            if entry.novel_id is not None or not entry.enabled:
                raise CatalogError(f"prompts[{index}]: 目录模板必须全局启用")
            verify_hash(info["original_body"], info["raw_sha256"], f"prompts[{index}].original_body")
            if entry.task_kind == "reference" and entry.body != info["original_body"]:
                raise CatalogError(f"prompts[{index}]: 参考正文必须与已校验来源原文一致")
            for block_index, block in enumerate(info["blocks"]):
                verify_hash(block.get("body"), block.get("sha256"), f"prompts[{index}].blocks[{block_index}]")
            prepared.append(entry)
        return pack, prepared
    except (ValidationError, HTTPException, ValueError, TypeError, UnicodeError) as exc:
        if isinstance(exc, CatalogError):
            raise
        message = exc.detail if isinstance(exc, HTTPException) else str(exc)
        raise CatalogError(f"目录格式无效: {message}") from exc


def require_schema(db):
    # In particular, dry-run must never initialize an empty database.
    if "schema_migrations" not in inspect(db.connection()).get_table_names() or db.scalar(text("SELECT MAX(version) FROM schema_migrations")) != SCHEMA_VERSION:
        raise CatalogError("须先离线执行 python -m app.migrations --apply", status=409)


def import_catalog(db, raw, *, dry_run=True):
    """The caller owns the transaction; validation/conflict failures write nothing."""
    pack, prepared = validate_pack(raw)
    require_schema(db)
    if not dry_run and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(18110, 2)"))
    additions, skips, conflicts = [], [], []
    for entry in prepared:
        existing = db.get(PromptTemplate, entry.id)
        data = entry.model_dump(exclude={"id"})
        data["category"] = data["category"] or CATEGORIES[entry.task_kind]
        if existing is None:
            additions.append((entry.id, data))
        elif existing.deleted or not existing.builtin or any(getattr(existing, key) != value for key, value in data.items()):
            conflicts.append({"id": entry.id, "name": entry.name, "reason": "ID已存在且内容不同、不是内置模板或已删除"})
        else:
            skips.append(entry.id)
    report = {
        "dry_run": dry_run, "catalog_version": pack.catalog_version,
        "added_count": len(additions), "skipped_count": len(skips),
        "conflict_count": len(conflicts), "conflicts": conflicts,
        "source_counts": dict(Counter(entry.source_info["project"] for entry in prepared)),
        "category_counts": dict(Counter(entry.category or CATEGORIES[entry.task_kind] for entry in prepared)),
        "sources": pack.sources,
    }
    if conflicts and not dry_run:
        raise CatalogError("存在冲突，未导入任何模板", status=409, report=report)
    if not dry_run:
        for identity, data in additions:
            row = PromptTemplate(id=identity, builtin=True, **data)
            row.source_label = source_label(row)
            db.add(row)
            snapshot(db, row)
        db.flush()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline private prompt catalog import; no network or template evaluation")
    parser.add_argument("--pack", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.pack.stat().st_size > 64000000:
            raise CatalogError("目录文件超过64000000字节")
        raw = json.loads(args.pack.read_text(encoding="utf-8"))
        with Session.begin() as db:
            report = import_catalog(db, raw, dry_run=args.dry_run)
        print(json.dumps(report, ensure_ascii=False))
        return 1 if report["conflict_count"] else 0
    except (CatalogError, OSError, ValueError) as exc:
        print(json.dumps({"status": getattr(exc, "status", 422), "error": str(exc),
                          "report": getattr(exc, "report", None)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
