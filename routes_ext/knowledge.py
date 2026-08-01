"""Review-gated knowledge compilation endpoints."""

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from extensions.processing.compiler import (
    CodexExecutionError,
    KnowledgeCompiler,
    PreviewValidationError,
)
from extensions.processing.job_store import KnowledgeJob, KnowledgeJobStore


router = APIRouter()


class PreviewRequest(BaseModel):
    markdown: str = Field(min_length=50, max_length=100_000)
    wiki_updates: list[str] = Field(default_factory=list, max_length=50)


class TrashSettingsRequest(BaseModel):
    retention_days: int = Field(ge=1, le=30)


class KnowledgeSettingsRequest(BaseModel):
    auto_distill: bool


@router.get("/knowledge/jobs", summary="List local knowledge jobs")
async def list_knowledge_jobs(status: str | None = Query(default=None)):
    compiler = KnowledgeCompiler()
    compiler.purge_expired_trash()
    jobs = compiler.store.list(status=status)
    return {"jobs": [_public_job(job) for job in jobs]}


@router.get("/knowledge/trash", summary="List jobs in the local recycle bin")
async def list_knowledge_trash():
    compiler = KnowledgeCompiler()
    compiler.purge_expired_trash()
    return {
        "jobs": [_public_job(job) for job in compiler.store.list_trash()],
        "retention_days": compiler.store.get_trash_retention_days(),
    }


@router.put("/knowledge/trash/settings", summary="Set recycle bin retention")
async def update_trash_settings(request: TrashSettingsRequest):
    retention = KnowledgeJobStore().set_trash_retention_days(request.retention_days)
    return {"retention_days": retention}


@router.get("/knowledge/settings", summary="Read local knowledge workflow settings")
async def read_knowledge_settings():
    return {"auto_distill": KnowledgeJobStore().get_auto_distill_enabled()}


@router.put("/knowledge/settings", summary="Update local knowledge workflow settings")
async def update_knowledge_settings(request: KnowledgeSettingsRequest):
    enabled = KnowledgeJobStore().set_auto_distill_enabled(request.auto_distill)
    return {"auto_distill": enabled}


@router.get(
    "/knowledge/jobs/{job_id}/preview",
    summary="Read a generated knowledge preview",
)
async def read_preview(job_id: str):
    try:
        job = KnowledgeJobStore().get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not job.preview_path or not Path(job.preview_path).exists():
        raise HTTPException(status_code=409, detail="knowledge preview is not ready")
    return {"job": _public_job(job), "markdown": Path(job.preview_path).read_text("utf-8")}


@router.post(
    "/knowledge/jobs/{job_id}/handoff",
    summary="Prepare one job for Codex distillation",
)
async def prepare_handoff(job_id: str):
    compiler = KnowledgeCompiler()
    try:
        result = compiler.prepare_handoff(job_id)
        job = compiler.store.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "job": _public_job(job),
        "mode": result.mode,
        "instruction": result.instruction,
    }


@router.post(
    "/knowledge/jobs/{job_id}/compile",
    summary="Generate a knowledge preview with the local Codex CLI",
)
async def compile_with_codex(job_id: str):
    compiler = KnowledgeCompiler()
    try:
        job = await asyncio.to_thread(compiler.run_codex, job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CodexExecutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"job": _public_job(job)}


@router.post(
    "/knowledge/jobs/{job_id}/preview",
    summary="Store a Codex-generated preview without changing Obsidian",
)
async def accept_preview(job_id: str, request: PreviewRequest):
    compiler = KnowledgeCompiler()
    try:
        job = compiler.accept_preview(
            job_id,
            request.markdown,
            request.wiki_updates,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PreviewValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"job": _public_job(job)}


@router.post(
    "/knowledge/jobs/{job_id}/import-preview",
    summary="Import a preview written to the Codex handoff output",
)
async def import_preview(job_id: str):
    compiler = KnowledgeCompiler()
    try:
        job = compiler.import_preview(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PreviewValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"job": _public_job(job)}


@router.post(
    "/knowledge/jobs/{job_id}/approve",
    summary="Apply an approved preview to Obsidian",
)
async def approve_preview(job_id: str):
    vault = os.getenv("OBSIDIAN_VAULT_PATH", "").strip()
    if not vault:
        raise HTTPException(status_code=409, detail="Obsidian Vault is not configured")
    compiler = KnowledgeCompiler()
    try:
        result = compiler.approve(job_id, Path(vault))
        job = compiler.store.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (FileNotFoundError, PreviewValidationError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "job": _public_job(job),
        "knowledge_card": str(result.knowledge_card),
        "updated_pages": [str(path) for path in result.updated_pages],
    }


@router.post(
    "/knowledge/jobs/{job_id}/reject",
    summary="Compatibility alias for moving a job to the recycle bin",
)
async def reject_preview(job_id: str):
    compiler = KnowledgeCompiler()
    try:
        job = compiler.trash(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"job": _public_job(job)}


@router.post(
    "/knowledge/jobs/{job_id}/trash",
    summary="Move a job to the local recycle bin",
)
async def trash_job(job_id: str):
    compiler = KnowledgeCompiler()
    try:
        job = compiler.trash(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"job": _public_job(job)}


@router.post(
    "/knowledge/jobs/{job_id}/restore",
    summary="Restore a job from the local recycle bin",
)
async def restore_job(job_id: str):
    compiler = KnowledgeCompiler()
    try:
        job = compiler.restore(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PreviewValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"job": _public_job(job)}


@router.delete(
    "/knowledge/jobs/{job_id}",
    status_code=204,
    summary="Permanently delete one local recycled job",
)
async def permanently_delete_job(job_id: str):
    compiler = KnowledgeCompiler()
    try:
        compiler.delete_permanently(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PreviewValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=204)


def _public_job(job: KnowledgeJob) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "source_url": job.source_url,
        "title": job.title,
        "author": job.author,
        "published_at": job.published_at,
        "platform": job.platform,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "deleted_at": job.deleted_at or (job.updated_at if job.status == "rejected" else ""),
        "wiki_updates": list(job.wiki_updates),
        "error": job.error,
    }
