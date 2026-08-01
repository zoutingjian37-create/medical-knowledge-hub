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


if __name__ == "__main__":
    unittest.main()
