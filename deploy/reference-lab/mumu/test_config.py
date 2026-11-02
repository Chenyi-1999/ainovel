"""Static regression checks; does not import or run the upstream application."""
from __future__ import annotations

import ast
from pathlib import Path
import tempfile
import unittest

import yaml

import patch_ui_only as patch

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[2] / ".reference-sources/mumu"


class EvaluationConfigTests(unittest.TestCase):
    def test_patch_matches_pinned_source_and_parses(self):
        original = patch.checked_text(SOURCE / "backend/app/services/memory_service.py", patch.MEMORY_SHA256)
        tree = ast.parse(patch.patch_memory(original))
        top_level_imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        names = {n.module if isinstance(n, ast.ImportFrom) else n.names[0].name for n in top_level_imports}
        self.assertNotIn("chromadb", names)
        self.assertNotIn("app.services.onnx_embedding", names)
        memory_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MemoryService")
        init = next(n for n in memory_class.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
        branch = next(n for n in init.body if isinstance(n, ast.If) and isinstance(n.test, ast.Name) and n.test.id == "UI_ONLY")
        self.assertIsInstance(branch.body[-1], ast.Return)
        assigned = {n.targets[0].attr for n in branch.body if isinstance(n, ast.Assign)}
        self.assertEqual(assigned, {"client", "embedding_model", "_initialized"})

    def test_disabled_vector_backend_fails_explicitly(self):
        original = patch.checked_text(SOURCE / "backend/app/services/memory_service.py", patch.MEMORY_SHA256)
        tree = ast.parse(patch.patch_memory(original))
        # Execute only our inserted proxy class, never the upstream module.
        proxy = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_UnavailableVectorBackend")
        namespace = {}
        exec(compile(ast.Module(body=[proxy], type_ignores=[]), "evaluation-proxy", "exec"), namespace)
        backend = namespace["_UnavailableVectorBackend"]()
        with self.assertRaisesRegex(RuntimeError, "disabled"):
            backend.encode("text")
        with self.assertRaisesRegex(RuntimeError, "disabled"):
            backend.get_or_create_collection("name")

    def test_vector_dependencies_removed_only(self):
        original = patch.checked_text(SOURCE / "backend/requirements.txt", patch.REQUIREMENTS_SHA256)
        reduced = patch.patch_requirements(original)
        for name in patch.OMITTED_PACKAGES:
            self.assertFalse(any(line.startswith(name + "==") for line in reduced.splitlines()))
        self.assertIn("fastapi==0.121.0", reduced)
        self.assertIn("asyncpg==0.31.0", reduced)
        self.assertIn("openai==2.7.0", reduced)

    def test_changed_source_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            changed = Path(temporary) / "changed.py"
            changed.write_text("# changed upstream\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unsupported upstream"):
                patch.checked_text(changed, patch.MEMORY_SHA256)

    def test_internal_networks_no_host_ports_and_blank_ai_credentials(self):
        config = yaml.safe_load((HERE / "compose-fragment.yml").read_text(encoding="utf-8"))
        self.assertEqual(set(config["services"]), {"mumu", "mumu-db"})
        for service in config["services"].values():
            self.assertNotIn("ports", service)
        self.assertTrue(all(network["internal"] for network in config["networks"].values()))
        self.assertEqual(config["services"]["mumu-db"]["networks"], ["mumu_db_net"])
        env = config["services"]["mumu"]["environment"]
        for key in ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "XIAOMI_MIMO_API_KEY", "DEFAULT_MODEL"):
            self.assertEqual(env[key], "")
        for key in ("POSTGRES_PASSWORD", "LOCAL_AUTH_PASSWORD", "SESSION_SECRET_KEY"):
            self.assertIn(":?", env[key])
        self.assertEqual(env["MUMU_UI_ONLY"], "true")
        self.assertEqual(env["ONNX_EMBEDDING_OFFLINE"], "true")
        self.assertEqual(config["services"]["mumu"]["mem_limit"], "384m")


if __name__ == "__main__":
    unittest.main()
