import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import app
from extensions.platforms.base import PlatformError
from extensions.platforms.wechat.adapter import WeChatAdapter


RETIRED_API_PATHS = {
    "/api/public/searchbiz",
    "/api/public/articles",
    "/api/public/articles/search",
    "/api/public/accountinfo",
    "/api/login/getqrcode",
    "/api/login/scan",
    "/api/login/bizlogin",
    "/api/admin/status",
    "/api/admin/history/fetch",
    "/api/rss/subscribe",
    "/api/rss/batch-subscribe",
    "/api/rss/poll",
    "/api/feed/articles.json",
    "/api/export/account/retired.zip",
    "/api/article",
    "/api/image",
    "/api/stats",
}


class RetiredWechatBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = TestClient(app)
        cls.client = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)

    def test_closed_wechat_backend_routes_are_not_exposed(self):
        openapi_paths = set(self.client.get("/api/openapi.json").json()["paths"])

        self.assertTrue(RETIRED_API_PATHS.isdisjoint(openapi_paths))

    def test_closed_wechat_backend_pages_are_not_served(self):
        for path in (
            "/login.html",
            "/verify.html",
            "/rss.html",
            "/history.html",
            "/categories.html",
            "/blacklist.html",
        ):
            with self.subTest(path=path):
                self.assertEqual(404, self.client.get(path).status_code)

    def test_manual_inbox_keeps_wechat_without_restoring_backend_login(self):
        response = self.client.get("/inbox.html")

        self.assertEqual(200, response.status_code)
        self.assertIn("/api/ext/platforms/queue", response.text)
        self.assertIn("微信", response.text)
        self.assertNotIn("/api/public/searchbiz", response.text)
        self.assertNotIn("/api/login/", response.text)

    def test_obsolete_runtime_modules_are_removed(self):
        root = Path(__file__).parents[1]
        for relative in (
            "routes/article.py",
            "routes/image.py",
            "routes/stats.py",
            "utils/rss_store.py",
            "utils/rss_resilience.py",
            "utils/article_fetcher.py",
        ):
            with self.subTest(relative=relative):
                self.assertFalse((root / relative).exists())


class LinkOnlyWechatAdapterTests(unittest.TestCase):
    def test_creator_discovery_and_batch_listing_are_explicitly_retired(self):
        adapter = WeChatAdapter()

        with self.assertRaisesRegex(PlatformError, "link|URL|链接"):
            import asyncio

            asyncio.run(adapter.search_creator("publisher"))
        with self.assertRaisesRegex(PlatformError, "link|URL|链接"):
            import asyncio

            asyncio.run(adapter.list_creator_items("publisher"))

    def test_public_link_builds_an_item_without_login(self):
        adapter = WeChatAdapter()

        item = adapter.item_ref_from_url("https://mp.weixin.qq.com/s/test-article")

        self.assertEqual("https://mp.weixin.qq.com/s/test-article", item.source_url)
        self.assertEqual("test-article", item.source_item_id)


if __name__ == "__main__":
    unittest.main()
