"""Orchestrate independent discovery, parsing, and knowledge queue layers."""

import asyncio
from datetime import date
import inspect
import re
import unicodedata

from extensions.processing.job_queue import QueueResult


class WeChatPipeline:
    def __init__(self, discoverer, parser, queue, compiler=None):
        self._discoverer = discoverer
        self._parser = parser
        self._queue = queue
        self._compiler = compiler

    async def run(self, accounts, per_account=10, date_from=None, date_to=None):
        results = []
        seen = set()
        for raw_account in accounts:
            account = str(raw_account).strip()
            if not account:
                continue
            try:
                links = await _discover(
                    self._discoverer,
                    [account],
                    per_account,
                    date_from,
                    date_to,
                )
            except Exception as exc:
                results.append(
                    QueueResult(
                        False,
                        "discovery_failed",
                        None,
                        account=account,
                        failed_step=str(getattr(exc, "step", "unknown")),
                        retry_from=str(
                            getattr(exc, "retry_from", "account_search")
                        ),
                        progress_kept=bool(getattr(exc, "progress_kept", False)),
                        error=str(exc),
                    )
                )
                continue
            for link in links:
                if link in seen:
                    continue
                seen.add(link)
                try:
                    document = await self._parser.parse(link)
                except Exception as exc:
                    results.append(
                        QueueResult(
                            False,
                            "parse_failed",
                            None,
                            account=account,
                            failed_step="parse_article",
                            retry_from="article_list",
                            progress_kept=True,
                            error=str(exc),
                        )
                    )
                    continue
                if _account_key(document.author) != _account_key(account):
                    results.append(QueueResult(False, "account_mismatch", None))
                    continue
                published = _document_date(document.published_at)
                if date_from is not None or date_to is not None:
                    if published is None:
                        results.append(QueueResult(False, "date_unverified", None))
                        continue
                    if date_from is not None and published < date_from:
                        results.append(QueueResult(False, "date_mismatch", None))
                        continue
                    if date_to is not None and published > date_to:
                        results.append(QueueResult(False, "date_mismatch", None))
                        continue
                result = self._queue.enqueue(document, platform="wechat")
                if result.queued and result.job and self._compiler is not None:
                    preview = self._compiler.prepare_clean_preview(result.job.id)
                    result = QueueResult(True, "preview_ready", preview)
                results.append(result)
        return tuple(results)


async def _discover(discoverer, accounts, per_account, date_from=None, date_to=None):
    method = discoverer.discover
    arguments = (accounts, per_account)
    keywords = {}
    if date_from is not None or date_to is not None:
        keywords = {"date_from": date_from, "date_to": date_to}
    if inspect.iscoroutinefunction(method):
        return await method(*arguments, **keywords)
    return await asyncio.to_thread(method, *arguments, **keywords)


def _account_key(value):
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", "", normalized).casefold()


def _document_date(value):
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    try:
        return date.fromisoformat(cleaned[:10])
    except ValueError:
        return None
