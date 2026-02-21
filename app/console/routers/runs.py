"""
Runs Router - API endpoints for accessing and controlling runs.
"""

import logging
from fastapi import APIRouter, HTTPException
from typing import List, Optional

from core.models.mongo_models import Run
from app.console.schemas import RunResponse
from core.utils.date_utils import get_now
from django_config import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(tags=["runs"])


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
    run = await Run.get(run_id)
    if not run:
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

    run.status = "failed"
    run.error_summary = "Cancelled by user"
    run.logs.append(f"[{get_now().time()}] 🛑 Run cancelled by user")
    run.finished_at = get_now()
    await run.save()
    return {"message": f"Run {run_id} stopped successfully", "run_id": run_id}
