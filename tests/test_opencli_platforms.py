import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from extensions.platforms.base import ItemRef, PlatformError, RawItem
from extensions.platforms.opencli.adapter import OpenCLIAdapter
from extensions.platforms.opencli.runner import OpenCLIRunner, OpenCLIStatus


class _FakeRunner:
    def __init__(self, responses=None, *, bridge_connected=True):
        self.responses = responses or {}
        self.bridge_connected = bridge_connected
        self.calls = []

    async def status(self):
        return OpenCLIStatus(
            installed=True,
            bridge_connected=self.bridge_connected,
            version="1.8.6",
            detail="ready" if self.bridge_connected else "browser bridge disconnected",
        )

    async def run_json(self, *arguments, timeout=60):
        self.calls.append(("json", arguments, timeout))
        return self.responses.get(arguments, [])

    async def run_text(self, *arguments, timeout=60):
        self.calls.append(("text", arguments, timeout))
        return self.responses.get(arguments, "")


class OpenCLIAdapterTests(unittest.TestCase):
    def test_runner_honors_documented_runtime_environment_name(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"OPENCLI_RUNTIME_DIR": directory},
            clear=False,
        ):
            runner = OpenCLIRunner()

        self.assertEqual(Path(directory), runner.runtime_dir)

    def test_all_four_platforms_use_the_same_adapter_class(self):
        adapters = [
            OpenCLIAdapter(key, runner=_FakeRunner())
            for key in ("zhihu", "bilibili", "xiaohongshu", "douyin")
        ]

        self.assertEqual(
            ["zhihu", "bilibili", "xiaohongshu", "douyin"],
            [adapter.platform_key for adapter in adapters],
        )

    def test_health_distinguishes_installed_engine_from_browser_connection(self):
        ready = OpenCLIAdapter("zhihu", runner=_FakeRunner())
        disconnected = OpenCLIAdapter(
            "zhihu", runner=_FakeRunner(bridge_connected=False)
        )

        ready_health = asyncio.run(ready.health())
        disconnected_health = asyncio.run(disconnected.health())

        self.assertTrue(ready_health.available)
        self.assertFalse(disconnected_health.available)
        self.assertIn("browser", disconnected_health.detail.lower())

    def test_bilibili_creator_search_and_listing_reuse_opencli_commands(self):
        runner = _FakeRunner(
            {
                (
                    "bilibili",
                    "search",
                    "医学统计",
                    "--type",
                    "user",
                    "--limit",
                    "20",
                ): [
                    {
                        "title": "统计之光",
                        "author": "统计之光",
                        "url": "https://space.bilibili.com/123456",
                    }
                ],
                (
                    "bilibili",
                    "user-videos",
                    "123456",
                    "--page",
                    "2",
                    "--limit",
                    "20",
                ): [
                    {
                        "title": "回归分析",
                        "url": "https://www.bilibili.com/video/BV1abc123456",
                        "date": "2026-07-01",
                    }
                ],
            }
        )
        adapter = OpenCLIAdapter("bilibili", runner=runner)

        creators = asyncio.run(adapter.search_creator("医学统计"))
        page = asyncio.run(
            adapter.list_creator_items(
                "123456", cursor=type("CursorLike", (), {"value": {"page": 2}})()
            )
        )

        self.assertEqual("123456", creators[0].creator_id)
        self.assertEqual("BV1abc123456", page.items[0].source_item_id)
        self.assertEqual(3, page.next_cursor.value["page"])

    def test_platform_urls_are_validated_and_canonicalized(self):
        cases = [
            (
                "zhihu",
                "https://www.zhihu.com/question/1/answer/123?utm_source=test#x",
                "answer:123",
                "https://www.zhihu.com/question/1/answer/123",
            ),
            (
                "bilibili",
                "https://www.bilibili.com/video/BV1abc123456/?spm_id_from=333",
                "BV1abc123456",
                "https://www.bilibili.com/video/BV1abc123456",
            ),
            (
                "xiaohongshu",
                "https://www.xiaohongshu.com/explore/abc123?xsec_token=keep&utm_source=x",
                "abc123",
                "https://www.xiaohongshu.com/explore/abc123?xsec_token=keep",
            ),
            (
                "douyin",
                "https://www.douyin.com/video/7654321?previous_page=web_code_link",
                "7654321",
                "https://www.douyin.com/video/7654321",
            ),
        ]

        for platform, url, source_id, canonical in cases:
            with self.subTest(platform=platform):
                adapter = OpenCLIAdapter(platform, runner=_FakeRunner())
                reference = adapter.item_ref_from_url(url)
                self.assertEqual(source_id, reference.source_item_id)
                self.assertEqual(canonical, reference.source_url)

        with self.assertRaises(ValueError):
            OpenCLIAdapter("zhihu", runner=_FakeRunner()).item_ref_from_url(
                "https://example.com/question/1/answer/2"
            )

    def test_bilibili_detail_is_normalized_to_the_common_content_model(self):
        detail = (
            "bilibili",
            "video",
            "BV1abc123456",
        )
        runner = _FakeRunner(
            {
                detail: [
                    {"field": "title", "value": "回归分析"},
                    {"field": "author", "value": "统计之光"},
                    {"field": "description", "value": "用实例讲解回归模型"},
                    {"field": "cover", "value": "https://i0.hdslb.com/cover.jpg"},
                ]
            }
        )
        adapter = OpenCLIAdapter("bilibili", runner=runner)
        reference = ItemRef(
            source_item_id="BV1abc123456",
            creator_id="123456",
            source_url="https://www.bilibili.com/video/BV1abc123456",
        )

        raw = asyncio.run(adapter.fetch_item(reference))
        normalized = adapter.normalize_item(raw)

        self.assertEqual("video", normalized.content_type)
        self.assertEqual("回归分析", normalized.title)
        self.assertEqual("统计之光", normalized.creator_name)
        self.assertIn("回归模型", normalized.body_text)
        self.assertEqual(["https://i0.hdslb.com/cover.jpg"], normalized.images)

    def test_douyin_single_url_uses_opencli_web_reader_without_copying_a_crawler(self):
        url = "https://www.douyin.com/video/7654321"
        runner = _FakeRunner(
            {
                (
                    "web",
                    "read",
                    "--url",
                    url,
                    "--stdout",
                    "true",
                    "--download-images",
                    "false",
                ): "# Logistic 回归\n\n作者：统计之光\n\n这是视频说明。",
            }
        )
        adapter = OpenCLIAdapter("douyin", runner=runner)

        raw = asyncio.run(adapter.fetch_item(adapter.item_ref_from_url(url)))
        normalized = adapter.normalize_item(raw)

        self.assertEqual("Logistic 回归", normalized.title)
        self.assertIn("视频说明", normalized.body_text)
        self.assertEqual("text", runner.calls[0][0])

    def test_douyin_web_page_is_compacted_and_extracts_creator(self):
        adapter = OpenCLIAdapter("douyin", runner=_FakeRunner())
        raw = RawItem(
            source_item_id="7654321",
            creator_id="",
            source_url="https://www.douyin.com/video/7654321",
            data={
                "markdown": (
                    "# 医学统计课程介绍 #医学统计 #R语言\n"
                    "> 原文链接: https://www.douyin.com/video/7654321\n\n"
                    "---\n\n"
                    "开启读屏标签\n\n推荐\n\n"
                    "发布时间：2026-06-01 20:41\n\n"
                    "[![左岸同学（统计之光）](https://example.com/avatar.jpg)]"
                    "(https://www.douyin.com/user/example)\n\n"
                    "## 推荐视频\n其他页面内容"
                ),
                "list_metadata": {},
            },
        )

        normalized = adapter.normalize_item(raw)

        self.assertEqual("左岸同学（统计之光）", normalized.creator_name)
        self.assertEqual("2026-06-01", normalized.published_at.date().isoformat())
        self.assertIn("医学统计课程介绍", normalized.body_text)
        self.assertNotIn("开启读屏标签", normalized.body_text)
        self.assertNotIn("推荐视频", normalized.body_text)
        self.assertLess(len(normalized.body_text), 300)

    def test_xiaohongshu_shell_title_falls_back_to_real_content(self):
        adapter = OpenCLIAdapter("xiaohongshu", runner=_FakeRunner())
        raw = RawItem(
            source_item_id="note-1",
            creator_id="creator-1",
            source_url="https://www.xiaohongshu.com/explore/note-1?xsec_token=keep",
            data={
                "payload": [
                    {"field": "title", "value": "温馨提示"},
                    {"field": "author", "value": "测试作者"},
                    {
                        "field": "content",
                        "value": "土区又复活啦#gpt #chatgpt #程序员日常",
                    },
                ],
                "list_metadata": {},
            },
        )

        normalized = adapter.normalize_item(raw)

        self.assertEqual("土区又复活啦", normalized.title)
        self.assertEqual("测试作者", normalized.creator_name)

    def test_empty_xiaohongshu_login_page_is_rejected(self):
        adapter = OpenCLIAdapter("xiaohongshu", runner=_FakeRunner())
        raw = RawItem(
            source_item_id="note-2",
            creator_id="",
            source_url="https://www.xiaohongshu.com/explore/note-2?xsec_token=keep",
            data={
                "payload": [
                    {"field": "title", "value": "手机号登录"},
                    {"field": "content", "value": "登录后查看内容"},
                ],
                "list_metadata": {},
            },
        )

        with self.assertRaisesRegex(PlatformError, "登录或验证"):
            adapter.normalize_item(raw)


if __name__ == "__main__":
    unittest.main()
