"""Extraction tests use synthetic text; no upstream prompt contents are committed."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("reference_catalog_builder", Path(__file__).with_name("build_reference_prompt_catalog.py"))
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


class ExtractionTests(unittest.TestCase):
    def test_ast_extraction_does_not_execute_module_or_skill_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompt_service.py"
            marker = Path(directory) / "executed"
            path.write_text(
                f"open({str(marker)!r}, 'w').write('bad')\n"
                "class PromptService:\n"
                "    ORIGINAL = '<system>synthetic rules</system>'\n"
                "    @staticmethod\n"
                "    def get_all_system_templates():\n"
                "        template_definitions = {'ORIGINAL': {'name':'sample','category':'test','parameters':[]}}\n"
                "        get_all_skills_cached()\n", encoding="utf-8")
            values, metadata = catalog.mumu_literals(path)
            self.assertEqual(list(metadata), ["ORIGINAL"])
            self.assertEqual(values["ORIGINAL"], "<system>synthetic rules</system>")
            self.assertFalse(marker.exists())

    def test_adapter_drops_output_contract_but_preserves_writing_rules(self):
        raw = '<system>Write {genre}</system><task>Keep {title}</task><output>OLD FORMAT</output><constraints>Do not repeat.</constraints>'
        rules = catalog.mumu_rules("OUTLINE_CREATE", raw)
        self.assertNotIn("OLD FORMAT", rules)
        self.assertIn("Do not repeat.", rules)
        self.assertIn("{{title}}", rules)
        self.assertIn("{{genre}}", rules)
        self.assertIn("当前任务合同", catalog.adapter_body(rules))

    def test_lite_conditions_remain_explicit_without_eval(self):
        raw = "{% if '悬疑' in genre or '推理' in genre %}clues{% endif %}"
        result = catalog.lite_rules(raw)
        self.assertIn("仅当本书题材包含悬疑、推理任一类型时", result)
        self.assertIn("clues", result)
        self.assertNotIn("{%", result)
        with self.assertRaises(ValueError):
            catalog.lite_rules("{% if __import__('os') %}bad{% endif %}")
        with self.assertRaises(ValueError):
            catalog.lite_rules("{% if '悬疑' in genre %}unclosed")

    def fixture(self, root, template_file="templates/input.md"):
        source = root / "mumu/backend/app/services"
        source.mkdir(parents=True)
        (source / "prompt_service.py").write_text(
            "class PromptService:\n"
            "    SAMPLE='not evaluated {title}'\n"
            "    def get_all_system_templates(self):\n"
            "        template_definitions={'SAMPLE':{'name':'Synthetic sample','category':'世界构建','parameters':['title']}}\n", encoding="utf-8")
        preset = root / "lite/backend/app/resources/prompt_presets/plan_chapter_v1"
        (preset / "templates").mkdir(parents=True)
        (preset / "templates/input.md").write_bytes(b"first\r\n{{story.raw_content}}\r\nlast")
        (preset / "preset.json").write_text(json.dumps({"name": "Synthetic plan", "version": 1, "category": "plan",
            "blocks": [{"identifier": "user.input", "name": "Input", "role": "user", "enabled": False,
                        "injection_order": 20, "template_file": template_file}]}), encoding="utf-8")
        return {"mumu": {"repository": "https://github.com/example/mumu", "commit": "a" * 40, "license": "GPL-3.0"},
                "lite": {"repository": "https://github.com/example/lite", "commit": "b" * 40, "license": None}}

    def test_complete_blocks_and_exact_original_text_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            locks = self.fixture(root)
            pack = catalog.build_catalog(root, locks, verify=False)
            lite = next(row for row in pack["prompts"] if row["source_info"]["project"] == "Ai-Novel Lite")
            block = lite["source_info"]["blocks"][0]
            self.assertFalse(block["enabled"])
            self.assertEqual(block["body"], "first\r\n{{story.raw_content}}\r\nlast")
            self.assertEqual(block["sha256"], catalog.sha(block["body"]))
            self.assertEqual(lite["body"], lite["source_info"]["original_body"])
            self.assertEqual(lite["task_kind"], "reference")
            self.assertEqual(pack, catalog.build_catalog(root, locks, verify=False))

    def test_template_path_cannot_escape_preset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            locks = self.fixture(root, "../../outside.md")
            with self.assertRaisesRegex(ValueError, "escapes"):
                catalog.build_catalog(root, locks, verify=False)


if __name__ == "__main__":
    unittest.main()
