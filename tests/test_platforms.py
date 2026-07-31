import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from app import app
from extensions.platforms.base import ItemRef, PlatformError, RawItem
from extensions.platforms.registry import build_default_registry
from extensions.platforms.wechat.adapter import WeChatAdapter
from extensions.processing.documents import MarkdownDocument
from extensions.processing.normalizer import NormalizedContent


class PlatformContractTests(unittest.TestCase):
    def test_default_registry_exposes_five_installed_platforms(self):
        registry = build_default_registry()
        statuses = {item.key: item for item in registry.list_platforms()}

        self.assertEqual(
            {"wechat", "zhihu", "bilibili", "xiaohongshu", "douyin"},
            set(statuses),
        )
        self.assertTrue(all(item.installed for item in statuses.values()))
        for key in ("zhihu", "bilibili", "xiaohongshu", "douyin"):
            self.assertEqual("opencli-1.8.6", statuses[key].version)

    def test_supported_public_urls_are_detected_without_guessing(self):
        from extensions.platforms.url_router import detect_platform

        examples = {
            "https://mp.weixin.qq.com/s/example": "wechat",
            "https://www.zhihu.com/question/1/answer/2": "zhihu",
            "https://www.bilibili.com/video/BV1abc123456": "bilibili",
            "https://www.xiaohongshu.com/explore/abc123": "xiaohongshu",
            "https://www.douyin.com/video/7654321": "douyin",
        }
        for url, expected in examples.items():
            with self.subTest(url=url):
                self.assertEqual(expected, detect_platform(url))

        with self.assertRaises(ValueError):
            detect_platform("https://example.com/article/1")

    def test_normalized_content_becomes_a_platform_neutral_markdown_document(self):
        from extensions.processing.documents import from_normalized

        normalized = NormalizedContent(
            platform="bilibili",
            creator_id="42",
            creator_name="统计作者",
            source_item_id="BV1abc123456",
            content_type="video",
            title="回归分析",
            body_html="",
            body_text="这是视频说明。",
            published_at=None,
            source_url="https://www.bilibili.com/video/BV1abc123456",
            transcript="这里是字幕。",
        )

        document = from_normalized(normalized)

        self.assertEqual("回归分析", document.title)
        self.assertEqual("统计作者", document.author)
        self.assertIn("> 来源平台: bilibili", document.markdown)
        self.assertIn("这是视频说明。", document.markdown)
        self.assertIn("## 字幕", document.markdown)


class MultiPlatformQueueApiTests(unittest.TestCase):
    def test_bilibili_link_is_fetched_and_added_to_the_common_knowledge_queue(self):
        from app import app
        from fastapi.testclient import TestClient

        normalized = NormalizedContent(
            platform="bilibili",
            creator_id="42",
            creator_name="统计作者",
            source_item_id="BV1abc123456",
            content_type="video",
            title="回归分析",
            body_html="",
            body_text="这是视频说明。",
            published_at=None,
            source_url="https://www.bilibili.com/video/BV1abc123456",
        )

        class Adapter:
            def item_ref_from_url(self, url):
                return ItemRef("BV1abc123456", "", url)

            async def health(self):
                return SimpleNamespace(available=True, detail="ready")

            async def fetch_item(self, reference):
                return RawItem(reference.source_item_id, "", reference.source_url, {})

            def normalize_item(self, raw):
                return normalized

        queued_job = SimpleNamespace(
            id="job-1",
            status="pending",
            source_url=normalized.source_url,
            title=normalized.title,
            author=normalized.creator_name,
        )
        queued = SimpleNamespace(queued=True, reason="pending", job=queued_job)

        with (
            patch("routes_ext.platforms.platform_registry.get_adapter", return_value=Adapter()),
            patch("routes_ext.platforms.KnowledgeJobQueue") as queue_type,
            TestClient(app) as client,
        ):
            queue_type.return_value.enqueue.return_value = queued
            response = client.post(
                "/api/ext/platforms/queue",
                json={"url": normalized.source_url},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("bilibili", response.json()["platform"])
        document = queue_type.return_value.enqueue.call_args.args[0]
        self.assertIsInstance(document, MarkdownDocument)
        self.assertEqual("bilibili", queue_type.return_value.enqueue.call_args.kwargs["platform"])

class WeChatLinkAdapterTests(unittest.TestCase):
    def test_health_requires_no_backend_account(self):
        adapter = WeChatAdapter()

        auth = asyncio.run(adapter.authenticate())
        health = asyncio.run(adapter.health())

        self.assertTrue(auth.authenticated)
        self.assertTrue(health.available)
        self.assertIn("link", health.detail.lower())

    def test_canonicalize_url_removes_tracking(self):
        adapter = WeChatAdapter()

        canonical = adapter.canonicalize_url(
            "http://mp.weixin.qq.com/s?scene=21&mid=2&__biz=abc&sn=xyz&idx=1#wechat_redirect"
        )

        self.assertEqual(
            "https://mp.weixin.qq.com/s?__biz=abc&mid=2&idx=1&sn=xyz",
            canonical,
        )

    def test_discovery_methods_are_retired(self):
        adapter = WeChatAdapter()

        with self.assertRaises(PlatformError):
            asyncio.run(adapter.search_creator("publisher"))
        with self.assertRaises(PlatformError):
            asyncio.run(adapter.list_creator_items("publisher"))

    def test_fetch_uses_public_url_without_credentials(self):
        calls = []

        class Parser:
            async def parse(self, url):
                calls.append(url)
                return MarkdownDocument(
                    source_url=url,
                    title="Title",
                    author="Publisher",
                    published_at="2023-11-14",
                    markdown="# Title\n\nBody",
                )

        adapter = WeChatAdapter(parser=Parser())
        reference = ItemRef(
            source_item_id="article-1",
            creator_id="",
            source_url="https://mp.weixin.qq.com/s/example",
        )

        raw = asyncio.run(adapter.fetch_item(reference))
        normalized = adapter.normalize_item(raw)

        self.assertIsInstance(raw, RawItem)
        self.assertEqual(["https://mp.weixin.qq.com/s/example"], calls)
        self.assertEqual("wechat", normalized.platform)
        self.assertEqual("# Title\n\nBody", normalized.body_text)


class PlatformStatusApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = TestClient(app)
        cls.client = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)

    def test_platform_status_and_page_are_available(self):
        payload = self.client.get("/api/ext/platforms").json()
        statuses = {item["key"]: item for item in payload["platforms"]}

        self.assertTrue(statuses["wechat"]["installed"])
        self.assertTrue(statuses["douyin"]["installed"])
        page = self.client.get("/platforms.html")
        self.assertEqual(200, page.status_code)
        self.assertIn("OpenCLI", page.text)
        self.assertIn("微信公众号", page.text)


if __name__ == "__main__":
    unittest.main()
