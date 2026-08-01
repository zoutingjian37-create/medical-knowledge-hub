import asyncio
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


class AutomationDueTests(unittest.TestCase):
    def test_disabled_automation_never_runs_but_manual_run_is_allowed(self):
        from extensions.subscriptions.automation import AutomationService
        from extensions.subscriptions.store import SubscriptionStore

        with TemporaryDirectory() as directory:
            store = SubscriptionStore(Path(directory))
            subscription = store.create(
                kind="feed", name="Example", source="https://example.org/rss"
            )
            service = AutomationService(store=store, runner=None)

            self.assertFalse(service.is_due(datetime(2026, 8, 1, 9, 0)))
            self.assertTrue(service.can_run_manually(subscription.id))

    def test_missed_daily_time_runs_once_when_the_computer_is_available(self):
        from extensions.subscriptions.automation import AutomationService
        from extensions.subscriptions.store import SubscriptionStore

        with TemporaryDirectory() as directory:
            store = SubscriptionStore(Path(directory))
            store.update_automation(
                enabled=True,
                run_time="08:30",
                catch_up=True,
                last_scheduled_date="2026-07-31",
            )
            service = AutomationService(store=store, runner=None)

            self.assertTrue(service.is_due(datetime(2026, 8, 1, 10, 0)))
            service.mark_scheduled(datetime(2026, 8, 1, 10, 0))
            self.assertFalse(service.is_due(datetime(2026, 8, 1, 10, 5)))


class SubscriptionRunnerTests(unittest.TestCase):
    def test_automatic_run_skips_paused_subscriptions_and_respects_global_limit(self):
        from extensions.subscriptions.runner import SubscriptionRunner
        from extensions.subscriptions.store import SubscriptionStore

        class Pipeline:
            def __init__(self):
                self.ran = []

            async def run(self, subscription):
                self.ran.append((subscription.id, subscription.daily_limit))
                return subscription.id

        with TemporaryDirectory() as directory:
            store = SubscriptionStore(Path(directory))
            first = store.create(
                kind="feed", name="One", source="https://example.org/1", daily_limit=4
            )
            second = store.create(
                kind="feed", name="Two", source="https://example.org/2", daily_limit=4
            )
            paused = store.create(
                kind="feed", name="Paused", source="https://example.org/3", enabled=False
            )
            store.update_automation(enabled=True, daily_limit=5)
            pipeline = Pipeline()
            runner = SubscriptionRunner(store=store, literature_pipeline=pipeline)

            results = asyncio.run(runner.run_enabled())

            self.assertEqual((first.id, second.id), results)
            self.assertEqual([(first.id, 4), (second.id, 1)], pipeline.ran)
            self.assertNotIn(paused.id, results)

    def test_manual_runs_can_be_scoped_to_wechat_or_literature(self):
        from extensions.subscriptions.runner import SubscriptionRunner
        from extensions.subscriptions.store import SubscriptionStore

        class Pipeline:
            def __init__(self):
                self.ran = []

            async def run(self, subscription):
                self.ran.append(subscription.id)
                return subscription.id

        with TemporaryDirectory() as directory:
            store = SubscriptionStore(Path(directory))
            wechat = store.create(
                kind="wechat_account", name="示例公众号", source="示例公众号"
            )
            literature = store.create(
                kind="feed", name="示例期刊", source="https://example.org/rss"
            )
            literature_pipeline = Pipeline()
            wechat_pipeline = Pipeline()
            runner = SubscriptionRunner(
                store=store,
                literature_pipeline=literature_pipeline,
                wechat_pipeline=wechat_pipeline,
            )

            wechat_results = asyncio.run(runner.run_all_manual(scope="wechat"))
            literature_results = asyncio.run(
                runner.run_all_manual(scope="literature")
            )

        self.assertEqual((wechat.id,), wechat_results)
        self.assertEqual((literature.id,), literature_results)
        self.assertEqual([wechat.id], wechat_pipeline.ran)
        self.assertEqual([literature.id], literature_pipeline.ran)


class ScheduledTaskScriptTests(unittest.TestCase):
    def test_windows_task_is_single_current_user_task_with_start_when_available(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "install-automation-task.ps1").read_text("utf-8")

        self.assertIn("Medical Knowledge Hub Daily", script)
        self.assertIn("-StartWhenAvailable", script)
        self.assertIn("Disable-ScheduledTask", script)
        self.assertNotIn("RunLevel Highest", script)


if __name__ == "__main__":
    unittest.main()
