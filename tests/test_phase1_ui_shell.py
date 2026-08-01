import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from app import app


ACTIVE_PAGES = (
    "/admin.html",
    "/inbox.html",
    "/wechat-collect.html",
    "/wechat-subscriptions.html",
    "/literature-subscriptions.html",
    "/review.html",
    "/trash.html",
    "/platforms.html",
)
RETIRED_PAGES = (
    "/login.html",
    "/rss.html",
    "/history.html",
    "/categories.html",
    "/blacklist.html",
    "/verify.html",
)


class UiShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = TestClient(app)
        cls.client = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)

    def test_active_pages_load_shared_assets(self):
        for path in ACTIVE_PAGES:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(200, response.status_code)
                self.assertIn('href="/static/css/app.css', response.text)
                self.assertIn('src="/static/js/api-client.js"', response.text)
                self.assertIn('src="/static/js/app-shell.js"', response.text)

    def test_retired_pages_are_gone(self):
        for path in RETIRED_PAGES:
            with self.subTest(path=path):
                self.assertEqual(404, self.client.get(path).status_code)

    def test_navigation_points_to_manual_inbox_and_not_backend_login(self):
        shell = self.client.get("/static/js/app-shell.js").text

        self.assertIn("/inbox.html", shell)
        self.assertIn("/review.html", shell)
        self.assertNotIn("/login.html", shell)
        self.assertNotIn("/rss.html", shell)
        self.assertNotIn("/api/admin/status", shell)

    def test_overview_links_to_project_repository(self):
        html = self.client.get("/admin.html").text

        self.assertIn("https://github.com/zoutingjian37-create/medical-knowledge-hub", html)
        self.assertNotIn("/api/public/searchbiz", html)

    def test_runtime_guides_do_not_restore_the_retired_login_flow(self):
        root = Path(__file__).resolve().parents[1]
        runtime_files = (
            "README.md",
            "env.example",
            "docker-compose.yml",
            "start.bat",
            "start.sh",
            "status.sh",
        )
        missing = [name for name in runtime_files if not (root / name).is_file()]
        self.assertEqual([], missing)
        text = "\n".join(
            (root / name).read_text(encoding="utf-8")
            for name in runtime_files
        )
        for retired_marker in (
            "WECHAT_TOKEN=",
            "WECHAT_COOKIE=",
            "/login.html",
            "/api/public/searchbiz",
            "ENABLE_MCP=",
        ):
            self.assertNotIn(retired_marker, text)


if __name__ == "__main__":
    unittest.main()
