"""Review-gated knowledge compilation endpoints."""

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
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


@router.get("/knowledge/jobs", summary="List local knowledge jobs")
async def list_knowledge_jobs(status: str | None = Query(default=None)):
    jobs = KnowledgeJobStore().list(status=status)
    return {"jobs": [_public_job(job) for job in jobs]}


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
    summary="Reject a preview and delete its temporary source",
)
async def reject_preview(job_id: str):
    compiler = KnowledgeCompiler()
    try:
        job = compiler.reject(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"job": _public_job(job)}


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
        "wiki_updates": list(job.wiki_updates),
        "error": job.error,
    }
