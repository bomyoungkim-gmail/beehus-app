"""
Jobs Router - API endpoints for job management and triggering runs.
"""

import logging
from fastapi import APIRouter, HTTPException
from typing import List, Optional

from core.models.mongo_models import Job, Run, Credential
from core.tasks import scrape_task
from django_config import celery_app  # noqa: F401 – used by retry_run
from app.console.schemas import JobCreate, JobResponse, JobUpdate, RunResponse
from core.services.visual_processing import (
    build_script_from_processing_config,
    extract_visual_config_from_script,
)
from core.utils.date_utils import get_now

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

@router.post("/jobs", response_model=JobResponse)
async def create_job(job_in: JobCreate):
    """Create a new scraping job."""
    if job_in.credential_id:
        credential = await Credential.get(job_in.credential_id)
        if not credential:
            raise HTTPException(status_code=400, detail="Credential not found")
        if credential.workspace_id != job_in.workspace_id:
            raise HTTPException(
                status_code=400,
                detail="Credential must belong to the same workspace as the job",
            )
    elif job_in.connector == "itau_onshore_login":
        manual_agency = job_in.params.get("agencia")
        manual_account = job_in.params.get("conta_corrente") or job_in.params.get("conta")
        manual_username = job_in.params.get("username") or job_in.params.get("user")
        manual_password = job_in.params.get("password") or job_in.params.get("pass")
        if not all([manual_agency, manual_account, manual_username, manual_password]):
            raise HTTPException(
                status_code=400,
                detail="Itaú onshore manual jobs require username, password, agencia and conta",
            )

    job_payload = job_in.model_dump()
    processing_config = job_payload.get("processing_config_json")
    if processing_config is not None:
        generated_script, normalized_config = build_script_from_processing_config(processing_config)
        if not normalized_config:
            raise HTTPException(status_code=400, detail="Invalid processing_config_json payload.")
        if normalized_config.get("mode") == "advanced" and not generated_script:
            raise HTTPException(status_code=400, detail="Advanced processing script is empty.")
        job_payload["processing_config_json"] = normalized_config
        job_payload["processing_script"] = generated_script
    elif job_payload.get("processing_script"):
        script = str(job_payload["processing_script"]).strip()
        job_payload["processing_script"] = script
        visual_cfg = extract_visual_config_from_script(script)
        if visual_cfg:
            job_payload["processing_config_json"] = {"mode": "visual", "visual_config": visual_cfg}
        else:
            job_payload["processing_config_json"] = {"mode": "advanced", "advanced_script": script}

    job = Job(**job_payload)
    await job.save()
    return job


@router.get("/jobs", response_model=List[JobResponse])
async def list_jobs(workspace_id: Optional[str] = None):
    """List jobs, optionally filtered by workspace."""
    if workspace_id:
        return await Job.find(Job.workspace_id == workspace_id).to_list()
    return await Job.find_all().to_list()


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """Get job by ID."""
    job = await Job.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.patch("/jobs/{job_id}", response_model=JobResponse)
async def update_job(job_id: str, job_update: JobUpdate):
    """Update mutable fields for a job."""
    job = await Job.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job_update.enable_processing is not None:
        job.enable_processing = job_update.enable_processing
        if not job.enable_processing:
            job.processing_config_json = None
            job.processing_script = None

    if job_update.processing_config_json is not None:
        script, normalized = build_script_from_processing_config(job_update.processing_config_json)
        if not normalized:
            raise HTTPException(status_code=400, detail="Invalid processing_config_json payload.")
        if normalized.get("mode") == "advanced" and not script:
            raise HTTPException(status_code=400, detail="Advanced processing script is empty.")
        job.processing_config_json = normalized
        job.processing_script = script

    if job_update.processing_script is not None:
        script = job_update.processing_script.strip()
        job.processing_script = script or None
        if script:
            visual_cfg = extract_visual_config_from_script(script)
            if visual_cfg:
                job.processing_config_json = {"mode": "visual", "visual_config": visual_cfg}
            else:
                job.processing_config_json = {"mode": "advanced", "advanced_script": script}
        else:
            job.processing_config_json = None

    if job_update.sheet_aliases is not None:
        normalized_aliases = []
        seen: set[str] = set()
        for alias in job_update.sheet_aliases:
            value = (alias or "").strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized_aliases.append(value)
        job.sheet_aliases = normalized_aliases

    await job.save()
    return job


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job by ID."""
    job = await Job.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await job.delete()
    return {"message": f"Job {job_id} deleted successfully"}


@router.delete("/jobs")
async def delete_all_jobs(workspace_id: Optional[str] = None):
    """
    Delete all jobs, optionally filtered by workspace.
    Warning: This action is irreversible.
    """
    if workspace_id:
        delete_result = await Job.find(Job.workspace_id == workspace_id).delete()
    else:
        delete_result = await Job.delete_all()
    count = delete_result.deleted_count if delete_result else 0
    return {"message": f"Deleted {count} jobs"}


# ---------------------------------------------------------------------------
# Run triggers (belong with jobs since they reference job_id in the path)
# ---------------------------------------------------------------------------

@router.post("/jobs/{job_id}/run", response_model=RunResponse)
async def trigger_run(job_id: str):
    """Trigger a job run. Creates a Run document and dispatches to Celery worker."""
    job = await Job.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "active":
        raise HTTPException(status_code=400, detail="Job is not active")

    run = Run(job_id=job.id, job_name=job.name, connector=job.connector, status="queued")
    await run.save()

    execution_params = _build_execution_params(job)
    task = scrape_task.delay(
        job_id=job.id,
        run_id=str(run.id),
        workspace_id=job.workspace_id,
        connector_name=job.connector,
        params=execution_params,
    )
    run.celery_task_id = task.id
    await run.save()
    return run


@router.post("/jobs/{job_id}/run/{run_id}/retry", response_model=RunResponse)
async def retry_run(job_id: str, run_id: str):
    """Retry a failed run."""
    job = await Job.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    run = await Run.get(run_id)
    if not run or run.job_id != job.id:
        raise HTTPException(status_code=404, detail="Run not found for this job")

    run.attempt += 1
    run.status = "queued"
    run.error_summary = None
    run.started_at = None
    run.finished_at = None
    run.processing_status = "not_required"
    run.selected_filename = None
    run.selected_sheet = None
    run.processing_error = None
    if not run.connector and job:
        run.connector = job.connector
    if not run.job_name and job:
        run.job_name = job.name
    await run.save()

    execution_params = _build_execution_params(job)
    task = scrape_task.delay(
        job_id=job.id,
        run_id=str(run.id),
        workspace_id=job.workspace_id,
        connector_name=job.connector,
        params=execution_params,
    )
    run.celery_task_id = task.id
    await run.save()
    return run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_execution_params(job: Job) -> dict:
    """Merge job-level export/date config into the params dict."""
    params = job.params.copy()
    params.update({
        "export_holdings": job.export_holdings,
        "export_history": job.export_history,
        "date_mode": job.date_mode,
        "holdings_lag_days": job.holdings_lag_days,
        "history_lag_days": job.history_lag_days,
        "holdings_date": job.holdings_date,
        "history_date": job.history_date,
    })
    return params
