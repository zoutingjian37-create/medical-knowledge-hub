import asyncio
from datetime import date
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
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
    def test_discovery_failure_returns_structured_failed_step(self):
        from fastapi.testclient import TestClient
        from app import app
        from extensions.platforms.wechat.discovery import WeChatDiscoveryError

        class Discoverer:
            def discover(self, accounts, per_account=10, date_from=None, date_to=None):
                raise WeChatDiscoveryError(
                    "复制链接菜单未出现",
                    step="copy_link",
                    retry_from="article_list",
                    progress_kept=True,
                )

        with (
            patch("routes_ext.platforms.WeChatUIDiscoverer", return_value=Discoverer()),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/ext/platforms/wechat/discover",
                json={"accounts": ["示例公众号"], "per_account": 1},
            )

        self.assertEqual(502, response.status_code)
        self.assertEqual(
            {
                "message": "复制链接菜单未出现",
                "failed_step": "copy_link",
                "retry_from": "article_list",
                "progress_kept": True,
            },
            response.json()["detail"],
        )

    def test_visual_desktop_is_the_default_discovery_mode(self):
        from fastapi.testclient import TestClient
        from app import app

        class Discoverer:
            def discover(self, accounts, per_account=10, date_from=None, date_to=None):
                return (PUBLIC_URL,)

        with (
            patch(
                "routes_ext.platforms.WeChatUIDiscoverer",
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
        self.assertEqual(
            {"links": [PUBLIC_URL], "source": "desktop_wechat"},
            response.json(),
        )

    def test_explicit_date_range_is_forwarded_to_desktop_discovery(self):
        from fastapi.testclient import TestClient
        from app import app

        class Discoverer:
            def discover(self, accounts, per_account=10, date_from=None, date_to=None):
                self.date_from = date_from
                self.date_to = date_to
                return (PUBLIC_URL,)

        discoverer = Discoverer()

        with (
            patch(
                "routes_ext.platforms.WeChatUIDiscoverer",
                return_value=discoverer,
            ),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/ext/platforms/wechat/discover",
                json={
                    "accounts": ["示例医学公众号"],
                    "per_account": 1,
                    "date_from": "2026-07-30",
                    "date_to": "2026-07-31",
                },
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("desktop_wechat", response.json()["source"])
        self.assertEqual("2026-07-30", discoverer.date_from.isoformat())
        self.assertEqual("2026-07-31", discoverer.date_to.isoformat())

    def test_partial_checkpoint_result_is_not_reported_as_complete(self):
        from fastapi.testclient import TestClient
        from app import app

        class Discoverer:
            last_status = SimpleNamespace(
                complete=False,
                attempts=3,
                incomplete_accounts=("示例医学公众号",),
                resume_dates={"示例医学公众号": "2026-07-23"},
                warning="微信界面连续 3 次未恢复；已保存成功链接，可从检查点继续。",
            )

            def discover(self, accounts, per_account=10, date_from=None, date_to=None):
                return (PUBLIC_URL,)

        with (
            patch("routes_ext.platforms.WeChatUIDiscoverer", return_value=Discoverer()),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/ext/platforms/wechat/discover",
                json={"accounts": ["示例医学公众号"], "per_account": 5},
            )

        self.assertEqual(206, response.status_code)
        self.assertFalse(response.json()["complete"])
        self.assertEqual(
            {"示例医学公众号": "2026-07-23"},
            response.json()["resume_dates"],
        )
        self.assertEqual([PUBLIC_URL], response.json()["links"])

    def test_collect_aggregates_failed_accounts_even_if_last_status_is_complete(self):
        from fastapi.testclient import TestClient
        from app import app
        from extensions.processing.job_queue import QueueResult

        async def run_pipeline(*args, **kwargs):
            return (
                QueueResult(
                    False,
                    "discovery_failed",
                    None,
                    account="失败公众号",
                    failed_step="article_list",
                    retry_from="article_list",
                    progress_kept=True,
                    error="文章列表被遮挡",
                ),
                QueueResult(False, "duplicate", None, account="成功公众号"),
            )

        discoverer = SimpleNamespace(
            last_status=SimpleNamespace(complete=True, attempts=1)
        )
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch.dict(
                os.environ,
                {
                    "CONTENT_HUB_CACHE_DIR": str(Path(temp_dir) / "cache"),
                    "CONTENT_HUB_STATE_DIR": str(Path(temp_dir) / "state"),
                },
            ),
            patch("routes_ext.platforms.WeChatUIDiscoverer", return_value=discoverer),
            patch("routes_ext.platforms.WeChatPipeline.run", new=run_pipeline),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/ext/platforms/wechat/collect",
                json={"accounts": ["失败公众号", "成功公众号"], "per_account": 5},
            )

        self.assertEqual(206, response.status_code)
        self.assertFalse(response.json()["complete"])
        self.assertEqual(["失败公众号"], response.json()["incomplete_accounts"])
        self.assertEqual("article_list", response.json()["failed_step"])
        self.assertTrue(response.json()["progress_kept"])
        self.assertEqual("失败公众号", response.json()["results"][0]["account"])

    def test_open_source_page_has_no_personal_subscription_defaults(self):
        from fastapi.testclient import TestClient
        from app import app

        with TestClient(app) as client:
            html = client.get("/wechat-collect.html").text

        self.assertIn("输入公众号名称和日期范围", html)
        self.assertIn("自动重试", html)
        self.assertIn("data.complete === false", html)
        self.assertNotIn("mode:", html)
        self.assertNotIn("示例医学统计号", html)
        self.assertNotIn("示例公共数据库号", html)
        self.assertNotIn("示例论文分析号", html)


class WeChatCheckpointResumeTests(unittest.TestCase):
    def _marker(self, account, published, url):
        from extensions.platforms.wechat.vision import article_dedup_marker

        return article_dedup_marker(account, published, url)

    def test_transient_failure_resumes_from_oldest_checkpoint_date(self):
        from extensions.platforms.wechat.desktop_vision import WeChatDiscoveryIndex
        from extensions.platforms.wechat.discovery import WeChatUIDiscoverer

        account = "示例医学公众号"
        second = "https://mp.weixin.qq.com/s/second-article"
        third = "https://mp.weixin.qq.com/s/third-article"

        with tempfile.TemporaryDirectory() as temp_dir:
            index = WeChatDiscoveryIndex(Path(temp_dir) / "wechat-index.json")

            class Backend:
                def __init__(self):
                    self.index = index
                    self.calls = []

                def collect_links(
                    self,
                    requested_account,
                    limit,
                    *,
                    date_from=None,
                    date_to=None,
                    exclude_urls=(),
                ):
                    self.calls.append((date_from, date_to, tuple(exclude_urls), limit))
                    if len(self.calls) == 1:
                        index.add(self_marker(account, date(2026, 8, 2), PUBLIC_URL))
                        index.add(self_marker(account, date(2026, 8, 1), second))
                        raise RuntimeError("temporary WeChat repaint timeout")
                    index.add(self_marker(account, date(2026, 7, 31), third))
                    return [third]

            self_marker = self._marker
            backend = Backend()
            discoverer = WeChatUIDiscoverer(backend=backend, max_attempts=2)

            links = discoverer.discover(
                [account],
                per_account=10,
                date_from=date(2026, 7, 31),
                date_to=date(2026, 8, 2),
            )

        self.assertEqual((PUBLIC_URL, second, third), links)
        self.assertEqual(date(2026, 8, 1), backend.calls[1][1])
        self.assertEqual((PUBLIC_URL, second), backend.calls[1][2])
        self.assertTrue(discoverer.last_status.complete)
        self.assertEqual(2, discoverer.last_status.attempts)

    def test_resume_includes_checkpoint_day_without_counting_existing_link(self):
        from extensions.platforms.wechat.desktop_vision import WeChatDiscoveryIndex
        from extensions.platforms.wechat.discovery import WeChatUIDiscoverer

        account = "示例医学公众号"
        same_day_second = "https://mp.weixin.qq.com/s/same-day-second"

        with tempfile.TemporaryDirectory() as temp_dir:
            index = WeChatDiscoveryIndex(Path(temp_dir) / "wechat-index.json")

            class Backend:
                def __init__(self):
                    self.index = index
                    self.calls = 0

                def collect_links(self, requested_account, limit, **options):
                    self.calls += 1
                    if self.calls == 1:
                        index.add(self_marker(account, date(2026, 8, 1), PUBLIC_URL))
                        raise RuntimeError("article tab repainted")
                    self.assert_resume(options)
                    return [same_day_second]

                def assert_resume(self, options):
                    if options["date_to"] != date(2026, 8, 1):
                        raise AssertionError("resume must include the checkpoint day")
                    if PUBLIC_URL not in options["exclude_urls"]:
                        raise AssertionError("checkpoint link must not consume the limit")

            self_marker = self._marker
            backend = Backend()
            discoverer = WeChatUIDiscoverer(backend=backend, max_attempts=2)

            links = discoverer.discover(
                [account],
                per_account=2,
                date_from=date(2026, 8, 1),
                date_to=date(2026, 8, 1),
            )

        self.assertEqual((PUBLIC_URL, same_day_second), links)

    def test_retry_exhaustion_returns_partial_links_with_explicit_status(self):
        from extensions.platforms.wechat.desktop_vision import WeChatDiscoveryIndex
        from extensions.platforms.wechat.discovery import WeChatUIDiscoverer

        account = "示例医学公众号"
        with tempfile.TemporaryDirectory() as temp_dir:
            index = WeChatDiscoveryIndex(Path(temp_dir) / "wechat-index.json")

            class Backend:
                def __init__(self):
                    self.index = index
                    self.calls = 0

                def collect_links(self, requested_account, limit, **options):
                    self.calls += 1
                    if self.calls == 1:
                        index.add(self_marker(account, date(2026, 8, 1), PUBLIC_URL))
                    raise RuntimeError("WeChat UI state did not become ready")

            self_marker = self._marker
            discoverer = WeChatUIDiscoverer(backend=Backend(), max_attempts=2)

            links = discoverer.discover(
                [account],
                per_account=5,
                date_from=date(2026, 7, 1),
                date_to=date(2026, 8, 2),
            )

        self.assertEqual((PUBLIC_URL,), links)
        self.assertFalse(discoverer.last_status.complete)
        self.assertEqual((account,), discoverer.last_status.incomplete_accounts)
        self.assertEqual("2026-08-01", discoverer.last_status.resume_dates[account])
        self.assertIn("2", discoverer.last_status.warning)


if __name__ == "__main__":
    unittest.main()
