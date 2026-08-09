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

    def test_sync_wechat_accounts_applies_the_saved_per_account_limit(self):
        store = self._store()
        existing = store.create(
            kind="wechat_account",
            name="示例医学方法号",
            source="示例医学方法号",
            daily_limit=2,
        )

        accounts = store.sync_wechat_accounts(
            ["示例医学方法号", "示例循证研究号"], daily_limit=7
        )

        self.assertEqual(existing.id, accounts[0].id)
        self.assertEqual([7, 7], [item.daily_limit for item in accounts])

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
                json={
                    "accounts": ["示例医学公众号", "循证研究笔记", "示例医学公众号"],
                    "daily_limit": 7,
                },
            )
            listed = client.get("/api/ext/subscriptions/wechat-accounts")

        self.assertEqual(200, saved.status_code)
        self.assertEqual(
            ["示例医学公众号", "循证研究笔记"],
            [item["name"] for item in saved.json()["subscriptions"]],
        )
        self.assertEqual(saved.json(), listed.json())
        self.assertEqual([7, 7], [item["daily_limit"] for item in saved.json()["subscriptions"]])

    def test_literature_source_list_adds_journals_and_rss_without_touching_existing_items(self):
        from fastapi.testclient import TestClient
        from app import app

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"CONTENT_HUB_STATE_DIR": directory}
        ), TestClient(app) as client:
            query = client.post(
                "/api/ext/subscriptions",
                json={"kind": "literature_query", "name": "保留的检索", "query": "biomarker"},
            )
            self.assertEqual(201, query.status_code)

            saved = client.post(
                "/api/ext/subscriptions/literature-sources",
                json={
                    "sources": [
                        "Clinical Chemistry",
                        "https://example.org/clinical-chemistry.xml",
                        "Clinical Chemistry",
                    ],
                    "daily_limit": 4,
                },
            )
            self.assertEqual(200, saved.status_code)
            first = saved.json()["subscriptions"]
            self.assertEqual(["journal", "feed"], [item["kind"] for item in first])
            self.assertEqual(4, first[0]["daily_limit"])

            repeated = client.post(
                "/api/ext/subscriptions/literature-sources",
                json={"sources": ["https://example.org/clinical-chemistry.xml"], "daily_limit": 3},
            )
            self.assertEqual(200, repeated.status_code)
            self.assertEqual(0, repeated.json()["created"])
            all_items = client.get("/api/ext/subscriptions").json()["subscriptions"]
            self.assertEqual(
                ["literature_query", "journal", "feed"],
                [item["kind"] for item in all_items],
            )

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

            updated = client.patch(
                f"/api/ext/subscriptions/{identifier}",
                json={
                    "name": "更新后的示例期刊",
                    "source": "https://example.org/updated.xml",
                    "keywords": ["causal inference"],
                    "daily_limit": 5,
                    "zotero_collection": "更新后的目录",
                },
            )
            self.assertEqual(200, updated.status_code)
            self.assertEqual("更新后的示例期刊", updated.json()["subscription"]["name"])
            self.assertEqual(5, updated.json()["subscription"]["daily_limit"])

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


class RunHistoryManagementTests(unittest.TestCase):
    def test_completed_runs_expire_but_failed_runs_stay_until_selected_for_deletion(self):
        from extensions.subscriptions.runs import LiteratureRunStore

        with TemporaryDirectory() as directory:
            store = LiteratureRunStore(Path(directory))
            with patch(
                "extensions.subscriptions.runs._utc_now",
                return_value="2026-07-01T08:30:00+00:00",
            ):
                completed = store.create("completed")
                store.update(completed.id, status="completed")
                failed = store.create("failed")
                store.update(failed.id, status="failed")
            with patch(
                "extensions.subscriptions.runs._utc_now",
                return_value="2026-08-01T08:30:00+00:00",
            ):
                recent = store.create("recent")
                store.update(recent.id, status="completed")

            expired = store.purge_completed(max_age_days=14)
            deleted = store.delete_many([failed.id, "missing-run"])

            self.assertEqual((completed.id,), expired)
            self.assertEqual((failed.id,), deleted)
            self.assertEqual((recent.id,), tuple(run.id for run in store.list()))

    def test_run_history_routes_retry_failed_items_and_delete_selected_records(self):
        from fastapi.testclient import TestClient
        from app import app
        from extensions.subscriptions.runs import LiteratureRunStore
        from extensions.subscriptions.store import SubscriptionStore

        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"CONTENT_HUB_STATE_DIR": directory}
        ):
            root = Path(directory)
            subscription = SubscriptionStore(root).create(
                kind="wechat_account", name="示例公众号", source="示例公众号"
            )
            run_store = LiteratureRunStore(root)
            failed = run_store.create(subscription.id)
            failed = run_store.update(
                failed.id,
                status="failed",
                date_from="2026-08-01",
                date_to="2026-08-02",
            )

            class Runner:
                def __init__(self):
                    self.calls = []

                async def run_one(self, subscription_id, *, date_from=None, date_to=None):
                    self.calls.append((subscription_id, date_from, date_to))
                    return run_store.create(subscription_id)

            runner = Runner()
            with patch(
                "routes_ext.subscriptions.build_subscription_runner",
                return_value=runner,
            ), TestClient(app) as client:
                retried = client.post(
                    "/api/ext/literature/runs/retry-selected",
                    json={"run_ids": [failed.id]},
                )
                deleted = client.request(
                    "DELETE",
                    "/api/ext/literature/runs",
                    json={"run_ids": [failed.id]},
                )

            self.assertEqual(200, retried.status_code)
            self.assertEqual(1, len(retried.json()["runs"]))
            self.assertEqual([(subscription.id, "2026-08-01", "2026-08-02")], [
                (identifier, start.isoformat(), end.isoformat())
                for identifier, start, end in runner.calls
            ])
            self.assertEqual(200, deleted.status_code)
            self.assertEqual([failed.id], deleted.json()["deleted_ids"])


if __name__ == "__main__":
    unittest.main()
