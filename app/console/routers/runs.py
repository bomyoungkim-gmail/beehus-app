"""
Runs Router - API endpoints for accessing and controlling runs.
"""

import logging
import unicodedata
from fastapi import APIRouter, HTTPException
from typing import List, Optional

from core.models.mongo_models import Run
from app.console.schemas import RunResponse
from django_config import celery_app
from core.services.run_state import run_state

logger = logging.getLogger(__name__)

router = APIRouter(tags=["runs"])


def _normalize_run_id(raw_run_id: str) -> str:
    """Normalize run id from URL to avoid hidden chars/whitespace mismatches."""
    value = str(raw_run_id or "")
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Cf")
    return value.strip()


@router.get("/runs", response_model=List[RunResponse])
async def list_runs(job_id: Optional[str] = None, status: Optional[str] = None):
    """List runs, optionally filtered by job_id and/or status."""
    query = Run.find()
    if job_id:
        query = query.find(Run.job_id == job_id)
    if status:
        query = query.find(Run.status == status)
    return await query.sort(-Run.created_at).to_list()


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str):
    """Get run by ID."""
    normalized_run_id = _normalize_run_id(run_id)
    run = await Run.get(normalized_run_id)
    if not run:
        recent_ids = [
            str(r.id)
            for r in await Run.find_all().sort(-Run.created_at).limit(3).to_list()
        ]
        logger.warning(
            "Run not found: requested=%r normalized=%r recent_ids=%s",
            run_id,
            normalized_run_id,
            recent_ids,
        )
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: str):
    """Stop/cancel a running or queued job."""
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status not in ["queued", "running"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot stop run with status '{run.status}'",
        )

    if run.celery_task_id:
        celery_app.control.revoke(run.celery_task_id, terminate=True)

    await run_state.mark_failed_with_log(
        run,
        reason="Cancelled by user",
        log_message="🛑 Run cancelled by user",
    )
    return {"message": f"Run {run_id} stopped successfully", "run_id": run_id}
