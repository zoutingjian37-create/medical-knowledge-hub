"""Local subscription and automation settings API."""

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


class ContinueLoginRequest(BaseModel):
    run_id: str


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
    return {"runs": [run.to_dict() for run in LiteratureRunStore().list()]}


@router.post("/literature/runs/run", summary="Run one subscription or all enabled subscriptions now")
async def run_literature_subscriptions(request: RunRequest):
    runner = build_subscription_runner()
    try:
        if request.subscription_id:
            results = (await runner.run_one(request.subscription_id),)
        else:
            results = await runner.run_all_manual()
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
