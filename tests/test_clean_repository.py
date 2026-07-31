from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CleanRepositoryContractTests(unittest.TestCase):
    def test_application_uses_the_new_independent_identity(self):
        from app import app

        self.assertEqual("Medical Knowledge Hub", app.title)

    def test_repository_contains_only_the_new_product_entrypoints(self):
        required = (
            "app.py",
            "extensions/platforms/registry.py",
            "extensions/processing/compiler.py",
            "routes_ext/platforms.py",
            "routes_ext/knowledge.py",
            "static/inbox.html",
            "static/review.html",
            "skills/distill-medical-wechat/SKILL.md",
        )

        missing = [path for path in required if not (ROOT / path).is_file()]

        self.assertEqual([], missing)

    def test_repository_does_not_restore_the_retired_backend(self):
        retired_paths = (
            "routes/account.py",
            "routes/article.py",
            "routes/rss.py",
            "utils/auth_manager.py",
            "utils/rss_store.py",
        )

        present = [path for path in retired_paths if (ROOT / path).exists()]

        self.assertEqual([], present)

    def test_runtime_paths_do_not_point_to_the_old_repository_slug(self):
        files = (
            "env.example",
            "install.ps1",
            "launch.ps1",
            "extensions/processing/job_store.py",
            "extensions/processing/source_cache.py",
            "extensions/platforms/wechat/parser.py",
        )
        stale = [
            path
            for path in files
            if "content-knowledge-hub" in (ROOT / path).read_text("utf-8").lower()
        ]

        self.assertEqual([], stale)


if __name__ == "__main__":
    unittest.main()
