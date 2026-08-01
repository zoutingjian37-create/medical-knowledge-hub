"""Convert cleaned public content into pending knowledge jobs."""

from dataclasses import dataclass, replace

from .archive import clean_markdown, is_advertisement_title
from .documents import MarkdownDocument
from .job_store import KnowledgeJob, KnowledgeJobStore
from .source_cache import SourceCache


@dataclass(frozen=True)
class QueueResult:
    queued: bool
    reason: str
    job: KnowledgeJob | None


class KnowledgeJobQueue:
    def __init__(
        self,
        cache: SourceCache | None = None,
        store: KnowledgeJobStore | None = None,
    ):
        self.cache = cache or SourceCache()
        self.store = store or KnowledgeJobStore()

    def enqueue(
        self,
        document: MarkdownDocument,
        platform: str = "wechat",
    ) -> QueueResult:
        if is_advertisement_title(document.title):
            return QueueResult(False, "advertisement", None)

        existing = self.store.find_by_source(document.source_url)
        if existing is not None:
            if existing.status == "needs_reparse":
                cleaned = replace(document, markdown=clean_markdown(document.markdown))
                cache_path = self.cache.put(existing.id, cleaned.markdown)
                refreshed = self.store.update(
                    existing.id,
                    status="pending",
                    cache_path=str(cache_path),
                    title=cleaned.title,
                    author=cleaned.author,
                    published_at=cleaned.published_at,
                    error="",
                )
                return QueueResult(True, "pending", refreshed)
            return QueueResult(False, "duplicate", existing)

        job_id = self.store.id_for_source(document.source_url)
        cleaned = replace(document, markdown=clean_markdown(document.markdown))
        cache_path = self.cache.put(job_id, cleaned.markdown)
        job = self.store.create(
            cleaned,
            cache_path,
            job_id=job_id,
            platform=platform,
        )
        return QueueResult(True, "pending", job)
