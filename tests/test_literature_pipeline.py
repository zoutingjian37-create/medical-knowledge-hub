import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


class LiteraturePipelineTests(unittest.TestCase):
    def _subscription(self, root: Path, **changes):
        from extensions.subscriptions.store import SubscriptionStore

        values = {
            "kind": "literature_query",
            "name": "因果推断",
            "query": "target trial",
            "keywords": ("cardiovascular",),
            "requirement": "关注可迁移的因果推断方法",
            "daily_limit": 5,
            "zotero_collection": "因果推断",
        }
        values.update(changes)
        return SubscriptionStore(root).create(**values)

    def test_auto_distillation_setting_controls_skill_execution(self):
        from extensions.subscriptions.pipeline import auto_distill_enabled

        class Store:
            def __init__(self, enabled):
                self.enabled = enabled

            def get_auto_distill_enabled(self):
                return self.enabled

        class Queue:
            def __init__(self, enabled):
                self.store = Store(enabled)

        self.assertTrue(auto_distill_enabled(Queue(True)))
        self.assertFalse(auto_distill_enabled(Queue(False)))

    def test_open_literature_flows_through_zotero_skill_and_review_gate(self):
        from extensions.processing.job_queue import QueueResult
        from extensions.processing.job_store import KnowledgeJob
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.pipeline import LiteraturePipeline
        from extensions.subscriptions.runs import LiteratureRunStore

        class Discoverer:
            async def discover(self, subscription):
                return (
                    LiteratureItem(
                        title="Target trial for cardiovascular outcomes",
                        url="https://doi.org/10.1000/target",
                        doi="10.1000/target",
                        abstract="The intervention reduced cardiovascular risk.",
                        authors="A. Researcher",
                        published_at="2026-07-31",
                        pdf_url="https://cdn.example/target.pdf",
                        open_access=True,
                    ),
                    LiteratureItem(
                        title="Unrelated laboratory study",
                        url="https://doi.org/10.1000/unrelated",
                        abstract="No matching topic.",
                    ),
                )

        class Zotero:
            def __init__(self):
                self.saved = []

            async def save(self, item, collection):
                self.saved.append((item.doi, collection))
                return {
                    "status": "saved",
                    "item_key": "ABCD1234",
                    "pdf_saved": False,
                    "pdf_error": "ReadTimeout",
                }

        class Queue:
            def __init__(self):
                self.documents = []

            def enqueue(self, document, platform="literature"):
                self.documents.append(document)
                job = KnowledgeJob(
                    id="job-1",
                    status="pending",
                    source_url=document.source_url,
                    title=document.title,
                    author=document.author,
                    published_at=document.published_at,
                    platform=platform,
                    cache_path="D:/temp/source.md",
                    created_at="2026-08-01T00:00:00+00:00",
                    updated_at="2026-08-01T00:00:00+00:00",
                )
                return QueueResult(True, "pending", job)

        class Compiler:
            def __init__(self):
                self.jobs = []

            def run_codex(self, job_id):
                self.jobs.append(job_id)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            subscription = self._subscription(root)
            zotero, queue, compiler = Zotero(), Queue(), Compiler()
            pipeline = LiteraturePipeline(
                discoverer=Discoverer(),
                zotero=zotero,
                queue=queue,
                compiler=compiler,
                run_store=LiteratureRunStore(root),
                state_root=root,
            )

            run = asyncio.run(pipeline.run(subscription))

            self.assertEqual("waiting_confirmation", run.status)
            self.assertEqual(2, run.discovered)
            self.assertEqual(1, run.filtered)
            self.assertEqual(1, run.saved_zotero)
            self.assertEqual(1, run.queued)
            self.assertIn("PDF", run.error)
            self.assertIn("ReadTimeout", run.error)
            self.assertEqual([("10.1000/target", "因果推断")], zotero.saved)
            self.assertEqual(["job-1"], compiler.jobs)
            self.assertIn("evidence_level: abstract", queue.documents[0].markdown)
            self.assertIn("DOI: 10.1000/target", queue.documents[0].markdown)
            self.assertIn("关注可迁移的因果推断方法", queue.documents[0].markdown)

    def test_paywalled_item_waits_for_school_login_without_credentials(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.pipeline import LiteraturePipeline
        from extensions.subscriptions.runs import LiteratureRunStore

        item = LiteratureItem(
            title="Restricted cohort study",
            url="https://publisher.example/article/1",
            doi="10.1000/restricted",
            abstract="Abstract only.",
            open_access=False,
        )

        class Discoverer:
            async def discover(self, subscription):
                return (item,)

        class Zotero:
            async def save(self, item, collection):
                return {"status": "waiting_school_login", "url": item.url}

        class Queue:
            def enqueue(self, document, platform="literature"):
                raise AssertionError("restricted item must wait before distillation")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            subscription = self._subscription(root, keywords=())
            run = asyncio.run(
                LiteraturePipeline(
                    discoverer=Discoverer(),
                    zotero=Zotero(),
                    queue=Queue(),
                    compiler=None,
                    run_store=LiteratureRunStore(root),
                    state_root=root,
                ).run(subscription)
            )

            self.assertEqual("waiting_school_login", run.status)
            pending = json_files(root / "login-handoffs")
            self.assertEqual(1, len(pending))
            text = pending[0].read_text("utf-8").lower()
            self.assertNotIn("password", text)
            self.assertNotIn("cookie", text)

    def test_zotero_indexed_full_text_is_labeled_as_full_text_evidence(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.pipeline import literature_document

        with TemporaryDirectory() as directory:
            subscription = self._subscription(Path(directory), keywords=())
        document = literature_document(
            LiteratureItem(
                title="Open article",
                url="https://doi.org/10.1000/full",
                doi="10.1000/full",
                abstract="Abstract only.",
            ),
            subscription,
            full_text="Full methods and results from the indexed PDF.",
        )

        self.assertIn("evidence_level: full_text", document.markdown)
        self.assertIn("Full methods and results", document.markdown)
        self.assertNotIn("Abstract only.", document.markdown)

    def test_distillation_failure_preserves_zotero_and_queue_progress(self):
        from extensions.processing.job_queue import QueueResult
        from extensions.processing.job_store import KnowledgeJob
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.pipeline import LiteraturePipeline
        from extensions.subscriptions.runs import LiteratureRunStore

        class Discoverer:
            async def discover(self, subscription):
                return (
                    LiteratureItem(
                        title="Open study",
                        url="https://doi.org/10.1000/progress",
                        doi="10.1000/progress",
                        abstract="Conclusion.",
                        open_access=True,
                    ),
                )

        class Zotero:
            async def save(self, item, collection):
                return {"status": "saved", "item_key": "ITEM1"}

        class Queue:
            def enqueue(self, document, platform="literature"):
                return QueueResult(
                    True,
                    "pending",
                    KnowledgeJob(
                        id="job-progress",
                        status="pending",
                        source_url=document.source_url,
                        title=document.title,
                        author=document.author,
                        published_at=document.published_at,
                        platform=platform,
                        cache_path="D:/temp/source.md",
                        created_at="2026-08-01T00:00:00+00:00",
                        updated_at="2026-08-01T00:00:00+00:00",
                    ),
                )

        class Compiler:
            def run_codex(self, job_id):
                raise RuntimeError("preview contract mismatch")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            subscription = self._subscription(root, keywords=())
            runs = LiteratureRunStore(root)
            pipeline = LiteraturePipeline(
                discoverer=Discoverer(), zotero=Zotero(), queue=Queue(),
                compiler=Compiler(), run_store=runs, state_root=root,
            )
            with self.assertRaisesRegex(RuntimeError, "contract mismatch"):
                asyncio.run(pipeline.run(subscription))

            failed = runs.list()[0]
            self.assertEqual("failed", failed.status)
            self.assertEqual(1, failed.saved_zotero)
            self.assertEqual(1, failed.queued)

    def test_continue_after_connector_save_resumes_distillation(self):
        from extensions.processing.job_queue import QueueResult
        from extensions.processing.job_store import KnowledgeJob
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.pipeline import LiteraturePipeline
        from extensions.subscriptions.runs import LiteratureRunStore

        item = LiteratureItem(
            title="Restricted cohort study",
            url="https://publisher.example/article/1",
            doi="10.1000/restricted",
            abstract="Abstract only.",
            open_access=False,
        )

        class Discoverer:
            async def discover(self, subscription):
                return (item,)

        class Zotero:
            async def save(self, item, collection):
                return {"status": "waiting_school_login", "url": item.url}

            async def contains(self, item):
                return True

            async def find_item_key(self, item):
                return "ITEM1"

            async def has_pdf_attachment(self, item_key):
                return item_key == "ITEM1"

            async def read_full_text(self, item_key):
                self.read_key = item_key
                return "Institutional full text methods and results."

        class Queue:
            def __init__(self):
                self.document = None

            def enqueue(self, document, platform="literature"):
                self.document = document
                return QueueResult(
                    True,
                    "pending",
                    KnowledgeJob(
                        id="job-after-login",
                        status="pending",
                        source_url=document.source_url,
                        title=document.title,
                        author=document.author,
                        published_at=document.published_at,
                        platform=platform,
                        cache_path="D:/temp/source.md",
                        created_at="2026-08-01T00:00:00+00:00",
                        updated_at="2026-08-01T00:00:00+00:00",
                    ),
                )

        class Compiler:
            def __init__(self):
                self.called = []

            def run_codex(self, job_id):
                self.called.append(job_id)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            subscription = self._subscription(root, keywords=())
            compiler = Compiler()
            queue = Queue()
            pipeline = LiteraturePipeline(
                discoverer=Discoverer(),
                zotero=Zotero(),
                queue=queue,
                compiler=compiler,
                run_store=LiteratureRunStore(root),
                state_root=root,
            )
            waiting = asyncio.run(pipeline.run(subscription))
            resumed = asyncio.run(pipeline.continue_login(waiting.id, subscription))

            self.assertEqual("waiting_confirmation", resumed.status)
            self.assertEqual(["job-after-login"], compiler.called)
            self.assertIn("evidence_level: full_text", queue.document.markdown)
            self.assertIn("Institutional full text", queue.document.markdown)
            self.assertEqual([], json_files(root / "login-handoffs"))

    def test_continue_login_keeps_waiting_when_zotero_has_only_metadata(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.pipeline import LiteraturePipeline
        from extensions.subscriptions.runs import LiteratureRunStore

        item = LiteratureItem(
            title="Restricted study without attachment",
            url="https://publisher.example/article/metadata-only",
            doi="10.1000/metadata-only",
            abstract="Abstract only.",
            open_access=False,
        )

        class Discoverer:
            async def discover(self, subscription):
                return (item,)

        class Zotero:
            async def save(self, item, collection):
                return {"status": "waiting_school_login", "url": item.url}

            async def find_item_key(self, item):
                return "ITEM-WITHOUT-PDF"

            async def has_pdf_attachment(self, item_key):
                return False

        class Queue:
            def enqueue(self, document, platform="literature"):
                raise AssertionError("metadata alone must not resume distillation")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            subscription = self._subscription(root, keywords=())
            pipeline = LiteraturePipeline(
                discoverer=Discoverer(),
                zotero=Zotero(),
                queue=Queue(),
                compiler=None,
                run_store=LiteratureRunStore(root),
                state_root=root,
            )
            waiting = asyncio.run(pipeline.run(subscription))
            resumed = asyncio.run(pipeline.continue_login(waiting.id, subscription))

            self.assertEqual("waiting_school_login", resumed.status)
            self.assertEqual(1, len(json_files(root / "login-handoffs")))


class ZoteroGatewayTests(unittest.TestCase):
    def test_gateway_waits_briefly_for_zotero_pdf_indexing(self):
        from extensions.subscriptions.zotero import ZoteroGateway

        sleeps = []

        async def no_wait(seconds):
            sleeps.append(seconds)

        class Gateway(ZoteroGateway):
            def __init__(self):
                super().__init__(client=object(), sleep=no_wait)
                self.calls = 0

            async def read_full_text(self, item_key):
                self.calls += 1
                return "" if self.calls < 3 else "Indexed full text."

        gateway = Gateway()
        content = asyncio.run(gateway.wait_for_full_text("ITEM1", attempts=4))

        self.assertEqual("Indexed full text.", content)
        self.assertEqual(3, gateway.calls)
        self.assertEqual([2, 2], sleeps)

    def test_pdf_download_failure_keeps_metadata_and_reports_a_reason(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.zotero import ZoteroGateway

        class Response:
            status_code = 201

            def __init__(self, payload=None):
                self.payload = payload or {}

            def json(self):
                return self.payload

            def raise_for_status(self):
                return None

        class Transport:
            async def post(self, url, **kwargs):
                if url.endswith("/connector/getSelectedCollection"):
                    return Response({"name": "Target"})
                return Response()

            async def get(self, url, **kwargs):
                if url.startswith("https://cdn.example"):
                    raise TimeoutError()
                return Response(
                    [{"key": "ITEM1", "data": {"DOI": "10.1000/slow"}}]
                )

        item = LiteratureItem(
            title="Slow PDF",
            url="https://doi.org/10.1000/slow",
            doi="10.1000/slow",
            pdf_url="https://cdn.example/slow.pdf",
            open_access=True,
        )
        result = asyncio.run(
            ZoteroGateway(
                client=Transport(),
                resolver=lambda *args: [(None, None, None, None, ("93.184.216.34", 443))],
            ).save(item, "Target")
        )

        self.assertEqual("saved", result["status"])
        self.assertFalse(result["pdf_saved"])
        self.assertEqual("TimeoutError", result["pdf_error"])

    def test_connector_saves_item_and_uploads_open_pdf_to_selected_collection(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.zotero import ZoteroGateway

        class Response:
            def __init__(self, status_code=200, payload=None, content=b"", headers=None):
                self.status_code = status_code
                self._payload = payload or {}
                self.text = "ok"
                self.content = content
                self.headers = headers or {}

            def json(self):
                return self._payload

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError("http error")

        class Transport:
            def __init__(self, selected):
                self.selected = selected
                self.posts = []

            async def post(self, url, **kwargs):
                self.posts.append((url, kwargs))
                if url.endswith("/connector/getSelectedCollection"):
                    return Response(payload={"name": self.selected})
                return Response(status_code=201)

            async def get(self, url, **kwargs):
                if url == "https://cdn.example/paper.pdf":
                    return Response(
                        content=b"%PDF-1.7 test pdf",
                        headers={"content-type": "application/pdf"},
                    )
                if url.endswith("/api/users/0/items"):
                    return Response(
                        payload=[{"key": "ZXCV1234", "data": {"DOI": "10.1000/example"}}]
                    )
                return Response(payload=[])

        item = LiteratureItem(
            title="A clinical study",
            url="https://doi.org/10.1000/example",
            doi="10.1000/example",
            authors="A. Researcher",
            published_at="2026",
            abstract="Conclusion.",
            pdf_url="https://cdn.example/paper.pdf",
            open_access=True,
        )
        wrong = asyncio.run(ZoteroGateway(client=Transport("Other")).save(item, "Target"))
        self.assertEqual("waiting_collection", wrong["status"])

        transport = Transport("Target")
        async def no_wait(_seconds):
            return None
        saved = asyncio.run(
            ZoteroGateway(
                client=transport,
                resolver=lambda *args: [(None, None, None, None, ("93.184.216.34", 443))],
                sleep=no_wait,
            ).save(item, "Target")
        )
        self.assertEqual("saved", saved["status"])
        self.assertTrue(saved["pdf_saved"])
        item_call = next(call for call in transport.posts if "/connector/saveItems" in call[0])
        attachment_call = next(call for call in transport.posts if "/connector/saveAttachment" in call[0])
        connector_item = item_call[1]["json"]["items"][0]
        metadata = json.loads(attachment_call[1]["headers"]["X-Metadata"])
        self.assertEqual("10.1000/example", connector_item["DOI"])
        self.assertEqual(connector_item["id"], metadata["parentItemID"])
        self.assertEqual(b"%PDF-1.7 test pdf", attachment_call[1]["content"])
        self.assertNotIn("cookie", json.dumps(item_call[1]["json"]).lower())
        self.assertFalse(any("/connector/import" in call[0] for call in transport.posts))

    def test_indexed_pdf_text_is_read_through_the_local_read_only_api(self):
        from extensions.subscriptions.zotero import ZoteroGateway

        class Response:
            status_code = 200

            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        class Transport:
            async def get(self, url, **kwargs):
                if url.endswith("/children"):
                    return Response(
                        [{"key": "ATTACH1", "data": {"itemType": "attachment"}}]
                    )
                return Response({"content": "Indexed methods and results."})

        content = asyncio.run(ZoteroGateway(client=Transport()).read_full_text("ITEM1"))
        self.assertEqual("Indexed methods and results.", content)

    def test_managed_pdf_attachment_is_required_after_school_login(self):
        from extensions.subscriptions.zotero import ZoteroGateway

        class Response:
            status_code = 200

            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        class Transport:
            async def get(self, url, **kwargs):
                return Response(
                    [
                        {
                            "key": "WEB1",
                            "data": {
                                "itemType": "attachment",
                                "contentType": "text/html",
                                "linkMode": "imported_url",
                            },
                        },
                        {
                            "key": "LINK1",
                            "data": {
                                "itemType": "attachment",
                                "contentType": "application/pdf",
                                "linkMode": "linked_url",
                            },
                        },
                        {
                            "key": "PDF1",
                            "data": {
                                "itemType": "attachment",
                                "contentType": "application/pdf",
                                "linkMode": "imported_url",
                            },
                        },
                    ]
                )

        ready = asyncio.run(
            ZoteroGateway(client=Transport()).has_pdf_attachment("ITEM1")
        )

        self.assertTrue(ready)

    def test_doi_detection_uses_everything_search_after_connector_save(self):
        from extensions.subscriptions.discovery import LiteratureItem
        from extensions.subscriptions.zotero import ZoteroGateway

        class Response:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return [{"key": "ITEM1", "data": {"DOI": "10.1000/restricted"}}]

        class Transport:
            def __init__(self):
                self.params = None

            async def get(self, url, **kwargs):
                self.params = kwargs["params"]
                return Response()

        transport = Transport()
        found = asyncio.run(
            ZoteroGateway(client=transport).contains(
                LiteratureItem(
                    title="Restricted", url="https://doi.org/10.1000/restricted",
                    doi="10.1000/restricted"
                )
            )
        )

        self.assertTrue(found)
        self.assertEqual("everything", transport.params["qmode"])


def json_files(path: Path):
    return sorted(path.glob("*.json")) if path.exists() else []


if __name__ == "__main__":
    unittest.main()
