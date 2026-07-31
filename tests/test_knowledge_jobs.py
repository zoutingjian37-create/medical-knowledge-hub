import json
import os
import tempfile
import time
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


if __name__ == "__main__":
    unittest.main()
