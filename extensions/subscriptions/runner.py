"""Apply global and per-subscription limits to enabled subscription runs."""

from dataclasses import replace
from datetime import date, datetime

from extensions.platforms.wechat.vision import SHANGHAI_TZ

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
            if not subscription.enabled:
                continue
            if subscription.kind == "wechat_account":
                results.append(await self._pipeline(subscription).run(subscription))
                continue
            if remaining <= 0:
                continue
            limit = min(subscription.daily_limit, remaining)
            limited = replace(subscription, daily_limit=limit)
            result = await self._pipeline(limited).run(limited)
            results.append(result)
            remaining -= limit
        return tuple(results)

    async def run_one(self, subscription_id: str, *, date_from=None, date_to=None):
        subscription = self.store.get(subscription_id)
        if subscription.kind == "wechat_account":
            return await self._run_wechat_manual(
                subscription, date_from=date_from, date_to=date_to
            )
        return await self._pipeline(subscription).run(subscription)

    async def run_all_manual(self, scope: str = "all", *, date_from=None, date_to=None):
        results = []
        remaining = self.store.get_automation().daily_limit
        for subscription in self.store.list():
            if (
                not subscription.enabled
                or not _matches_scope(subscription.kind, scope)
            ):
                continue
            if subscription.kind == "wechat_account":
                results.append(
                    await self._run_wechat_manual(
                        subscription, date_from=date_from, date_to=date_to
                    )
                )
                continue
            if remaining <= 0:
                continue
            limited = replace(
                subscription, daily_limit=min(subscription.daily_limit, remaining)
            )
            results.append(await self._pipeline(limited).run(limited))
            remaining -= limited.daily_limit
        return tuple(results)

    async def _run_wechat_manual(self, subscription, *, date_from=None, date_to=None):
        pipeline = self._pipeline(subscription)
        method = getattr(pipeline, "run_manual", None)
        if method is None:
            return await pipeline.run(subscription)
        return await method(subscription, date_from=date_from, date_to=date_to)

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
    def __init__(
        self,
        *,
        discoverer,
        parser,
        queue,
        compiler,
        run_store,
        subscription_store=None,
        now_provider=None,
    ):
        self.discoverer = discoverer
        self.parser = parser
        self.queue = queue
        self.compiler = compiler
        self.run_store = run_store
        self.subscription_store = subscription_store
        self.now_provider = now_provider or (lambda: datetime.now(SHANGHAI_TZ))

    async def run(self, subscription):
        return await self._run(subscription, catch_up=True)

    async def run_manual(self, subscription, *, date_from=None, date_to=None):
        return await self._run(
            subscription,
            date_from=date_from,
            date_to=date_to,
            catch_up=False,
        )

    async def _run(
        self,
        subscription,
        *,
        date_from=None,
        date_to=None,
        catch_up: bool,
    ):
        from extensions.platforms.wechat.pipeline import WeChatPipeline

        run = self.run_store.create(subscription.id)
        try:
            today = self.now_provider().astimezone(SHANGHAI_TZ).date()
            cursor = str(getattr(subscription, "last_successful_date", "") or "")
            resolved_to = date_to or today
            resolved_from = date_from
            if resolved_from is None:
                resolved_from = date.fromisoformat(cursor) if catch_up and cursor else resolved_to
            if resolved_from > resolved_to:
                raise ValueError("date_from must not be after date_to")
            results = await WeChatPipeline(
                self.discoverer, self.parser, self.queue, self.compiler
            ).run(
                [subscription.source or subscription.name],
                per_account=subscription.daily_limit,
                date_from=resolved_from,
                date_to=resolved_to,
            )
            article_results = tuple(
                result
                for result in results
                if result.reason not in {"discovery_failed", "parse_failed"}
            )
            queued = 0
            for result in article_results:
                if result.queued and result.job:
                    queued += 1
            pipeline_failure = next(
                (
                    result
                    for result in results
                    if result.reason in {"discovery_failed", "parse_failed"}
                ),
                None,
            )
            discovery_status = getattr(self.discoverer, "last_status", None)
            complete = bool(getattr(discovery_status, "complete", True)) and not pipeline_failure
            warning = str(getattr(discovery_status, "warning", "") or "")
            if pipeline_failure is not None:
                warning = pipeline_failure.error or pipeline_failure.reason
            failed_step = str(getattr(discovery_status, "failed_step", "") or "")
            retry_from = str(getattr(discovery_status, "retry_from", "") or "")
            progress_kept = bool(getattr(discovery_status, "progress_kept", False))
            if pipeline_failure is not None:
                failed_step = pipeline_failure.failed_step
                retry_from = pipeline_failure.retry_from
                progress_kept = pipeline_failure.progress_kept
            completed = self.run_store.update(
                run.id,
                status=(
                    "failed"
                    if not complete
                    else "waiting_confirmation" if queued else "completed"
                ),
                discovered=len(article_results),
                filtered=max(0, len(article_results) - queued),
                queued=queued,
                error=warning if not complete else "",
                account_name=subscription.source or subscription.name,
                date_from=resolved_from.isoformat(),
                date_to=resolved_to.isoformat(),
                failed_step=failed_step if not complete else "",
                retry_from=retry_from if not complete else "",
                progress_kept=progress_kept if not complete else False,
            )
            if complete and self.subscription_store is not None:
                cursor_date = date.fromisoformat(cursor) if cursor else None
                successful_date = max(
                    item for item in (cursor_date, resolved_to) if item is not None
                )
                self.subscription_store.update(
                    subscription.id,
                    last_successful_date=successful_date.isoformat(),
                )
            return completed
        except Exception as exc:
            return self.run_store.update(
                run.id,
                status="failed",
                error=str(exc),
                account_name=subscription.source or subscription.name,
                failed_step=str(getattr(exc, "step", "unknown")),
                retry_from=str(getattr(exc, "retry_from", "account_search")),
                progress_kept=bool(getattr(exc, "progress_kept", False)),
            )


def _matches_scope(kind: str, scope: str) -> bool:
    if scope == "all":
        return True
    if scope == "wechat":
        return kind == "wechat_account"
    if scope == "literature":
        return kind != "wechat_account"
    raise ValueError(f"unsupported subscription scope: {scope}")
