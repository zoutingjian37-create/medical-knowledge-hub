"""Platform discovery, health checks, and safe single-item reads."""

import asyncio
from dataclasses import asdict
from datetime import date
import inspect
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from extensions.platforms.base import PlatformError
from extensions.platforms.registry import platform_registry
from extensions.platforms.wechat.discovery import (
    OpenCLIWeChatDiscoverer,
    WeChatDiscoveryError,
    WeChatUIDiscoverer,
)
from extensions.platforms.wechat.parser import OpenCLIWeChatParser
from extensions.platforms.wechat.pipeline import WeChatPipeline
from extensions.platforms.url_router import detect_platform
from extensions.processing.documents import from_normalized
from extensions.processing.job_queue import KnowledgeJobQueue, QueueResult


router = APIRouter()


@router.get("/platforms", summary="查看平台注册与安装状态")
async def list_platforms():
    return {
        "platforms": [item.to_dict() for item in platform_registry.list_platforms()]
    }


class PlatformFetchRequest(BaseModel):
    url: str = Field(min_length=10, max_length=2048)


class WeChatDiscoverRequest(BaseModel):
    accounts: list[str] = Field(min_length=1, max_length=20)
    per_account: int = Field(default=10, ge=1, le=50)
    mode: Literal["public", "wechat_ui"] = "wechat_ui"
    date_from: date | None = None
    date_to: date | None = None


@router.post(
    "/platforms/wechat/discover",
    summary="Discover public WeChat article links",
)
async def discover_wechat_links(request: WeChatDiscoverRequest):
    discoverer = _wechat_discoverer(request.mode)
    try:
        links = await _discover_links(
            discoverer,
            request.accounts,
            request.per_account,
            request.date_from,
            request.date_to,
        )
    except WeChatDiscoveryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"links": list(links), "mode": request.mode}


@router.post(
    "/platforms/wechat/collect",
    summary="Discover, parse, clean, and queue WeChat articles",
)
async def collect_wechat_articles(request: WeChatDiscoverRequest):
    pipeline = WeChatPipeline(
        discoverer=_wechat_discoverer(request.mode),
        parser=OpenCLIWeChatParser(),
        queue=KnowledgeJobQueue(),
    )
    try:
        if request.date_from is None and request.date_to is None:
            results = await pipeline.run(request.accounts, request.per_account)
        else:
            results = await pipeline.run(
                request.accounts,
                request.per_account,
                date_from=request.date_from,
                date_to=request.date_to,
            )
    except (RuntimeError, ValueError, WeChatDiscoveryError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "results": [_queue_payload(result) for result in results],
        "mode": request.mode,
    }


@router.post(
    "/platforms/queue",
    summary="Detect and queue one supported public link for knowledge distillation",
)
async def queue_public_content(request: PlatformFetchRequest):
    try:
        platform = detect_platform(request.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        if platform == "wechat":
            document = await OpenCLIWeChatParser().parse(request.url)
        else:
            adapter = _adapter_or_404(platform)
            item_builder = getattr(adapter, "item_ref_from_url", None)
            if not item_builder:
                raise HTTPException(status_code=400, detail="该平台暂不支持链接读取")
            reference = item_builder(request.url)
            health = await adapter.health()
            if not health.available:
                raise HTTPException(status_code=503, detail=health.detail)
            raw = await adapter.fetch_item(reference)
            document = from_normalized(adapter.normalize_item(raw))
        result = KnowledgeJobQueue().enqueue(document, platform=platform)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (PlatformError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"platform": platform, **_queue_payload(result)}


@router.post(
    "/platforms/wechat/queue",
    summary="Legacy alias for the shared public-link queue",
)
async def queue_wechat_article(request: PlatformFetchRequest):
    return await queue_public_content(request)


@router.get("/platforms/{platform_key}/health", summary="检查平台采集连接")
async def platform_health(platform_key: str):
    adapter = _adapter_or_404(platform_key)
    health = await adapter.health()
    return {"platform": platform_key, **asdict(health)}


@router.post("/platforms/{platform_key}/fetch", summary="测试读取单条公开内容")
async def fetch_platform_item(platform_key: str, request: PlatformFetchRequest):
    adapter = _adapter_or_404(platform_key)
    item_builder = getattr(adapter, "item_ref_from_url", None)
    if not item_builder:
        raise HTTPException(status_code=400, detail="该平台暂不支持链接读取")
    try:
        reference = item_builder(request.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    health = await adapter.health()
    if not health.available:
        raise HTTPException(status_code=503, detail=health.detail)
    try:
        raw = await adapter.fetch_item(reference)
        normalized = adapter.normalize_item(raw)
    except PlatformError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    payload = asdict(normalized)
    if normalized.published_at:
        payload["published_at"] = normalized.published_at.isoformat()
    return {"content": payload}


def _adapter_or_404(platform_key: str):
    try:
        return platform_registry.get_adapter(platform_key)
    except (KeyError, LookupError) as exc:
        raise HTTPException(status_code=404, detail="未知或未安装的平台") from exc


def _queue_payload(result: QueueResult) -> dict:
    job = result.job
    return {
        "queued": result.queued,
        "reason": result.reason,
        "job_id": job.id if job else "",
        "status": job.status if job else "skipped",
        "source_url": job.source_url if job else "",
        "title": job.title if job else "",
        "author": job.author if job else "",
    }


def _wechat_discoverer(mode: str):
    if mode == "wechat_ui":
        return WeChatUIDiscoverer()
    return OpenCLIWeChatDiscoverer()


async def _discover_links(
    discoverer, accounts, per_account, date_from=None, date_to=None
):
    method = discoverer.discover
    arguments = (accounts, per_account)
    keywords = {}
    if date_from is not None or date_to is not None:
        keywords = {"date_from": date_from, "date_to": date_to}
    if inspect.iscoroutinefunction(method):
        return await method(*arguments, **keywords)
    return await asyncio.to_thread(method, *arguments, **keywords)
