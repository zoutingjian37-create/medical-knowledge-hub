"""Discover, filter, save, distill, and stop at the Obsidian review gate."""

import asyncio
from dataclasses import asdict
import json
from pathlib import Path

from extensions.processing.documents import MarkdownDocument

from .dedup import unique_items
from .discovery import LiteratureItem
from .runs import LiteratureRunStore


def auto_distill_enabled(queue) -> bool:
    store = getattr(queue, "store", None)
    getter = getattr(store, "get_auto_distill_enabled", None)
    return bool(getter()) if callable(getter) else True


class LiteraturePipeline:
    def __init__(
        self,
        *,
        discoverer,
        zotero,
        queue,
        compiler,
        run_store: LiteratureRunStore,
        state_root: Path,
    ):
        self.discoverer = discoverer
        self.zotero = zotero
        self.queue = queue
        self.compiler = compiler
        self.run_store = run_store
        self.state_root = Path(state_root)
        self.seen = SeenLiteratureStore(self.state_root)

    async def run(self, subscription):
        run = self.run_store.create(subscription.id)
        try:
            discovered = tuple(await self.discoverer.discover(subscription))
            candidates = unique_items(discovered)
            candidates = tuple(
                item
                for item in candidates
                if matches_subscription(item, subscription) and not self.seen.contains(item)
            )[: subscription.daily_limit]
            run = self.run_store.update(
                run.id,
                status="filtered",
                discovered=len(discovered),
                filtered=len(candidates),
            )

            saved = 0
            queued = 0
            waiting = False
            warnings = []
            for item in candidates:
                result = await self.zotero.save(item, subscription.zotero_collection)
                if result.get("status") in {"waiting_school_login", "waiting_collection"}:
                    self._save_handoff(run.id, subscription, item, result)
                    waiting = True
                    continue
                if result.get("status") != "saved":
                    raise RuntimeError(result.get("detail") or "Zotero import failed")
                if item.pdf_url and result.get("pdf_saved") is False:
                    reason = str(result.get("pdf_error") or "PDF download failed")
                    warnings.append(f"PDF 未保存：{item.title}（{reason}）")
                saved += 1
                self.run_store.update(
                    run.id,
                    status="saved_zotero",
                    saved_zotero=saved,
                    queued=queued,
                )
                queue_result = self.queue.enqueue(
                    literature_document(
                        item,
                        subscription,
                        full_text=str(result.get("full_text") or ""),
                    ),
                    platform="literature",
                )
                self.seen.add(item)
                if queue_result.queued and queue_result.job:
                    queued += 1
                    if self.compiler is not None and auto_distill_enabled(self.queue):
                        self.run_store.update(
                            run.id,
                            status="distilling",
                            saved_zotero=saved,
                            queued=queued,
                        )
                        await asyncio.to_thread(
                            self.compiler.run_codex, queue_result.job.id
                        )

            if waiting:
                status = "waiting_school_login"
            elif queued:
                status = "waiting_confirmation"
            else:
                status = "completed"
            return self.run_store.update(
                run.id,
                status=status,
                saved_zotero=saved,
                queued=queued,
                error="；".join(warnings),
            )
        except Exception as exc:
            self.run_store.update(run.id, status="failed", error=str(exc))
            raise

    async def continue_login(self, run_id, subscription):
        run = self.run_store.get(run_id)
        root = self.state_root / "login-handoffs"
        handoffs = sorted(root.glob(f"{run_id}-*.json")) if root.exists() else []
        queued = 0
        saved = 0
        remaining = 0
        for path in handoffs:
            payload = json.loads(path.read_text("utf-8"))
            item = LiteratureItem(**payload["item"])
            reason = payload.get("reason", "waiting_school_login")
            item_key = ""
            full_text = ""
            find_item_key = getattr(self.zotero, "find_item_key", None)
            if callable(find_item_key):
                item_key = await find_item_key(item)
                has_pdf_attachment = getattr(
                    self.zotero, "has_pdf_attachment", None
                )
                ready = bool(item_key)
                if ready and callable(has_pdf_attachment):
                    ready = await has_pdf_attachment(item_key)
            else:
                ready = await self.zotero.contains(item)
            if not ready and reason == "waiting_collection":
                result = await self.zotero.save(item, subscription.zotero_collection)
                ready = result.get("status") == "saved"
                item_key = str(result.get("item_key") or "")
                full_text = str(result.get("full_text") or "")
            if not ready:
                remaining += 1
                continue
            read_full_text = getattr(self.zotero, "read_full_text", None)
            if not full_text and item_key and callable(read_full_text):
                full_text = await read_full_text(item_key)
            saved += 1
            queue_result = self.queue.enqueue(
                literature_document(item, subscription, full_text=full_text),
                platform="literature",
            )
            self.seen.add(item)
            if queue_result.queued and queue_result.job:
                queued += 1
                if self.compiler is not None and auto_distill_enabled(self.queue):
                    self.run_store.update(run.id, status="distilling")
                    await asyncio.to_thread(self.compiler.run_codex, queue_result.job.id)
            path.unlink(missing_ok=True)
        status = (
            "waiting_school_login"
            if remaining
            else "waiting_confirmation"
            if queued
            else "completed"
        )
        return self.run_store.update(
            run.id,
            status=status,
            saved_zotero=run.saved_zotero + saved,
            queued=run.queued + queued,
        )

    def _save_handoff(self, run_id, subscription, item, result) -> None:
        root = self.state_root / "login-handoffs"
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{run_id}-{_safe_id(item)}.json"
        payload = {
            "run_id": run_id,
            "subscription_id": subscription.id,
            "subscription_name": subscription.name,
            "zotero_collection": subscription.zotero_collection,
            "item": asdict(item),
            "reason": result.get("status", "waiting_school_login"),
            "open_url": result.get("url") or item.url,
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8"
        )
        temporary.replace(path)


