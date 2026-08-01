"""Apply global and per-subscription limits to enabled subscription runs."""

from dataclasses import replace


class SubscriptionRunner:
    def __init__(self, *, store, literature_pipeline, wechat_pipeline=None):
        self.store = store
        self.literature_pipeline = literature_pipeline
        self.wechat_pipeline = wechat_pipeline

    async def run_enabled(self):
        settings = self.store.get_automation()
        if not settings.enabled:
            return ()
        remaining = settings.daily_limit
        results = []
        for subscription in self.store.list():
            if not subscription.enabled or remaining <= 0:
                continue
            limit = min(subscription.daily_limit, remaining)
            limited = replace(subscription, daily_limit=limit)
            result = await self._pipeline(limited).run(limited)
            results.append(result)
            remaining -= limit
        return tuple(results)

    async def run_one(self, subscription_id: str):
        subscription = self.store.get(subscription_id)
        return await self._pipeline(subscription).run(subscription)

    async def run_all_manual(self):
        results = []
        remaining = self.store.get_automation().daily_limit
        for subscription in self.store.list():
            if not subscription.enabled or remaining <= 0:
                continue
            limited = replace(
                subscription, daily_limit=min(subscription.daily_limit, remaining)
            )
            results.append(await self._pipeline(limited).run(limited))
            remaining -= limited.daily_limit
        return tuple(results)

    async def continue_login(self, run_id: str):
        run = self.literature_pipeline.run_store.get(run_id)
        subscription = self.store.get(run.subscription_id)
        return await self.literature_pipeline.continue_login(run_id, subscription)

    def _pipeline(self, subscription):
        if subscription.kind == "wechat_account":
            if self.wechat_pipeline is None:
                raise RuntimeError("WeChat subscription pipeline is unavailable")
            return self.wechat_pipeline
        return self.literature_pipeline


class WeChatSubscriptionPipeline:
    def __init__(self, *, discoverer, parser, queue, compiler, run_store):
        self.discoverer = discoverer
        self.parser = parser
        self.queue = queue
        self.compiler = compiler
        self.run_store = run_store

    async def run(self, subscription):
        from extensions.platforms.wechat.pipeline import WeChatPipeline

        run = self.run_store.create(subscription.id)
        try:
            results = await WeChatPipeline(
                self.discoverer, self.parser, self.queue
            ).run(
                [subscription.source or subscription.name],
                per_account=subscription.daily_limit,
            )
            queued = 0
            for result in results:
                if result.queued and result.job:
                    queued += 1
                    self.run_store.update(run.id, status="distilling")
                    import asyncio

                    await asyncio.to_thread(self.compiler.run_codex, result.job.id)
            return self.run_store.update(
                run.id,
                status="waiting_confirmation" if queued else "completed",
                discovered=len(results),
                filtered=queued,
                queued=queued,
            )
        except Exception as exc:
            self.run_store.update(run.id, status="failed", error=str(exc))
            raise
