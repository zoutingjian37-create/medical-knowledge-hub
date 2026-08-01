import json
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from extensions.processing.documents import MarkdownDocument


class KnowledgeJobLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.cache_root = root / "cache"
        self.state_root = root / "state"

    def tearDown(self):
        self.temporary.cleanup()

    def _document(self, body="clean article body"):
        return MarkdownDocument(
            source_url="https://mp.weixin.qq.com/s?__biz=demo&mid=1&idx=1&sn=x",
            title="A medical article",
            author="Medical account",
            published_at="2026-07-30",
            markdown=body,
        )

    def test_job_metadata_keeps_url_but_not_article_body(self):
        from extensions.processing.job_store import KnowledgeJobStore
        from extensions.processing.source_cache import SourceCache

        cache = SourceCache(self.cache_root)
        store = KnowledgeJobStore(self.state_root)
        document = self._document()
        cached = cache.put("job-1", document.markdown)

        job = store.create(document, cached, job_id="job-1")
        raw_metadata = (self.state_root / "jobs" / f"{job.id}.json").read_text(
            "utf-8"
        )

        self.assertIn(document.source_url, raw_metadata)
        self.assertNotIn(document.markdown, raw_metadata)
        self.assertEqual("pending", job.status)
        self.assertEqual(document.markdown, cache.read(job.id))

    def test_same_source_url_reuses_existing_job(self):
        from extensions.processing.job_store import KnowledgeJobStore
        from extensions.processing.source_cache import SourceCache

        cache = SourceCache(self.cache_root)
        store = KnowledgeJobStore(self.state_root)
        document = self._document()
        first = store.create(document, cache.put("first", document.markdown))
        second = store.create(document, cache.put("second", "new copy"))

        self.assertEqual(first.id, second.id)
        self.assertEqual(1, len(store.list()))

    def test_expired_source_is_deleted_and_job_requires_reparse(self):
        from extensions.processing.job_store import KnowledgeJobStore, expire_jobs
        from extensions.processing.source_cache import SourceCache

        cache = SourceCache(self.cache_root)
        store = KnowledgeJobStore(self.state_root)
        document = self._document()
        cached = cache.put("old-job", document.markdown)
        job = store.create(document, cached, job_id="old-job")
        old = time.time() - 25 * 60 * 60
        os.utime(cached, (old, old))

        expired = expire_jobs(cache, store, max_age_hours=24)

        self.assertEqual((job.id,), expired)
        self.assertFalse(cached.exists())
        self.assertEqual("needs_reparse", store.get(job.id).status)

    def test_job_json_is_valid_utf8_and_update_is_persistent(self):
        from extensions.processing.job_store import KnowledgeJobStore
        from extensions.processing.source_cache import SourceCache

        cache = SourceCache(self.cache_root)
        store = KnowledgeJobStore(self.state_root)
        document = self._document("医学正文")
        job = store.create(document, cache.put("unicode", document.markdown))

        updated = store.update(job.id, status="preview_ready")
        payload = json.loads(
            (self.state_root / "jobs" / f"{job.id}.json").read_text("utf-8")
        )

        self.assertEqual("preview_ready", updated.status)
        self.assertEqual(document.title, payload["title"])

    def test_reparse_recreates_expired_cache_for_the_same_job(self):
        from extensions.processing.job_queue import KnowledgeJobQueue
        from extensions.processing.job_store import KnowledgeJobStore
        from extensions.processing.source_cache import SourceCache

        cache = SourceCache(self.cache_root)
        store = KnowledgeJobStore(self.state_root)
        queue = KnowledgeJobQueue(cache=cache, store=store)
        document = self._document()
        first = queue.enqueue(document)
        Path(first.job.cache_path).unlink()
        store.update(first.job.id, status="needs_reparse", cache_path="")

        reparsed = queue.enqueue(document)

        self.assertTrue(reparsed.queued)
        self.assertEqual(first.job.id, reparsed.job.id)
        self.assertEqual("pending", reparsed.job.status)
        self.assertTrue(Path(reparsed.job.cache_path).exists())

    def test_trash_retention_defaults_to_seven_days_and_accepts_one_to_thirty(self):
        from extensions.processing.job_store import KnowledgeJobStore

        store = KnowledgeJobStore(self.state_root)

        self.assertEqual(7, store.get_trash_retention_days())
        self.assertEqual(30, store.set_trash_retention_days(30))
        self.assertEqual(30, store.get_trash_retention_days())
        with self.assertRaises(ValueError):
            store.set_trash_retention_days(0)
        with self.assertRaises(ValueError):
            store.set_trash_retention_days(31)

    def test_skill_distillation_is_the_default_and_can_be_disabled(self):
        from extensions.processing.job_store import KnowledgeJobStore

        store = KnowledgeJobStore(self.state_root)

        self.assertTrue(store.get_auto_distill_enabled())
        self.assertFalse(store.set_auto_distill_enabled(False))
        self.assertFalse(store.get_auto_distill_enabled())
        self.assertTrue(store.set_auto_distill_enabled(True))

    def test_expired_trash_is_permanently_deleted_after_retention_period(self):
        from extensions.processing.compiler import KnowledgeCompiler
        from extensions.processing.job_store import KnowledgeJobStore
        from extensions.processing.source_cache import SourceCache

        cache = SourceCache(self.cache_root)
        store = KnowledgeJobStore(self.state_root)
        document = self._document()
        job = store.create(document, cache.put("trash-job", document.markdown), job_id="trash-job")
        compiler = KnowledgeCompiler(store=store, cache=cache)
        compiler.trash(job.id)
        deleted_at = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        store.update(job.id, deleted_at=deleted_at)

        purged = compiler.purge_expired_trash()

        self.assertEqual((job.id,), purged)
        self.assertFalse(Path(job.cache_path).exists())
        with self.assertRaises(KeyError):
            store.get(job.id)


if __name__ == "__main__":
    unittest.main()
