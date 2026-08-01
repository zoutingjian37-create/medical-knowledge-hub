import asyncio
from unittest.mock import patch
import unittest


PUBLIC_URL = "https://mp.weixin.qq.com/s/example-article"
SOGOU_URL = "https://weixin.sogou.com/link?url=opaque&type=2&token=secret"


class _SearchRunner:
    def __init__(self, resolved_url=PUBLIC_URL):
        self.resolved_url = resolved_url
        self.json_calls = []
        self.text_calls = []
        self.url_reads = 0

    async def run_json(self, *arguments, timeout=60):
        self.json_calls.append((arguments, timeout))
        return [
            {
                "title": "医学研究方法讲解",
                "url": SOGOU_URL,
                "summary": "公开搜索结果",
                "publish_time": "1小时前",
            }
        ]

    async def run_text(self, *arguments, timeout=60):
        self.text_calls.append((arguments, timeout))
        if "get" in arguments and "url" in arguments:
            self.url_reads += 1
            return SOGOU_URL if self.url_reads == 1 else self.resolved_url
        return "ok"


class OpenCLIPublicDiscoveryTests(unittest.TestCase):
    def _type(self):
        from extensions.platforms.wechat.discovery import OpenCLIWeChatDiscoverer

        return OpenCLIWeChatDiscoverer

    def test_search_resolves_sogou_redirect_without_wechat_desktop_ui(self):
        runner = _SearchRunner()
        discoverer = self._type()(
            runner=runner,
            poll_interval=0,
            resolve_timeout=1,
        )

        links = asyncio.run(discoverer.discover(["示例医学公众号"], per_account=1))

        self.assertEqual((PUBLIC_URL,), links)
        self.assertEqual("weixin", runner.json_calls[0][0][0])
        self.assertEqual("search", runner.json_calls[0][0][1])
        text_arguments = [call[0] for call in runner.text_calls]
        self.assertTrue(any("open" in call for call in text_arguments))
        self.assertTrue(any("get" in call and "url" in call for call in text_arguments))
        self.assertTrue(any("close" in call for call in text_arguments))

    def test_unresolved_redirect_fails_fast_and_releases_browser_session(self):
        from extensions.platforms.wechat.discovery import WeChatUIDiscoveryError

        runner = _SearchRunner(resolved_url=SOGOU_URL)
        discoverer = self._type()(
            runner=runner,
            poll_interval=0,
            resolve_timeout=0,
        )

        with self.assertRaisesRegex(WeChatUIDiscoveryError, "resolve"):
            asyncio.run(discoverer.discover(["示例医学公众号"], per_account=1))

        self.assertTrue(any("close" in call[0] for call in runner.text_calls))

    def test_signed_search_redirect_url_keeps_the_fields_required_by_wechat(self):
        from extensions.platforms.wechat.public_link import (
            canonicalize_public_article_url,
        )

        signed = (
            "https://mp.weixin.qq.com/s?src=11&timestamp=1785579762&ver=6878"
            "&signature=abc123&new=1"
        )

        self.assertEqual(signed, canonicalize_public_article_url(signed))

    def test_bare_article_path_is_rejected(self):
        from extensions.platforms.wechat.public_link import (
            canonicalize_public_article_url,
        )

        with self.assertRaises(ValueError):
            canonicalize_public_article_url("https://mp.weixin.qq.com/s")


class WeChatParserRetryTests(unittest.TestCase):
    def test_transient_verification_page_is_retried_once(self):
        from extensions.platforms.wechat.parser import OpenCLIWeChatParser

        class Runner:
            def __init__(self):
                self.calls = 0

            async def run_json(self, *arguments, timeout=60):
                self.calls += 1
                output = arguments[arguments.index("--output") + 1]
                if self.calls == 1:
                    return [{"status": "failed - verification required"}]
                from pathlib import Path

                article = Path(output) / "article.md"
                article.write_text("# 医学研究\n\n正文", encoding="utf-8")
                return [{"title": "医学研究", "author": "示例医学公众号"}]

        runner = Runner()
        parser = OpenCLIWeChatParser(runner=runner, retry_delay=0)

        document = asyncio.run(parser.parse(PUBLIC_URL))

        self.assertEqual(2, runner.calls)
        self.assertEqual("医学研究", document.title)


class WeChatPipelineAccountTests(unittest.TestCase):
    def test_search_candidates_from_another_account_are_not_queued(self):
        from extensions.platforms.wechat.pipeline import WeChatPipeline
        from extensions.processing.documents import MarkdownDocument

        class Discoverer:
            async def discover(self, accounts, per_account=10):
                return (PUBLIC_URL,)

        class Parser:
            async def parse(self, url):
                return MarkdownDocument(
                    source_url=url,
                    title="医学研究",
                    author="另一个公众号",
                    published_at="2026-08-01",
                    markdown="# 医学研究",
                )

        class Queue:
            def enqueue(self, document, platform="wechat"):
                raise AssertionError("account mismatch must not be queued")

        results = asyncio.run(
            WeChatPipeline(Discoverer(), Parser(), Queue()).run(
                ["示例医学公众号"],
                per_account=1,
            )
        )

        self.assertEqual(1, len(results))
        self.assertFalse(results[0].queued)
        self.assertEqual("account_mismatch", results[0].reason)


class WeChatDiscoveryRouteTests(unittest.TestCase):
    def test_public_search_is_the_default_discovery_mode(self):
        from fastapi.testclient import TestClient
        from app import app

        class Discoverer:
            async def discover(self, accounts, per_account=10):
                return (PUBLIC_URL,)

        with (
            patch(
                "routes_ext.platforms.OpenCLIWeChatDiscoverer",
                return_value=Discoverer(),
                create=True,
            ),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/ext/platforms/wechat/discover",
                json={"accounts": ["示例医学公众号"], "per_account": 1},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual({"links": [PUBLIC_URL], "mode": "public"}, response.json())

    def test_desktop_wechat_ui_is_an_explicit_fallback(self):
        from fastapi.testclient import TestClient
        from app import app

        class Discoverer:
            def discover(self, accounts, per_account=10):
                return (PUBLIC_URL,)

        with (
            patch(
                "routes_ext.platforms.WeChatUIDiscoverer",
                return_value=Discoverer(),
            ),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/ext/platforms/wechat/discover",
                json={
                    "accounts": ["示例医学公众号"],
                    "per_account": 1,
                    "mode": "wechat_ui",
                },
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("wechat_ui", response.json()["mode"])

    def test_open_source_page_has_no_personal_subscription_defaults(self):
        from fastapi.testclient import TestClient
        from app import app

        with TestClient(app) as client:
            html = client.get("/wechat-collect.html").text

        self.assertIn("快速公开搜索", html)
        self.assertIn("微信界面补全", html)
        self.assertNotIn("示例医学统计号", html)
        self.assertNotIn("示例公共数据库号", html)
        self.assertNotIn("示例论文分析号", html)


if __name__ == "__main__":
    unittest.main()
