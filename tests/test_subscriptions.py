import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


class SubscriptionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _store(self):
        from extensions.subscriptions.store import SubscriptionStore

        return SubscriptionStore(self.root)

    def test_create_pause_resume_and_delete_subscription(self):
        store = self._store()
        created = store.create(
            kind="journal",
            name="Journal of Clinical Epidemiology",
            source="https://example.org/feed.xml",
            keywords=("causal inference",),
            daily_limit=3,
        )

        self.assertTrue(created.enabled)
        self.assertEqual("journal", created.kind)
        self.assertEqual(3, created.daily_limit)
        self.assertEqual((created,), store.list())

        paused = store.update(created.id, enabled=False)
        self.assertFalse(paused.enabled)
        self.assertFalse(store.get(created.id).enabled)

        resumed = store.update(created.id, enabled=True)
        self.assertTrue(resumed.enabled)
        store.delete(created.id)
        self.assertEqual((), store.list())

    def test_state_is_atomic_and_export_import_is_explicit(self):
        source = self._store()
        source.create(
            kind="wechat_account",
            name="示例医学公众号",
            source="示例医学公众号",
        )
        source.update_automation(enabled=True, run_time="08:30", daily_limit=5)

        payload = source.export_config()
        self.assertEqual("medical-knowledge-hub-subscriptions", payload["format"])
        self.assertNotIn("cookie", json.dumps(payload).lower())
        self.assertFalse(any(self.root.rglob("*.tmp")))

        target_root = self.root / "imported"
        from extensions.subscriptions.store import SubscriptionStore

        target = SubscriptionStore(target_root)
        target.import_config(payload)
        self.assertEqual("示例医学公众号", target.list()[0].name)
        self.assertTrue(target.get_automation().enabled)

    def test_invalid_subscription_kind_and_time_are_rejected(self):
        store = self._store()
        with self.assertRaises(ValueError):
            store.create(kind="crawler", name="x", source="https://example.org")
        with self.assertRaises(ValueError):
            store.update_automation(run_time="25:90")

    def test_wechat_subscription_persists_a_concrete_success_cursor(self):
        store = self._store()
        subscription = store.create(
            kind="wechat_account",
            name="示例医学公众号",
            source="示例医学公众号",
        )

        self.assertEqual("", subscription.last_successful_date)
        updated = store.update(subscription.id, last_successful_date="2026-08-01")

        self.assertEqual("2026-08-01", updated.last_successful_date)
        self.assertEqual("2026-08-01", store.get(subscription.id).last_successful_date)
        with self.assertRaises(ValueError):
            store.update(
                subscription.id,
                last_successful_date="2026-08-01T08:30:00",
            )

    def test_sync_wechat_accounts_is_atomic_and_keeps_literature_subscriptions(self):
        store = self._store()
        old_wechat = store.create(
            kind="wechat_account",
            name="旧公众号",
            source="旧公众号",
            enabled=False,
            daily_limit=3,
        )
        literature = store.create(
            kind="feed",
            name="示例期刊",
            source="https://example.org/rss.xml",
        )

        accounts = store.sync_wechat_accounts(
            [" 示例医学方法号 ", "示例科研写作号", "示例医学方法号"]
        )

        self.assertEqual(
            ["示例医学方法号", "示例科研写作号"],
            [item.name for item in accounts],
        )
        self.assertTrue(all(item.enabled for item in accounts))
        self.assertEqual("示例医学方法号", accounts[0].source)
        self.assertNotIn(old_wechat.id, [item.id for item in store.list()])
        self.assertEqual(literature, store.get(literature.id))
        self.assertFalse(any(self.root.rglob("*.tmp")))

    def test_sync_wechat_accounts_can_clear_the_default_list(self):
        store = self._store()
        store.create(kind="wechat_account", name="示例公众号", source="示例公众号")
        store.create(kind="journal", name="示例期刊")

        self.assertEqual((), store.sync_wechat_accounts([]))
        self.assertEqual(["journal"], [item.kind for item in store.list()])


