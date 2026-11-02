"""Static invariants for the evaluation overlay; never imports upstream code."""
from pathlib import Path
import subprocess
import unittest

import yaml

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parent.parent


class EvaluationConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = yaml.safe_load((HERE / "compose-fragment.yml").read_text(encoding="utf-8"))

    def test_runtime_is_internal_and_never_publishes_ports(self):
        self.assertEqual(set(self.config["services"]), {"lite", "lite-api"})
        self.assertTrue(self.config["networks"]["lite_net"]["internal"])
        for service in self.config["services"].values():
            self.assertNotIn("ports", service)
            self.assertNotIn("network_mode", service)
            self.assertNotIn("env_file", service)
            self.assertEqual(service["networks"], ["lite_net"])

    def test_login_is_required_with_isolated_cookies(self):
        env = self.config["services"]["lite-api"]["environment"]
        self.assertEqual(env["AUTH_DEV_FALLBACK_USER_ID"], "")
        for name in ("AUTH_ADMIN_PASSWORD", "AUTH_SESSION_SIGNING_KEY"):
            self.assertIn(":?", env[name])
        self.assertEqual(env["AUTH_COOKIE_USER_ID_NAME"], "lite_session")
        self.assertEqual(env["AUTH_COOKIE_EXPIRE_AT_NAME"], "lite_session_expiry")

    def test_sqlite_single_worker_and_no_provisioned_models(self):
        api = self.config["services"]["lite-api"]
        env = api["environment"]
        self.assertEqual(env["DATABASE_URL"], "sqlite:////data/lite.db")
        self.assertEqual(env["WEB_CONCURRENCY"], "1")
        self.assertEqual(env["TASK_QUEUE_BACKEND"], "inline")
        self.assertEqual(env["INLINE_WORKER_CONCURRENCY"], "1")
        self.assertEqual(api["volumes"], ["lite_data:/data"])
        for name, value in env.items():
            if name.startswith(("VECTOR_", "LINUXDO_")) and name.endswith(
                ("API_KEY", "MODEL", "BASE_URL", "CLIENT_ID", "CLIENT_SECRET")
            ):
                self.assertEqual(value, "", name)

    def test_source_pin_and_docker_context_paths(self):
        sha = subprocess.check_output(
            ["git", "-C", str(ROOT / ".reference-sources/lite"), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        self.assertEqual(sha, "d3bce7437861402083edd77af3cc50b088026b7d")
        for service in self.config["services"].values():
            build = service["build"]
            context = (BASE / build["context"]).resolve()
            self.assertTrue(context.is_dir())
            dockerfile = context / build.get("dockerfile", "Dockerfile")
            self.assertTrue(dockerfile.is_file(), str(dockerfile))

    def test_frontend_preserves_api_paths_and_spa_navigation(self):
        nginx = (HERE / "nginx.conf").read_text(encoding="utf-8")
        self.assertIn("http://lite-api:8000", nginx)
        self.assertIn("proxy_pass $upstream;", nginx)
        self.assertIn("try_files $uri $uri/ /index.html;", nginx)
        self.assertIn("worker_processes 1;", (HERE / "nginx-main.conf").read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
