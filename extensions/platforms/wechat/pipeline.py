"""Orchestrate independent discovery, parsing, and knowledge queue layers."""

import asyncio
import inspect
import re
import unicodedata

from extensions.processing.job_queue import QueueResult


class WeChatPipeline:
    def __init__(self, discoverer, parser, queue):
        self._discoverer = discoverer
        self._parser = parser
        self._queue = queue

    async def run(self, accounts, per_account=10, date_from=None, date_to=None):
        results = []
        seen = set()
        for raw_account in accounts:
            account = str(raw_account).strip()
            if not account:
                continue
            links = await _discover(
                self._discoverer,
                [account],
                per_account,
                date_from,
                date_to,
            )
            for link in links:
                if link in seen:
                    continue
                seen.add(link)
                document = await self._parser.parse(link)
                if _account_key(document.author) != _account_key(account):
                    results.append(QueueResult(False, "account_mismatch", None))
                    continue
                results.append(self._queue.enqueue(document, platform="wechat"))
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
