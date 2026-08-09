import asyncio
from datetime import date, datetime
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from extensions.platforms.wechat.vision import SHANGHAI_TZ


class _RunStore:
    def create(self, subscription_id):
        return SimpleNamespace(id="run-1", subscription_id=subscription_id)

    def update(self, run_id, **changes):
        return SimpleNamespace(id=run_id, **changes)


class _SubscriptionStore:
    def __init__(self):
        self.updated = []

    def update(self, subscription_id, **changes):
        self.updated.append((subscription_id, changes))


class WeChatSubscriptionCursorTests(unittest.TestCase):
    def test_daily_run_rechecks_last_success_date_and_advances_to_today(self):
        from extensions.subscriptions.runner import WeChatSubscriptionPipeline

        calls = []

        class Pipeline:
            def __init__(self, *args):
                pass

            async def run(self, accounts, per_account=10, date_from=None, date_to=None):
                calls.append((accounts, per_account, date_from, date_to))
                return ()

        subscriptions = _SubscriptionStore()
        pipeline = WeChatSubscriptionPipeline(
            discoverer=object(),
            parser=object(),
            queue=object(),
            compiler=object(),
            run_store=_RunStore(),
            subscription_store=subscriptions,
            now_provider=lambda: datetime(2026, 8, 1, 9, 0, tzinfo=SHANGHAI_TZ),
        )
        subscription = SimpleNamespace(
            id="wechat-1",
            source="示例医学公众号",
            name="示例医学公众号",
            daily_limit=5,
            last_successful_date="2026-07-31",
        )

        with patch("extensions.platforms.wechat.pipeline.WeChatPipeline", Pipeline):
            result = asyncio.run(pipeline.run(subscription))

        self.assertEqual(
            [(["示例医学公众号"], 5, date(2026, 7, 31), date(2026, 8, 1))],
            calls,
        )
        self.assertEqual(
            [("wechat-1", {"last_successful_date": "2026-08-01"})],
            subscriptions.updated,
        )
        self.assertEqual("completed", result.status)

    def test_manual_subscription_run_uses_today_only_instead_of_the_cursor(self):
        from extensions.subscriptions.runner import WeChatSubscriptionPipeline

        calls = []

        class Pipeline:
            def __init__(self, *args):
                pass

            async def run(self, accounts, per_account=10, date_from=None, date_to=None):
                calls.append((accounts, per_account, date_from, date_to))
                return ()

        pipeline = WeChatSubscriptionPipeline(
            discoverer=object(),
            parser=object(),
            queue=object(),
            compiler=object(),
            run_store=_RunStore(),
            subscription_store=_SubscriptionStore(),
            now_provider=lambda: datetime(2026, 8, 2, 9, 0, tzinfo=SHANGHAI_TZ),
        )
        subscription = SimpleNamespace(
            id="wechat-1",
            source="示例医学公众号",
            name="示例医学公众号",
            daily_limit=5,
            last_successful_date="2026-07-20",
        )

        with patch("extensions.platforms.wechat.pipeline.WeChatPipeline", Pipeline):
            result = asyncio.run(pipeline.run_manual(subscription))

        self.assertEqual(
            [(["示例医学公众号"], 5, date(2026, 8, 2), date(2026, 8, 2))],
            calls,
        )
        self.assertEqual("completed", result.status)

    def test_failed_step_is_kept_in_the_subscription_run(self):
        from extensions.platforms.wechat.discovery import WeChatDiscoveryStatus
        from extensions.subscriptions.runner import WeChatSubscriptionPipeline

        class Discoverer:
            last_status = WeChatDiscoveryStatus(
                complete=False,
                warning="文章列表未完成",
                failed_step="article_list",
                retry_from="account_search",
                progress_kept=True,
            )

        class Pipeline:
            def __init__(self, *args):
                pass

            async def run(self, accounts, per_account=10, date_from=None, date_to=None):
                return (
                    SimpleNamespace(
                        queued=False,
                        job=None,
                        reason="discovery_failed",
                        error="文章列表未完成",
                        failed_step="article_list",
                        retry_from="account_search",
                        progress_kept=True,
                    ),
                )

        pipeline = WeChatSubscriptionPipeline(
            discoverer=Discoverer(),
            parser=object(),
            queue=object(),
            compiler=object(),
            run_store=_RunStore(),
            subscription_store=_SubscriptionStore(),
            now_provider=lambda: datetime(2026, 8, 2, 9, 0, tzinfo=SHANGHAI_TZ),
        )
        subscription = SimpleNamespace(
            id="wechat-1",
            source="示例医学公众号",
            name="示例医学公众号",
            daily_limit=5,
            last_successful_date="",
        )

        with patch("extensions.platforms.wechat.pipeline.WeChatPipeline", Pipeline):
            result = asyncio.run(pipeline.run_manual(subscription))

        self.assertEqual("failed", result.status)
        self.assertEqual("article_list", result.failed_step)
        self.assertEqual("account_search", result.retry_from)
        self.assertTrue(result.progress_kept)
        self.assertEqual(0, result.discovered)
        self.assertEqual(0, result.filtered)


if __name__ == "__main__":
    unittest.main()
