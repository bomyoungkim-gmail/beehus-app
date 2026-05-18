"""
Jobs Router - API endpoints for job management and triggering runs.
"""

import logging
import unicodedata
import os
import socket
from fastapi import APIRouter, HTTPException, Request
from typing import List, Optional

from core.models.mongo_models import Job, Run, Credential
from core.tasks import scrape_task
from core.connectors.registry import ConnectorRegistry
from django_config import celery_app  # noqa: F401 – used by retry_run
from app.console.schemas import (
    JobCreate,
    JobResponse,
    JobUpdate,
    ProcessingScriptPreviewRequest,
    ProcessingScriptPreviewResponse,
    RunResponse,
)
from core.services.visual_processing import (
    build_script_from_processing_config,
    extract_visual_config_from_script,
)
from core.utils.date_utils import get_now
from core.services.run_state import run_state

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])


def _normalize_connector_name(raw_name: Optional[str]) -> str:
    """Normalize connector names to prevent hidden-char and whitespace mismatches."""
    if raw_name is None:
        return ""
    name = str(raw_name)
    name = "".join(ch for ch in name if unicodedata.category(ch) != "Cf")
    return name.strip()


def _validate_connector_or_400(connector_name: str) -> None:
    """Validate connector exists in registry before scheduling a run."""
    try:
        ConnectorRegistry.get_connector(connector_name)
    except ValueError as exc:
        available = sorted(getattr(ConnectorRegistry, "_registry", {}).keys())
        raise HTTPException(
            status_code=400,
            detail={
                "error": str(exc),
                "connector": connector_name,
                "available_connectors": available,
            },
        ) from exc


def _runtime_identity() -> str:
    host = os.getenv("HOSTNAME") or socket.gethostname()
    mongo_db = os.getenv("MONGO_DB_NAME", "-")
    return f"api_host={host} mongo_db={mongo_db}"


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

@router.post(
    "/jobs/processing/preview-script",
    response_model=ProcessingScriptPreviewResponse,
)
async def preview_processing_script(payload: ProcessingScriptPreviewRequest):
    """Validate processing config and return generated script + normalized config."""
    script, normalized_config = build_script_from_processing_config(payload.processing_config_json)
    if not normalized_config:
        raise HTTPException(status_code=400, detail="Invalid processing_config_json payload.")
    if normalized_config.get("mode") == "advanced" and not script:
        raise HTTPException(status_code=400, detail="Advanced processing script is empty.")
    return ProcessingScriptPreviewResponse(script=script, processing_config_json=normalized_config)

