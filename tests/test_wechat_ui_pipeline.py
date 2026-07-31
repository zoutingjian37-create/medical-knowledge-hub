import asyncio
import inspect
import os
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PUBLIC_URL = "https://mp.weixin.qq.com/s/example-article"


def _subprocess_discovery_success(account, limit):
    return [PUBLIC_URL]


def _subprocess_discovery_hangs(account, limit):
    time.sleep(5)
    return []


class _DiscoveryBackend:
    def __init__(self):
        self.calls = []

    def collect_links(self, account, limit):
        self.calls.append((account, limit))
        return [
            PUBLIC_URL + "?scene=21#wechat_redirect",
            PUBLIC_URL,
            "https://example.com/not-wechat",
        ]


class _OpenCLIRunner:
    def __init__(self):
        self.calls = []

    async def run_json(self, *arguments, timeout=60):
        self.calls.append((arguments, timeout))
        output = Path(arguments[arguments.index("--output") + 1])
        output.mkdir(parents=True, exist_ok=True)
        (output / "article.md").write_text(
            "# 回归分析入门\n\n正文内容", encoding="utf-8"
        )
        return [
            {
                "title": "回归分析入门",
                "author": "统计之光医学统计",
                "publish_time": "2026-07-30",
                "saved": str(output / "article.md"),
            }
        ]


class _WeChatParser:
    def __init__(self, document):
        self.document = document
        self.calls = []

    async def parse(self, url):
        self.calls.append(url)
        return self.document


class WeChatUIDiscoveryContractTests(unittest.TestCase):
    def _discoverer_type(self):
        try:
            from extensions.platforms.wechat.discovery import WeChatUIDiscoverer
        except ModuleNotFoundError:
            self.fail("WeChat UI discovery module is missing")
        return WeChatUIDiscoverer

    def test_discovery_outputs_only_unique_public_article_urls(self):
        discoverer_type = self._discoverer_type()
        backend = _DiscoveryBackend()
        discoverer = discoverer_type(backend=backend)

        links = discoverer.discover(["统计之光医学统计"], per_account=5)

        self.assertEqual((PUBLIC_URL,), links)
        self.assertEqual([("统计之光医学统计", 5)], backend.calls)

    def test_discovery_api_has_no_credential_parameters(self):
        discoverer_type = self._discoverer_type()

        parameters = inspect.signature(discoverer_type.discover).parameters

        self.assertNotIn("cookie", parameters)
        self.assertNotIn("token", parameters)
        self.assertNotIn("credential", parameters)

    def test_pyweixin_backend_is_isolated_and_times_out(self):
        try:
            from extensions.platforms.wechat.discovery import (
                PyWeixinLinkBackend,
                WeChatUIDiscoveryError,
            )
        except ModuleNotFoundError:
            self.fail("Isolated pyweixin backend is missing")

        self.assertIn("worker", inspect.signature(PyWeixinLinkBackend).parameters)
        backend = PyWeixinLinkBackend(
            worker=_subprocess_discovery_success,
            timeout=5,
        )
        self.assertEqual([PUBLIC_URL], list(backend.collect_links("account", 1)))

        hanging = PyWeixinLinkBackend(
            worker=_subprocess_discovery_hangs,
            timeout=0.1,
        )
        with self.assertRaisesRegex(WeChatUIDiscoveryError, "timed out"):
            hanging.collect_links("account", 1)