class SeenLiteratureStore:
    def __init__(self, root: Path):
        self.path = Path(root) / "literature-seen.json"

    def contains(self, item: LiteratureItem) -> bool:
        return bool(set(item.identity_keys) & self._read())

    def add(self, item: LiteratureItem) -> None:
        values = self._read() | set(item.identity_keys)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(sorted(values), ensure_ascii=False, indent=2) + "\n", "utf-8"
        )
        temporary.replace(self.path)

    def _read(self) -> set[str]:
        if not self.path.exists():
            return set()
        return set(json.loads(self.path.read_text("utf-8")))


def matches_subscription(item: LiteratureItem, subscription) -> bool:
    if not subscription.keywords:
        return True
    haystack = f"{item.title}\n{item.abstract}".casefold()
    return any(keyword.casefold() in haystack for keyword in subscription.keywords)


def literature_document(
    item: LiteratureItem, subscription, full_text: str = ""
) -> MarkdownDocument:
    evidence = "full_text" if full_text else "abstract" if item.abstract else "metadata"
    body = full_text or item.abstract or "No abstract was available; do not infer full-text findings."
    identifiers = []
    if item.doi:
        identifiers.append(f"> DOI: {item.doi}")
    if item.pmid:
        identifiers.append(f"> PMID: {item.pmid}")
    markdown = "\n\n".join(
        (
            "---\n"
            f"evidence_level: {evidence}\n"
            f"subscription: {subscription.name}\n"
            "---",
            f"# {item.title}",
            "\n".join(
                [
                    "> 来源平台: literature",
                    f"> 作者: {item.authors or '未识别'}",
                    f"> 原文链接: {item.url}",
                    *identifiers,
                ]
            ),
            "## 本订阅的提炼要求",
            subscription.requirement or "按医学文献默认提炼契约处理。",
            "## 可用证据",
            body,
        )
    )
    return MarkdownDocument(
        source_url=item.url or f"https://doi.org/{item.doi}",
        title=item.title,
        author=item.authors,
        published_at=item.published_at,
        markdown=markdown,
    )


def _safe_id(item: LiteratureItem) -> str:
    value = item.doi or item.pmid or item.openalex_id or str(abs(hash(item.url)))
    return "".join(character for character in value if character.isalnum())[:40]
