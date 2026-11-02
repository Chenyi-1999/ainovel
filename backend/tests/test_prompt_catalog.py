"""Synthetic catalog fixtures: upstream text is private and is never copied here."""
from copy import deepcopy
import hashlib
import json
from uuid import NAMESPACE_URL, uuid5

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session as LocalSession

from app.db import Base, Novel, PromptRevision, PromptTemplate, Session
from app.migrations import check_schema, migrate
from app.prompt_catalog import CatalogError, import_catalog, main, validate_pack
from app.prompts import selected_snapshot


def sha(body):
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def entry(key="reference", *, runnable=False):
    original = "Synthetic original {% if source_flag %}{{source_value}}{% endif %}"
    block = "Synthetic block {{unavailable}}"
    return {
        "id": str(uuid5(NAMESPACE_URL, "synthetic-catalog/" + key)), "name": "合成目录 " + key,
        "task_kind": "write" if runnable else "reference", "category": "测试用途",
        "body": "适配 {{title}} {{instructions}}" if runnable else original,
        "source_info": {
            "project": "MuMuAINovel" if runnable else "Ai-Novel Lite",
            "repository": "https://example.invalid/synthetic", "commit": "0" * 40,
            "key": key, "path": "synthetic.json", "license": "synthetic-test",
            "original_name": "合成原名", "original_category": "合成类别", "original_body": original,
            "raw_sha256": sha(original), "parameters": ["source_flag", "source_value"],
            "blocks": [{"identifier": "b1", "name": "合成块", "role": "system", "enabled": False,
                        "injection_order": 2, "template_file": "synthetic.j2", "body": block,
                        "sha256": sha(block), "custom_metadata": {"keep": True}}],
            "compatibility": "adapted" if runnable else "reference_only", "adapter_note": "仅供测试",
        },
    }


def pack(*entries):
    return {"schema_version": 1, "catalog_version": 1, "prompts": list(entries), "sources": [{"project": "synthetic"}]}


def count_rows(db, model):
    return len(db.scalars(select(model)).all())


def test_catalog_dry_run_atomic_apply_idempotency_and_conflicts(client):
    raw = pack(entry(), entry("adapted", runnable=True))
    with Session.begin() as db:
        before = count_rows(db, PromptTemplate), count_rows(db, PromptRevision)
        report = import_catalog(db, raw)
        assert report["added_count"] == 2 and report["source_counts"] == {"Ai-Novel Lite": 1, "MuMuAINovel": 1}
        assert (count_rows(db, PromptTemplate), count_rows(db, PromptRevision)) == before
    with Session.begin() as db:
        assert import_catalog(db, raw, dry_run=False)["added_count"] == 2
    with Session.begin() as db:
        assert import_catalog(db, raw, dry_run=False)["skipped_count"] == 2
        assert count_rows(db, PromptTemplate) == before[0] + 2
        assert count_rows(db, PromptRevision) == before[1] + 2
    conflict = deepcopy(raw)
    conflict["prompts"][0]["description"] = "changed"
    conflict["prompts"].insert(0, entry("would-be-new"))
    with pytest.raises(CatalogError) as error, Session.begin() as db:
        import_catalog(db, conflict, dry_run=False)
    assert error.value.status == 409
    with Session() as db:
        assert db.get(PromptTemplate, entry("would-be-new")["id"]) is None
        assert db.get(PromptTemplate, entry()["id"]).description == ""
    with Session.begin() as db:
        db.get(PromptTemplate, entry()["id"]).deleted = True
    with pytest.raises(CatalogError, match="冲突"), Session.begin() as db:
        import_catalog(db, raw, dry_run=False)
    with Session() as db:
        assert db.get(PromptTemplate, entry()["id"]).deleted


@pytest.mark.parametrize("mutation", ["original_hash", "block_hash", "duplicate_id", "unsafe_body", "wrong_compatibility", "reference_body"])
def test_entire_catalog_is_validated_before_any_write(client, mutation):
    raw = pack(entry("safe", runnable=True), entry("bad", runnable=True))
    bad = raw["prompts"][-1]
    if mutation == "original_hash":
        bad["source_info"]["original_body"] += "tampered"
    elif mutation == "block_hash":
        bad["source_info"]["blocks"][0]["body"] += "tampered"
    elif mutation == "duplicate_id":
        bad["id"] = raw["prompts"][0]["id"]
    elif mutation == "unsafe_body":
        bad["body"] = "{{__import__('os').system('bad')}}"
    elif mutation == "wrong_compatibility":
        bad["source_info"]["compatibility"] = "reference_only"
    else:
        bad["task_kind"], bad["source_info"]["compatibility"] = "reference", "reference_only"
        bad["body"] = "Unhashed replacement"
    with pytest.raises(CatalogError), Session.begin() as db:
        import_catalog(db, raw, dry_run=False)
    with Session() as db:
        assert db.get(PromptTemplate, raw["prompts"][0]["id"]) is None


