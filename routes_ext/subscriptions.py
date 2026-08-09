"""Local subscription and automation settings API."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from extensions.subscriptions.store import SubscriptionStore
from extensions.subscriptions.factory import build_subscription_runner
from extensions.subscriptions.runs import LiteratureRunStore
from extensions.subscriptions.task_scheduler import sync_windows_task
from extensions.subscriptions.zotero import ZoteroGateway


router = APIRouter()


class SubscriptionCreateRequest(BaseModel):
    kind: Literal["wechat_account", "journal", "feed", "literature_query"]
    name: str = Field(min_length=1, max_length=200)
    source: str = Field(default="", max_length=2000)
    query: str = Field(default="", max_length=2000)
    keywords: list[str] = Field(default_factory=list, max_length=100)
    requirement: str = Field(default="", max_length=5000)
    enabled: bool = True
    daily_limit: int = Field(default=5, ge=1, le=100)
    zotero_collection: str = Field(default="", max_length=200)


class SubscriptionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    source: str | None = Field(default=None, max_length=2000)
    query: str | None = Field(default=None, max_length=2000)
    keywords: list[str] | None = Field(default=None, max_length=100)
    requirement: str | None = Field(default=None, max_length=5000)
    enabled: bool | None = None
    daily_limit: int | None = Field(default=None, ge=1, le=100)
    zotero_collection: str | None = Field(default=None, max_length=200)


class WeChatAccountsRequest(BaseModel):
    accounts: list[str] = Field(default_factory=list, max_length=100)
    daily_limit: int = Field(default=5, ge=1, le=100)


class LiteratureSourcesRequest(BaseModel):
    sources: list[str] = Field(default_factory=list, max_length=100)
    daily_limit: int = Field(default=5, ge=1, le=100)


class AutomationRequest(BaseModel):
    enabled: bool | None = None
    run_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    daily_limit: int | None = Field(default=None, ge=1, le=100)
    catch_up: bool | None = None


class ImportRequest(BaseModel):
    format: str
    version: int
    subscriptions: list[dict]
    automation: dict


class RunRequest(BaseModel):
    subscription_id: str | None = None
    scope: Literal["all", "wechat", "literature"] = "all"
    date_from: date | None = None
    date_to: date | None = None


class ContinueLoginRequest(BaseModel):
    run_id: str


class RunSelectionRequest(BaseModel):
    run_ids: list[str] = Field(min_length=1, max_length=100)


@router.get("/subscriptions", summary="List personal subscriptions")
async def list_subscriptions():
    return {"subscriptions": [item.to_dict() for item in SubscriptionStore().list()]}


@router.post("/subscriptions", status_code=201, summary="Create a subscription")
async def create_subscription(request: SubscriptionCreateRequest):
    try:
        item = SubscriptionStore().create(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"subscription": item.to_dict()}


@router.get("/subscriptions/wechat-accounts", summary="List default WeChat accounts")
async def list_wechat_accounts():
    items = [
        item.to_dict()
        for item in SubscriptionStore().list()
        if item.kind == "wechat_account"
    ]
    return {"subscriptions": items}


@router.put("/subscriptions/wechat-accounts", summary="Replace default WeChat accounts")
async def replace_wechat_accounts(request: WeChatAccountsRequest):
    try:
        items = SubscriptionStore().sync_wechat_accounts(
            request.accounts, daily_limit=request.daily_limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"subscriptions": [item.to_dict() for item in items]}


@router.post("/subscriptions/literature-sources", summary="Add journal names or RSS sources")
async def add_literature_sources(request: LiteratureSourcesRequest):
    try:
        items = SubscriptionStore().add_literature_sources(
            request.sources, daily_limit=request.daily_limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"created": len(items), "subscriptions": [item.to_dict() for item in items]}


@router.get("/subscriptions/export", summary="Export personal subscription settings")
async def export_subscriptions():
    return SubscriptionStore().export_config()


@router.post("/subscriptions/import", summary="Import personal subscription settings")
async def import_subscriptions(request: ImportRequest):
    store = SubscriptionStore()
    try:
        store.import_config(request.model_dump())
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        scheduled_task = sync_windows_task(store.get_automation())
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    exported = store.export_config()
    exported["scheduled_task"] = scheduled_task
    return exported


@router.patch("/subscriptions/{subscription_id}", summary="Update a subscription")
async def update_subscription(subscription_id: str, request: SubscriptionUpdateRequest):
    changes = request.model_dump(exclude_none=True)
    try:
        item = SubscriptionStore().update(subscription_id, **changes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"subscription": item.to_dict()}


@router.delete("/subscriptions/{subscription_id}", status_code=204)
async def delete_subscription(subscription_id: str):
    try:
        SubscriptionStore().delete(subscription_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.get("/automation", summary="Read daily automation settings")
async def read_automation():
    return {"automation": SubscriptionStore().get_automation().to_dict()}


@router.put("/automation", summary="Update daily automation settings")
async def update_automation(request: AutomationRequest):
    try:
        settings = SubscriptionStore().update_automation(
            **request.model_dump(exclude_none=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        scheduled_task = sync_windows_task(settings)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"automation": settings.to_dict(), "scheduled_task": scheduled_task}


@router.get("/literature/runs", summary="List literature subscription runs")
async def list_literature_runs():
    runs = LiteratureRunStore()
    runs.purge_completed(max_age_days=14)
    return {"runs": [run.to_dict() for run in runs.list()]}


@router.delete("/literature/runs", summary="Delete selected local run-history records")
async def delete_literature_runs(request: RunSelectionRequest):
    deleted = LiteratureRunStore().delete_many(request.run_ids)
    return {"deleted_ids": list(deleted)}


@router.post("/literature/runs/retry-selected", summary="Retry selected failed subscription runs")
async def retry_selected_literature_runs(request: RunSelectionRequest):
    store = LiteratureRunStore()
    runner = build_subscription_runner()
    results = []
    skipped = []
    for run_id in dict.fromkeys(request.run_ids):
        try:
            previous = store.get(run_id)
        except KeyError:
            skipped.append({"run_id": run_id, "reason": "not_found"})
            continue
        if previous.status != "failed":
            skipped.append({"run_id": run_id, "reason": "not_failed"})
            continue
        try:
            date_from = date.fromisoformat(previous.date_from) if previous.date_from else None
            date_to = date.fromisoformat(previous.date_to) if previous.date_to else None
            results.append(
                await runner.run_one(
                    previous.subscription_id,
                    date_from=date_from,
                    date_to=date_to,
                )
            )
        except (KeyError, RuntimeError, ValueError) as exc:
            skipped.append({"run_id": run_id, "reason": "retry_failed", "error": str(exc)})
    return {
        "runs": [run.to_dict() for run in results],
        "skipped": skipped,
    }


@router.post("/literature/runs/run", summary="Run one subscription or all enabled subscriptions now")
async def run_literature_subscriptions(request: RunRequest):
    runner = build_subscription_runner()
    try:
        if request.subscription_id:
            if request.date_from is None and request.date_to is None:
                results = (await runner.run_one(request.subscription_id),)
            else:
                results = (
                    await runner.run_one(
                        request.subscription_id,
                        date_from=request.date_from,
                        date_to=request.date_to,
                    ),
                )
        else:
            if request.date_from is None and request.date_to is None:
                results = await runner.run_all_manual(scope=request.scope)
            else:
                results = await runner.run_all_manual(
                    scope=request.scope,
                    date_from=request.date_from,
                    date_to=request.date_to,
                )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"runs": [run.to_dict() for run in results]}


@router.post("/literature/runs/continue-login", summary="Continue after Zotero Connector save")
async def continue_literature_login(request: ContinueLoginRequest):
    try:
        run = await build_subscription_runner().continue_login(request.run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"run": run.to_dict()}


@router.get("/literature/runs/{run_id}/handoffs", summary="List user login handoffs")
async def list_login_handoffs(run_id: str):
    root = SubscriptionStore().root / "login-handoffs"
    values = []
    for path in sorted(root.glob(f"{run_id}-*.json")) if root.exists() else []:
        import json

        payload = json.loads(path.read_text("utf-8"))
        values.append(
            {
                "run_id": payload["run_id"],
                "subscription_name": payload["subscription_name"],
                "reason": payload["reason"],
                "open_url": payload["open_url"],
                "title": payload["item"]["title"],
                "doi": payload["item"].get("doi", ""),
                "zotero_collection": payload["zotero_collection"],
            }
        )
    return {"handoffs": values}


@router.get("/zotero/status", summary="Check Zotero local API and Connector")
async def zotero_status():
    return await ZoteroGateway().status()