class OpenCLIWeChatParserContractTests(unittest.TestCase):
    def test_default_temporary_downloads_stay_outside_the_repository(self):
        from extensions.platforms.wechat.parser import DEFAULT_TEMP_ROOT

        project = Path(__file__).resolve().parents[1]
        self.assertNotEqual(project, DEFAULT_TEMP_ROOT)
        self.assertNotIn(project, DEFAULT_TEMP_ROOT.parents)
        self.assertTrue(str(DEFAULT_TEMP_ROOT).startswith("D:\\Codex\\cache\\"))

    def _types(self):
        try:
            from extensions.platforms.wechat.parser import OpenCLIWeChatParser
            from extensions.processing.documents import MarkdownDocument
        except ModuleNotFoundError:
            self.fail("Independent OpenCLI WeChat parser is missing")
        return OpenCLIWeChatParser, MarkdownDocument

    def test_parser_passes_only_public_url_to_opencli_and_returns_markdown(self):
        parser_type, document_type = self._types()
        runner = _OpenCLIRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            parser = parser_type(runner=runner, temp_root=Path(temp_dir))

            document = asyncio.run(parser.parse(PUBLIC_URL))

        self.assertIsInstance(document, document_type)
        self.assertEqual("回归分析入门", document.title)
        self.assertIn("正文内容", document.markdown)
        arguments, timeout = runner.calls[0]
        self.assertEqual("weixin", arguments[0])
        self.assertEqual("download", arguments[1])
        self.assertEqual(PUBLIC_URL, arguments[arguments.index("--url") + 1])
        self.assertNotIn("cookie", " ".join(arguments).lower())
        self.assertNotIn("token", " ".join(arguments).lower())
        self.assertEqual(120, timeout)

    def test_parser_rejects_non_wechat_urls_before_starting_opencli(self):
        parser_type, _ = self._types()
        runner = _OpenCLIRunner()
        parser = parser_type(runner=runner)

        with self.assertRaises(ValueError):
            asyncio.run(parser.parse("https://example.com/article"))

        self.assertEqual([], runner.calls)


class WeChatAdapterParserBoundaryTests(unittest.TestCase):
    def test_default_wechat_adapter_uses_the_independent_markdown_parser(self):
        try:
            from extensions.platforms.base import ItemRef
            from extensions.platforms.wechat.adapter import WeChatAdapter
            from extensions.processing.documents import MarkdownDocument
        except ModuleNotFoundError:
            self.fail("WeChat adapter parser integration is missing")
        document = MarkdownDocument(
            source_url=PUBLIC_URL,
            title="回归分析入门",
            author="统计之光医学统计",
            published_at="2026-07-30",
            markdown="# 回归分析入门\n\n正文内容",
        )
        parser = _WeChatParser(document)
        self.assertIn("parser", inspect.signature(WeChatAdapter).parameters)
        adapter = WeChatAdapter(parser=parser)

        raw = asyncio.run(
            adapter.fetch_item(
                ItemRef(
                    source_item_id="example-article",
                    creator_id="",
                    source_url=PUBLIC_URL,
                )
            )
        )
        normalized = adapter.normalize_item(raw)

        self.assertEqual([PUBLIC_URL], parser.calls)
        self.assertEqual("回归分析入门", normalized.title)
        self.assertEqual("正文内容", normalized.body_text.splitlines()[-1])
        self.assertEqual(PUBLIC_URL, normalized.source_url)


