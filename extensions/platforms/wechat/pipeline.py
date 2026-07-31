"""Orchestrate independent discovery, parsing, and knowledge queue layers."""

import asyncio


class WeChatPipeline:
    def __init__(self, discoverer, parser, queue):
        self._discoverer = discoverer
        self._parser = parser
        self._queue = queue

    async def run(self, accounts, per_account=10):
        links = await asyncio.to_thread(
            self._discoverer.discover,
            accounts,
            per_account,
        )
        results = []
        for link in links:
            document = await self._parser.parse(link)
            results.append(self._queue.enqueue(document, platform="wechat"))
        return tuple(results)