class SubscriptionApiTests(unittest.TestCase):
    def test_wechat_account_list_has_a_dedicated_bulk_editor_api(self):
        from fastapi.testclient import TestClient
        from app import app

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"CONTENT_HUB_STATE_DIR": directory}
        ), TestClient(app) as client:
            saved = client.put(
                "/api/ext/subscriptions/wechat-accounts",
                json={"accounts": ["示例医学公众号", "循证研究笔记", "示例医学公众号"]},
            )
            listed = client.get("/api/ext/subscriptions/wechat-accounts")

        self.assertEqual(200, saved.status_code)
        self.assertEqual(
            ["示例医学公众号", "循证研究笔记"],
            [item["name"] for item in saved.json()["subscriptions"]],
        )
        self.assertEqual(saved.json(), listed.json())

    def test_imported_automation_is_synchronized_with_the_windows_task(self):
        from fastapi.testclient import TestClient
        from app import app

        payload = {
            "format": "medical-knowledge-hub-subscriptions",
            "version": 1,
            "subscriptions": [],
            "automation": {
                "enabled": True,
                "run_time": "07:45",
                "daily_limit": 3,
                "catch_up": True,
                "last_scheduled_date": "",
            },
        }
        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"CONTENT_HUB_STATE_DIR": directory}
        ), patch(
            "routes_ext.subscriptions.sync_windows_task",
            return_value={"managed": True},
        ) as sync_task, TestClient(app) as client:
            response = client.post("/api/ext/subscriptions/import", json=payload)

        self.assertEqual(200, response.status_code)
        sync_task.assert_called_once()
        self.assertEqual("07:45", sync_task.call_args.args[0].run_time)

    def test_crud_and_automation_api_start_with_blank_personal_state(self):
        from fastapi.testclient import TestClient
        from app import app

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"CONTENT_HUB_STATE_DIR": directory}
        ), TestClient(app) as client:
            self.assertEqual([], client.get("/api/ext/subscriptions").json()["subscriptions"])

            created = client.post(
                "/api/ext/subscriptions",
                json={
                    "kind": "feed",
                    "name": "示例期刊",
                    "source": "https://example.org/rss.xml",
                    "keywords": ["survival analysis"],
                    "daily_limit": 2,
                },
            )
            self.assertEqual(201, created.status_code)
            identifier = created.json()["subscription"]["id"]

            paused = client.patch(
                f"/api/ext/subscriptions/{identifier}", json={"enabled": False}
            )
            self.assertFalse(paused.json()["subscription"]["enabled"])

            settings = client.put(
                "/api/ext/automation",
                json={"enabled": True, "run_time": "09:15", "daily_limit": 4},
            )
            self.assertEqual("09:15", settings.json()["automation"]["run_time"])

            exported = client.get("/api/ext/subscriptions/export").json()
            self.assertEqual(1, len(exported["subscriptions"]))

            deleted = client.delete(f"/api/ext/subscriptions/{identifier}")
            self.assertEqual(204, deleted.status_code)
            self.assertEqual([], client.get("/api/ext/subscriptions").json()["subscriptions"])

    def test_manual_run_and_login_continuation_routes_are_exposed(self):
        from fastapi.testclient import TestClient
        from app import app
        from extensions.subscriptions.runs import LiteratureRunStore

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"CONTENT_HUB_STATE_DIR": directory}
        ):
            root = Path(directory)
            from extensions.subscriptions.store import SubscriptionStore

            subscription = SubscriptionStore(root).create(
                kind="literature_query",
                name="示例检索",
                query="causal inference",
            )
            run_store = LiteratureRunStore(root)

            class Runner:
                async def run_one(self, subscription_id):
                    return run_store.create(subscription_id)

            with patch(
                "routes_ext.subscriptions.build_subscription_runner",
                return_value=Runner(),
                create=True,
            ), TestClient(app) as client:
                response = client.post(
                    "/api/ext/literature/runs/run",
                    json={"subscription_id": subscription.id},
                )
                listed = client.get("/api/ext/literature/runs")

            self.assertEqual(200, response.status_code)
            self.assertEqual("discovering", response.json()["runs"][0]["status"])
            self.assertEqual(1, len(listed.json()["runs"]))


if __name__ == "__main__":
    unittest.main()