class ObsidianArchiveContractTests(unittest.TestCase):
    def _types(self):
        try:
            from extensions.processing.archive import ObsidianArchiver
            from extensions.processing.documents import MarkdownDocument
        except ModuleNotFoundError:
            self.fail("Independent Obsidian archive module is missing")
        return ObsidianArchiver, MarkdownDocument

    def test_archive_filters_ads_and_deduplicates_by_public_url(self):
        archiver_type, document_type = self._types()
        normal = document_type(
            source_url=PUBLIC_URL,
            title="回归分析入门",
            author="统计之光医学统计",
            published_at="2026-07-30",
            markdown="# 回归分析入门\n\n正文内容",
        )
        advert = document_type(
            source_url="https://mp.weixin.qq.com/s/advert",
            title="课程优惠报名通知",
            author="统计之光医学统计",
            published_at="2026-07-30",
            markdown="# 课程优惠报名通知\n\n立即购买",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            archiver = archiver_type(Path(temp_dir))
            first = archiver.archive(normal)
            duplicate = archiver.archive(normal)
            filtered = archiver.archive(advert)

            self.assertTrue(first.saved)
            self.assertTrue(first.path.is_file())
            self.assertEqual("回归分析入门.md", first.path.name)
            self.assertIn(PUBLIC_URL, first.path.read_text("utf-8"))
            self.assertFalse(duplicate.saved)
            self.assertEqual("duplicate", duplicate.reason)
            self.assertFalse(filtered.saved)
            self.assertEqual("advertisement", filtered.reason)
            self.assertEqual(1, len(list(Path(temp_dir).rglob("*.md"))))

    def test_archive_uses_numbered_suffix_only_for_a_real_title_collision(self):
        archiver_type, document_type = self._types()
        first_document = document_type(
            source_url="https://mp.weixin.qq.com/s/first",
            title="直线相关还是秩相关？ | 30天学会医学统计学公益课(D15)",
            author="医学论文与统计分析",
            published_at="2026-07-30",
            markdown="# 第一篇\n\n正文一",
        )
        second_document = document_type(
            source_url="https://mp.weixin.qq.com/s/second",
            title="直线相关还是秩相关？ | 30天学会医学统计学公益课(D15)",
            author="医学论文与统计分析",
            published_at="2026-07-30",
            markdown="# 第二篇\n\n正文二",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            archiver = archiver_type(Path(temp_dir))
            first = archiver.archive(first_document)
            second = archiver.archive(second_document)

            self.assertEqual(
                "直线相关还是秩相关？ - 30天学会医学统计学公益课(D15).md",
                first.path.name,
            )
            self.assertEqual(
                "直线相关还是秩相关？ - 30天学会医学统计学公益课(D15) (2).md",
                second.path.name,
            )

    def test_archive_removes_embedded_course_and_tool_promotions(self):
        archiver_type, document_type = self._types()
        document = document_type(
            source_url="https://mp.weixin.qq.com/s/correlation",
            title="直线相关还是秩相关？",
            author="医学论文与统计分析",
            published_at="2026-07-30",
            markdown=(
                "# 直线相关还是秩相关？\n\n"
                "> 公众号: 医学论文与统计分析\n\n---\n\n"
                "![头图](https://example.test/ad.png)\n\n"
                "朋友们，30天学会统计学公益课上线了！\n\n"
                "发送“报名”到本公众号，加入微信学习群吧。\n\n"
                "本课程是浙江中医药大学医学统计学教研室的公益、免费公开视频课！"
                "不是骗人入坑收费的广告。本课程公益网络视频课定期开课，欢迎您参与学习。\n\n"
                "本课程的课件如下：绝对精品教程公开赠送。\n\n"
                "无论实验性研究还是观察性研究，都少不了相关分析的身影。"
                "相关分析用于描述两个变量关联的方向和强度。\n\n"
                "## 方法选择\n\n"
                "Pearson相关关注线性关系，Spearman相关关注单调关系。\n\n"
                "除了SPSS，数据分析可使用郑老师研制的工具。\n\n"
                "www.medsta.cn\n\n"
                "## 相关分析方法小结\n\n"
                "应先查看散点图，并检查异常值。\n\n"
                "本文更多疑问，请发送关键词4020到本公众号。\n\n"
                "关于郑老师团队及公众号：课程训练营详情。\n"
            ),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = archiver_type(Path(temp_dir)).archive(document)
            saved = result.path.read_text("utf-8")

            self.assertIn("无论实验性研究还是观察性研究", saved)
            self.assertIn("Pearson相关关注线性关系", saved)
            self.assertIn("应先查看散点图", saved)
            self.assertNotIn("公益课上线", saved)
            self.assertNotIn("不是广告", saved)
            self.assertNotIn("课件如下", saved)
            self.assertNotIn("发送“报名”", saved)
            self.assertNotIn("medsta.cn", saved)
            self.assertNotIn("课程训练营详情", saved)


class WeChatDiscoveryApiTests(unittest.TestCase):
    def test_nontechnical_wechat_collection_page_is_available(self):
        try:
            from fastapi.testclient import TestClient
            from app import app
        except (ImportError, ModuleNotFoundError):
            self.fail("WeChat collection page is missing")

        with TestClient(app) as client:
            response = client.get("/wechat-collect.html")

        self.assertEqual(200, response.status_code)
        self.assertIn("统计之光医学统计", response.text)
        self.assertIn("/api/ext/platforms/wechat/discover", response.text)
        self.assertIn("/api/ext/platforms/wechat/collect", response.text)

    def test_api_returns_ui_discovery_links_without_private_metadata(self):
        try:
            from fastapi.testclient import TestClient
            from app import app
        except (ImportError, ModuleNotFoundError):
            self.fail("WeChat UI discovery API is missing")

        class Discoverer:
            def discover(self, accounts, per_account=10):
                self.accounts = accounts
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
                json={"accounts": ["统计之光医学统计"], "per_account": 3},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual({"links": [PUBLIC_URL]}, response.json())
        serialized = response.text.lower()
        self.assertNotIn("cookie", serialized)
        self.assertNotIn("token", serialized)
        self.assertNotIn("wxid", serialized)

    def test_collect_api_returns_pending_jobs_without_requiring_vault(self):
        try:
            from extensions.processing.job_queue import QueueResult
            from extensions.processing.job_store import KnowledgeJob
            from fastapi.testclient import TestClient
            from app import app
        except (ImportError, ModuleNotFoundError):
            self.fail("WeChat collection API is missing")

        class Pipeline:
            async def run(self, accounts, per_account=10):
                return (
                    QueueResult(
                        queued=True,
                        reason="pending",
                        job=KnowledgeJob(
                            id="job-1",
                            status="pending",
                            source_url=PUBLIC_URL,
                            title="医学文章",
                            author="统计之光医学统计",
                            published_at="2026-07-30",
                            platform="wechat",
                            cache_path=r"D:\Codex\cache\medical-knowledge-hub\job-1.md",
                            created_at="2026-07-30T00:00:00+00:00",
                            updated_at="2026-07-30T00:00:00+00:00",
                        ),
                    ),
                )

        with (
            patch.dict(os.environ, {}, clear=False),
            patch(
                "routes_ext.platforms.WeChatPipeline",
                return_value=Pipeline(),
                create=True,
            ),
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/ext/platforms/wechat/collect",
                json={"accounts": ["统计之光医学统计"], "per_account": 3},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("pending", response.json()["results"][0]["status"])
        self.assertEqual("job-1", response.json()["results"][0]["job_id"])
        self.assertNotIn("cookie", response.text.lower())
        self.assertNotIn("cache_path", response.text.lower())

    def test_manual_public_link_is_queued_for_distillation(self):
        from extensions.processing.documents import MarkdownDocument
        from fastapi.testclient import TestClient
        from app import app

        class Parser:
            async def parse(self, url):
                return MarkdownDocument(
                    source_url=url,
                    title="高分医学文献讲解",
                    author="医学论文与统计分析",
                    published_at="2026-07-30",
                    markdown="# 高分医学文献讲解\n\n有价值的研究正文。",
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.dict(
                    os.environ,
                    {
                        "CONTENT_HUB_CACHE_DIR": str(root / "cache"),
                        "CONTENT_HUB_STATE_DIR": str(root / "state"),
                    },
                ),
                patch(
                    "routes_ext.platforms.OpenCLIWeChatParser",
                    return_value=Parser(),
                ),
                TestClient(app) as client,
            ):
                response = client.post(
                    "/api/ext/platforms/wechat/queue",
                    json={"url": PUBLIC_URL},
                )

        self.assertEqual(200, response.status_code)
        self.assertEqual("pending", response.json()["status"])
        self.assertEqual(PUBLIC_URL, response.json()["source_url"])
        self.assertNotIn("cache_path", response.text)


class WeChatPipelineTests(unittest.TestCase):
    def test_pipeline_creates_pending_jobs_instead_of_archiving_raw_articles(self):
        try:
            from extensions.platforms.wechat.pipeline import WeChatPipeline
            from extensions.processing.documents import MarkdownDocument
            from extensions.processing.job_queue import KnowledgeJobQueue
            from extensions.processing.job_store import KnowledgeJobStore
            from extensions.processing.source_cache import SourceCache
        except ModuleNotFoundError:
            self.fail("WeChat three-layer pipeline is missing")

        class Discoverer:
            def discover(self, accounts, per_account=10):
                return (PUBLIC_URL, "https://mp.weixin.qq.com/s/advert")

        class Parser:
            async def parse(self, url):
                title = "课程优惠报名通知" if url.endswith("advert") else "回归分析入门"
                return MarkdownDocument(
                    source_url=url,
                    title=title,
                    author="统计之光医学统计",
                    published_at="2026-07-30",
                    markdown=f"# {title}\n\n正文",
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pipeline = WeChatPipeline(
                discoverer=Discoverer(),
                parser=Parser(),
                queue=KnowledgeJobQueue(
                    cache=SourceCache(root / "cache"),
                    store=KnowledgeJobStore(root / "state"),
                ),
            )
            results = asyncio.run(
                pipeline.run(["统计之光医学统计"], per_account=2)
            )
            raw_vault_notes = list((root / "vault").rglob("*.md"))

        self.assertEqual(2, len(results))
        self.assertTrue(results[0].queued)
        self.assertEqual("pending", results[0].job.status)
        self.assertFalse(results[1].queued)
        self.assertEqual("advertisement", results[1].reason)
        self.assertEqual([], raw_vault_notes)


if __name__ == "__main__":
    unittest.main()