@router.post("/jobs", response_model=JobResponse)
async def create_job(job_in: JobCreate):
    """Create a new scraping job."""
    normalized_connector = _normalize_connector_name(job_in.connector)
    if not normalized_connector:
        raise HTTPException(status_code=400, detail="Connector is required")
    _validate_connector_or_400(normalized_connector)

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
    job_payload["connector"] = normalized_connector
    processing_config = job_payload.get("processing_config_json")
    if processing_config is not None:
        generated_script, normalized_config = _normalize_processing_config(processing_config)
        job_payload["processing_config_json"] = normalized_config
        job_payload["processing_script"] = generated_script
    elif job_payload.get("processing_script"):
        script = str(job_payload["processing_script"]).strip()
        job_payload["processing_script"] = script
        job_payload["processing_config_json"] = _derive_processing_config_from_script(script)

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
        script, normalized = _normalize_processing_config(job_update.processing_config_json)
        job.processing_config_json = normalized
        job.processing_script = script

    if job_update.processing_script is not None:
        script = job_update.processing_script.strip()
        job.processing_script = script or None
        if script:
            job.processing_config_json = _derive_processing_config_from_script(script)
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
async def trigger_run(job_id: str, request: Request):
    """Trigger a job run. Creates a Run document and dispatches to Celery worker."""
    job = await Job.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "active":
        raise HTTPException(status_code=400, detail="Job is not active")

    connector_name = _normalize_connector_name(job.connector)
    if not connector_name:
        raise HTTPException(status_code=400, detail="Job connector is empty")
    _validate_connector_or_400(connector_name)
    if connector_name != (job.connector or ""):
        original_connector = job.connector
        job.connector = connector_name
        await job.save()
        logger.info("Normalized connector for job %s from %r to %r", job.id, original_connector, connector_name)

    client_trace_id = (
        request.headers.get("X-Beehus-Client-Trace")
        or request.headers.get("X-Request-ID")
        or "-"
    )
    client_time = request.headers.get("X-Beehus-Client-Time") or "-"

    run = Run(job_id=job.id, job_name=job.name, connector=connector_name, status="queued")
    run.logs.append(
        f"[{get_now().time()}] 🧭 Trigger accepted: client_trace_id={client_trace_id} "
        f"client_time={client_time} connector={connector_name} {_runtime_identity()}"
    )
    await run.save()
    persisted_run = await Run.get(str(run.id))
    if not persisted_run:
        logger.error(
            "Run registration failed before enqueue: run_id=%s job_id=%s connector=%s host=%s mongo_db=%s",
            run.id,
            job.id,
            connector_name,
            os.getenv("HOSTNAME", "-"),
            os.getenv("MONGO_DB_NAME", "-"),
        )
        raise HTTPException(status_code=500, detail="Failed to register run before enqueue")
    logger.info(
        "Run registered: run_id=%s job_id=%s connector=%s host=%s mongo_db=%s",
        run.id,
        job.id,
        connector_name,
        os.getenv("HOSTNAME", "-"),
        os.getenv("MONGO_DB_NAME", "-"),
    )

    execution_params = _build_execution_params(job)
    task = scrape_task.delay(
        job_id=job.id,
        run_id=str(run.id),
        workspace_id=job.workspace_id,
        connector_name=connector_name,
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
    run.error_summary = None
    run.started_at = None
    run.finished_at = None
    run.updated_at = get_now()
    run.processing_status = "not_required"
    run.selected_filename = None
    run.selected_sheet = None
    run.processing_error = None
    if not run.connector and job:
        run.connector = job.connector
    if not run.job_name and job:
        run.job_name = job.name
    await run.save()

    connector_name = _normalize_connector_name(job.connector)
    if not connector_name:
        raise HTTPException(status_code=400, detail="Job connector is empty")
    _validate_connector_or_400(connector_name)
    if connector_name != (job.connector or ""):
        original_connector = job.connector
        job.connector = connector_name
        await job.save()
        logger.info("Normalized connector for job %s from %r to %r", job.id, original_connector, connector_name)
    run_connector_normalized = _normalize_connector_name(run.connector)
    if run_connector_normalized and run_connector_normalized != (run.connector or ""):
        original_run_connector = run.connector
        run.connector = run_connector_normalized
        await run.save()
        logger.info("Normalized connector for run %s from %r to %r", run.id, original_run_connector, run_connector_normalized)

    execution_params = _build_execution_params(job)
    task = scrape_task.delay(
        job_id=job.id,
        run_id=str(run.id),
        workspace_id=job.workspace_id,
        connector_name=connector_name,
        params=execution_params,
    )
    run.celery_task_id = task.id
    await run.save()
    await run_state.save_run_status(str(run.id), "queued", force=True)
    persisted_run = await Run.get(str(run.id))
    if not persisted_run:
        logger.error(
            "Run registration lost after retry enqueue: run_id=%s job_id=%s connector=%s host=%s mongo_db=%s",
            run.id,
            job.id,
            connector_name,
            os.getenv("HOSTNAME", "-"),
            os.getenv("MONGO_DB_NAME", "-"),
        )
        raise HTTPException(status_code=500, detail="Run missing after retry enqueue")
    logger.info(
        "Run retry re-queued: run_id=%s job_id=%s connector=%s task_id=%s host=%s mongo_db=%s",
        run.id,
        job.id,
        connector_name,
        run.celery_task_id,
        os.getenv("HOSTNAME", "-"),
        os.getenv("MONGO_DB_NAME", "-"),
    )
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


def _normalize_processing_config(processing_config: dict) -> tuple[str, dict]:
    script, normalized_config = build_script_from_processing_config(processing_config)
    if not normalized_config:
        raise HTTPException(status_code=400, detail="Invalid processing_config_json payload.")
    if normalized_config.get("mode") == "advanced" and not script:
        raise HTTPException(status_code=400, detail="Advanced processing script is empty.")
    return script, normalized_config


def _derive_processing_config_from_script(script: str) -> dict:
    visual_cfg = extract_visual_config_from_script(script)
    if visual_cfg:
        return {"mode": "visual", "visual_config": visual_cfg}
    return {"mode": "advanced", "advanced_script": script}