def test_reference_preview_never_renders_dsl_or_enters_tasks(client, novel):
    original = entry()
    with Session.begin() as db:
        import_catalog(db, pack(original), dry_run=False)
    response = client.post(f"/api/prompts/{original['id']}/preview", json={"novel_id": novel["id"]})
    assert response.status_code == 200
    assert response.json()["rendered"] == original["body"]
    assert response.json()["reference_only"] and response.json()["missing_variables"] == original["source_info"]["parameters"]
    assert client.post(f"/api/novels/{novel['id']}/jobs", json={"kind": "write", "prompt_template_id": original["id"]}).status_code == 422
    assert client.post(f"/api/novels/{novel['id']}/jobs", json={"kind": "reference", "prompt_template_id": original["id"]}).status_code == 422
    with Session() as db:
        with pytest.raises(Exception) as error:
            selected_snapshot(db, original["id"], db.get(Novel, novel["id"]), "reference", "")
        assert error.value.status_code == 422
    # Corrupt metadata/task fields cannot turn a reference-only record into a task.
    with Session.begin() as db:
        row = db.get(PromptTemplate, original["id"])
        row.task_kind, row.body = "write", "Safe-looking body"
    assert client.post(f"/api/novels/{novel['id']}/jobs", json={"kind": "write", "prompt_template_id": original["id"]}).status_code == 422


def test_source_info_roundtrip_versions_copy_and_task_snapshot(client, novel):
    raw = entry("runnable", runnable=True)
    with Session.begin() as db:
        import_catalog(db, pack(raw), dry_run=False)
    item = client.get(f"/api/prompts/{raw['id']}").json()
    assert item["source_info"] == raw["source_info"] and item["source_label"] == "MuMu适配"
    assert client.get(f"/api/prompts/{raw['id']}/versions").json()[0]["snapshot"]["source_info"] == raw["source_info"]
    assert next(row for row in client.get("/api/prompts/export").json()["prompts"] if row["id"] == raw["id"])["source_info"] == raw["source_info"]
    copy = {**item, "name": "用户来源副本", "builtin": True, "source_label": "本项目原创"}
    del copy["id"]
    imported = client.post("/api/prompts/import?dry_run=false", json={"schema_version": 1, "prompts": [copy]})
    assert imported.status_code == 200, imported.text
    copied = imported.json()["imported"][0]
    assert not copied["builtin"] and copied["source_label"] == "用户来源副本" and copied["source_info"] == raw["source_info"]
    changed = client.patch(f"/api/prompts/{copied['id']}", json={"revision": 1, "body": "自定义 {{title}}"}).json()
    assert changed["source_info"] == raw["source_info"]
    job = client.post(f"/api/novels/{novel['id']}/jobs", json={"kind": "write", "prompt_template_id": copied["id"]}).json()
    assert job["payload"]["prompt_snapshot"]["source_info"] == raw["source_info"]


@pytest.mark.parametrize("field,value", [("original_body", "x" * 100001), ("blocks", [{}] * 101), ("parameters", ["x"] * 151), ("other", "中" * 100001)], ids=["original-limit", "block-limit", "parameter-limit", "byte-limit"])
def test_source_metadata_limits(client, field, value):
    body = entry()
    body["source_info"][field] = value
    assert client.post("/api/prompts", json=body).status_code == 422


def test_schema1_upgrade_preserves_templates_history_and_user_data(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "schema1.db"))
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO schema_migrations VALUES (1)"))
        # Recreate the exact previous prompt table shape without the new column.
        columns = [column for column in PromptTemplate.__table__.columns if column.name != "source_info"]
        from sqlalchemy.schema import CreateColumn
        definitions = ", ".join(str(CreateColumn(column).compile(engine)) for column in columns)
        connection.execute(text("CREATE TABLE prompt_templates (" + definitions + ")"))
        connection.execute(text("INSERT INTO prompt_templates (id,name,category,task_kind,genre_tags,description,body,enabled,deleted,revision,builtin,source_label) VALUES ('builtin-write-2','既有模板','正文创作','write','[]','','保留原文',1,0,3,1,'本项目原创')"))
    with pytest.raises(RuntimeError, match="Schema upgrade required"):
        check_schema(engine)
    migrate(engine)
    with LocalSession(engine) as db:
        row = db.get(PromptTemplate, "builtin-write-2")
        assert row.body == "保留原文" and row.revision == 3 and row.source_info == {}
        db.add(PromptRevision(prompt_id=row.id, revision=3, snapshot={"body": row.body}))
        db.commit()
    migrate(engine)
    check_schema(engine)
    with LocalSession(engine) as db:
        assert count_rows(db, PromptRevision) == 1
        assert list(db.scalars(text("SELECT version FROM schema_migrations ORDER BY version"))) == [1, 2]
    engine.dispose()


def test_cli_dry_run_reports_without_mutation_and_controlled_errors(client, tmp_path, capsys):
    path = tmp_path / "private-catalog.json"
    path.write_text(json.dumps(pack(entry())), encoding="utf-8")
    assert main(["--pack", str(path), "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["added_count"] == 1
    with Session() as db:
        assert db.get(PromptTemplate, entry()["id"]) is None
    path.write_text("{invalid", encoding="utf-8")
    assert main(["--pack", str(path), "--apply"]) == 1
    assert json.loads(capsys.readouterr().err)["status"] == 422


def test_dry_run_does_not_initialize_empty_database(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "empty.db"))
    with LocalSession(engine) as db, pytest.raises(CatalogError, match="离线"):
        import_catalog(db, pack(entry()))
    from sqlalchemy import inspect
    assert inspect(engine).get_table_names() == []
    engine.dispose()
