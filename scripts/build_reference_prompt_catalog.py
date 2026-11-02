"""Extract a private prompt pack from pinned checkouts, without importing their code.

The public importer contains no upstream prompt bodies. Generated content and
license copies stay in the caller's private output directory, outside Git.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import uuid

NAMESPACE = uuid.UUID("b33f4394-83ba-4daa-878c-182c50fbd110")
MUMU_TASKS = {
    "OUTLINE_CREATE": "outline", "OUTLINE_CONTINUE": "outline",
    "OUTLINE_EXPAND_SINGLE": "outline", "OUTLINE_EXPAND_MULTI": "outline",
    "CHAPTER_GENERATION_ONE_TO_MANY": "write", "CHAPTER_GENERATION_ONE_TO_MANY_NEXT": "write",
    "CHAPTER_GENERATION_ONE_TO_ONE": "write", "CHAPTER_GENERATION_ONE_TO_ONE_NEXT": "write",
    "CHAPTER_REGENERATION_SYSTEM": "rewrite", "PARTIAL_REGENERATE": "rewrite", "PLOT_ANALYSIS": "audit",
}
LITE_TASKS = {
    "outline_generate_v3": "outline", "chapter_generate_v3": "write", "chapter_generate_v4": "write",
    "post_edit_v1": "rewrite", "content_optimize_v1": "rewrite",
}
MUMU_PURPOSES = {
    "封面生成": "封面与工具", "世界构建": "世界与职业设定", "拆书导入": "拆书与反推",
    "角色生成": "人物与组织", "大纲生成": "大纲与细纲", "大纲展开": "大纲与细纲", "情节展开": "大纲与细纲",
    "章节创作": "章节写作", "章节重写": "润色与改写", "情节分析": "情节分析",
    "MCP测试": "封面与工具", "MCP增强": "封面与工具", "灵感模式": "灵感与立意",
    "自动角色引入": "人物与组织", "自动组织引入": "人物与组织",
}
LITE_PURPOSES = {
    "outline_generate_v3": "大纲与细纲", "detailed_outline_generate_v1": "大纲与细纲",
    "plan_chapter_v1": "章节规划", "chapter_generate_v3": "章节写作", "chapter_generate_v4": "章节写作",
    "post_edit_v1": "润色与改写", "content_optimize_v1": "润色与改写",
}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(path: Path) -> str:
    # Avoid implicit newline conversion so the preserved source body is exact.
    return path.read_bytes().decode("utf-8-sig")


def verified_checkout(path: Path, commit: str) -> None:
    actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"], text=True).strip()
    if actual != commit or dirty:
        raise ValueError(f"Expected a clean pinned checkout: {path.name}")


def mumu_literals(path: Path) -> tuple[dict, dict]:
    tree = ast.parse(read_text(path))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PromptService")
    strings = {}
    for node in cls.body:
        if not isinstance(node, ast.Assign):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
        if isinstance(value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    strings[target.id] = value
    method = next(node for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and node.name == "get_all_system_templates")
    definitions = next(ast.literal_eval(node.value) for node in ast.walk(method)
                       if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "template_definitions" for t in node.targets))
    if not isinstance(definitions, dict) or not definitions.keys() <= strings.keys():
        raise ValueError("MuMu static template metadata does not match literal strings")
    return strings, definitions


def mumu_rules(key: str, raw: str) -> str:
    # Only prose/rule sections enter the adapter; output contracts and source-only
    # data injection slots remain preserved in original_body, not executed.
    pattern = r"<(system|task|guidelines|constraints|analysis_framework|requirements)(?:\s[^>]*)?>(.*?)</\1>"
    sections = [match.group(2).strip() for match in re.finditer(pattern, raw, re.S)]
    if not sections:
        raise ValueError(f"No auditable writing-rule sections for {key}")
    body = "\n\n".join(sections).replace("{{", "{").replace("}}", "}")
    variables = {
        "title": "当前章节标题（见任务资料）" if key == "PLOT_ANALYSIS" else "{{title}}",
        "project_title": "{{title}}", "genre": "{{genre}}", "style_content": "{{style}}",
        "requirements": "{{instructions}}", "user_instructions": "{{instructions}}",
        "chapter_number": "本次目标章号", "chapter_title": "当前章节标题（见任务资料）",
        "chapter_count": "本次所需的", "target_word_count": "本次任务指定的目标字数",
        "narrative_perspective": "按本书文风与作者要求", "plot_stage_instruction": "按当前大纲推进阶段",
    }
    return re.sub(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})",
                  lambda match: variables.get(match[1], f"（{match[1]}：以当前任务资料为准，未提供时不适用）"), body)


def adapter_body(rules: str) -> str:
    if "{{" in re.sub(r"{{(?:title|genre|style|instructions)}}", "", rules) or "{%" in rules:
        raise ValueError("Adapter contains unsupported source template syntax")
    return (
        "【当前工作台适配说明】\n以下保留来源的写作方法与质量要求；源系统的输出契约、工具调用及动态数据注入不在此执行。"
        "世界观、人物、已发生事实和章节范围，以本次任务提供的资料为准；未提供的信息不要假装已知。\n"
        "书名：{{title}}；题材：{{genre}}；文风：{{style}}。\n\n" + rules +
        "\n\n作者补充：{{instructions}}\n"
        "【最终约束】来源的格式、字数和流程若与当前任务合同冲突，以后附的当前任务合同为准。"
        "不要调用MCP或其他工具，不输出旧系统的专用分隔符，不编造来源中提及但本次未提供的ID。"
    )


def lite_rules(text: str) -> str:
    """Keep conditional meaning explicit in prose; never evaluate the source DSL."""
    depth = 0
    def replace(match):
        nonlocal depth
        command = match[1].strip()
        if command.startswith("if "):
            expression = command[3:].strip()
            if expression == "post_edit_sanitize":
                condition = "仅当作者明确要求深度去味与一致性修复时"
            else:
                genres = re.findall(r"'([^']+)'\s+in\s+genre", expression)
                remainder = re.sub(r"'[^']+'\s+in\s+genre", "", expression).replace("or", "").strip()
                if not genres or remainder:
                    raise ValueError("Unreviewed Lite conditional expression")
                condition = "仅当本书题材包含" + "、".join(genres) + "任一类型时"
            depth += 1
            return "【适用条件：" + condition + "，才采用下列要求；否则忽略本段】"
        if command == "endif" and depth:
            depth -= 1
            return "【条件段结束】"
        raise ValueError("Unsupported Lite conditional directive")
    result = re.sub(r"{%\s*(.*?)\s*%}", replace, text, flags=re.S)
    if depth:
        raise ValueError("Unclosed Lite conditional")
    return result


def entry(source: dict, key: str, name: str, category: str, description: str, raw: str,
          parameters: list, blocks: list, task: str | None, rules: str | None, path: str, original_category: str) -> dict:
    adapted = task is not None
    body = adapter_body(rules or "") if adapted else raw
    if len(body) > (20000 if adapted else 100000):
        raise ValueError(f"Prompt exceeds supported size: {key}")
    note = ("保留原文与来源参数；适配版仅采用写作规则，改用当前任务资料和服务端输出合同。源条件分支保留为明示适用条件，不执行原系统模板引擎。"
            if adapted else "原系统独立功能或分块注入流程尚未接入；保留完整原文供查看、复制和自行使用，不可直接作为当前任务模板。")
    info = {
        "project": source["project"], "repository": source["repository"], "commit": source["commit"],
        "key": key, "path": path, "license": source["license"], "original_name": name,
        "original_category": original_category, "original_body": raw, "raw_sha256": sha(raw),
        "parameters": sorted(set(parameters)), "blocks": blocks,
        "compatibility": "adapted" if adapted else "reference_only", "adapter_note": note,
        "attribution": source["attribution"], "license_url": source.get("license_url"),
    }
    return {
        "id": str(uuid.uuid5(NAMESPACE, source["project"] + ":" + key)),
        "name": f"{source['short']} · {name}", "category": category, "task_kind": task or "reference",
        "genre_tags": [], "description": description + "\n" + note, "body": body,
        "novel_id": None, "enabled": True, "source_info": info,
    }


def build_catalog(source_root: Path, locks: dict, verify: bool = True) -> dict:
    source_root = source_root.resolve()
    if verify:
        for key in ("mumu", "lite"):
            verified_checkout(source_root / key, locks[key]["commit"])
    sources = [
        {"project": "MuMuAINovel", "short": "MuMu", **locks["mumu"],
         "attribution": "MuMuAINovel 原项目作者及贡献者；规则适配修改见各条adapter_note；原文未改写。",
         "license_url": locks["mumu"]["repository"] + "/blob/" + locks["mumu"]["commit"] + "/LICENSE"},
        {"project": "Ai-Novel Lite", "short": "Lite", **locks["lite"], "license": "未附许可证（当前实例参考包）",
         "attribution": "inliver233/Ai-Novel 原项目作者及贡献者；保留原分块、版本及文本；不随公开源码再分发。"},
    ]
    prompts = []
    mumu_path = Path("backend/app/services/prompt_service.py")
    strings, definitions = mumu_literals(source_root / "mumu" / mumu_path)
    for key, metadata in definitions.items():
        raw = strings[key]
        parameters = list(metadata.get("parameters", [])) + re.findall(r"(?<!\{)\{([A-Za-z_]\w*)\}(?!\})", raw)
        category = MUMU_PURPOSES.get(metadata["category"], "人物与组织" if "角色" in metadata["category"] or "组织" in metadata["category"] else metadata["category"])
        task = MUMU_TASKS.get(key)
        prompts.append(entry(sources[0], key, metadata["name"], category, metadata.get("description", ""), raw,
                             parameters, [], task, mumu_rules(key, raw) if task else None,
                             mumu_path.as_posix(), metadata["category"]))
    resource_base = source_root / "lite/backend/app/resources/prompt_presets"
    for metadata_path in sorted(resource_base.glob("*/preset.json")):
        preset = json.loads(read_text(metadata_path))
        root = metadata_path.parent.resolve()
        blocks = []
        for index, block in enumerate(preset["blocks"]):
            target = (root / block["template_file"]).resolve()
            if not target.is_relative_to(root) or Path(block["template_file"]).is_absolute():
                raise ValueError("Preset template path escapes its resource directory")
            text = read_text(target)
            blocks.append({**block, "body": text, "sha256": sha(text), "source_index": index})
        blocks.sort(key=lambda value: (value.get("injection_order", 0), value["source_index"]))
        raw = "\n\n".join(f"### {block['identifier']} | {block['role']} | {'enabled' if block.get('enabled', True) else 'disabled'}\n" + block["body"] for block in blocks)
        key = metadata_path.parent.name
        task = LITE_TASKS.get(key)
        rule_blocks = [block["body"] for block in blocks if block.get("enabled", True) and
                       any(block["identifier"].endswith(suffix) for suffix in (".role", ".core_role", ".plot_tools", ".sanitize"))]
        if task and not rule_blocks:
            raise ValueError(f"No writing-rule blocks for {key}")
        parameters = [value.strip() for value in re.findall(r"{{\s*([^{}]+)\s*}}", raw)]
        path = metadata_path.relative_to(source_root / "lite").as_posix()
        row = entry(sources[1], key, preset["name"], LITE_PURPOSES[key],
                    f"来源资源 {key}；原版本 {preset.get('version')}；保留 {len(blocks)} 个有序组成块。", raw,
                    parameters, blocks, task, lite_rules("\n\n".join(rule_blocks)) if task else None, path, preset.get("category", ""))
        row["source_info"]["preset_metadata"] = {key: value for key, value in preset.items() if key != "blocks"}
        prompts.append(row)
    if len(prompts) != len({prompt["id"] for prompt in prompts}):
        raise ValueError("Duplicate catalog identity")
    return {"schema_version": 1, "catalog_version": 1, "sources": sources, "prompts": prompts}


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=project / ".reference-sources")
    parser.add_argument("--output", type=Path, default=project / ".secrets/reference-prompt-catalog/catalog.json")
    parser.add_argument("--locks", type=Path, default=project / "deploy/reference-lab/sources.lock.json")
    args = parser.parse_args()
    catalog = build_catalog(args.source_root, json.loads(read_text(args.locks)))
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    shutil.copyfile(args.source_root / "mumu/LICENSE", args.output.parent / "MuMu.LICENSE")
    (args.output.parent / "NOTICE.txt").write_text(
        "当前实例的私有参考内容包。MuMu原文保留GPL-3.0许可全文及项目归属；Lite源检出未附许可证，原文不随本项目公开源码分发。"
        "原文与写作规则适配版分开保存；未执行任何上游模块、Skill或模型调用。\n", encoding="utf-8")
    summary = {"templates": len(catalog["prompts"]), "adapted": sum(p["task_kind"] != "reference" for p in catalog["prompts"]),
               "reference_only": sum(p["task_kind"] == "reference" for p in catalog["prompts"]),
               "lite_blocks": sum(len(p["source_info"]["blocks"]) for p in catalog["prompts"]),
               "categories": {category: sum(p["category"] == category for p in catalog["prompts"]) for category in sorted({p["category"] for p in catalog["prompts"]})}}
    args.output.with_name("summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
