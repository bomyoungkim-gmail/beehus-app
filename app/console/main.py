"""
App Console API - FastAPI application for managing workspaces, jobs, and runs.
Migrated to use Beanie (MongoDB) and Celery for task execution.
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from cryptography.fernet import Fernet
import os
import asyncio
import json
import redis.asyncio as redis
from typing import List
from datetime import datetime
from core.utils.date_utils import get_now

from core.db import init_db, close_db
from core.config import settings
from core.models.mongo_models import Workspace, InboxIntegration, OtpRule, Job, Run, OtpAudit, Credential
from core.tasks import scrape_task
from core.services.user_service import ensure_admin_exists
from django_config import celery_app
from core.schemas.otp import (
    WorkspaceCreate, WorkspaceResponse,
    InboxIntegrationCreate, InboxIntegrationResponse,
    OtpRuleCreate, OtpRuleResponse
)
from app.console.schemas import JobCreate, JobResponse, RunResponse
from app.console.websockets import ConnectionManager

# WebSocket Manager
manager = ConnectionManager()

# Background Redis Listener
async def redis_listener():
    """
    Subscribes to Redis 'run_updates' channel and broadcasts messages to WebSockets.
    """
    try:
        r = redis.from_url(settings.REDIS_URL)
        pubsub = r.pubsub()
        await pubsub.subscribe("run_updates")
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                
                try:
                    payload = json.loads(data)
                    await manager.broadcast(payload)
                except json.JSONDecodeError:
                    print(f"Failed to decode Redis message: {data}")
                    
    except asyncio.CancelledError:
        # Task cancelled on shutdown
        pass
    except Exception as e:
        print(f"Redis listener error: {e}")

# Crypto Helpers
def encrypt_token(token: str) -> str:
    """Encrypts a token using Fernet symmetric encryption."""
    key = os.getenv("TOKEN_ENC_KEY", "someloginsecretkeythatshouldbesecret==").encode()
    f = Fernet(key)
    return f.encrypt(token.encode()).decode()


def decrypt_token(token: str) -> str:
    """Decrypts a token using Fernet symmetric encryption."""
    key = os.getenv("TOKEN_ENC_KEY", "someloginsecretkeythatshouldbesecret==").encode()
    f = Fernet(key)
    return f.decrypt(token.encode()).decode()


# Lifecycle for Beanie initialization and Background Tasks
async def lifespan(app: FastAPI):
    """Initialize DB and start background tasks."""
    # Startup
    await init_db()
    await ensure_admin_exists()
    redis_task = asyncio.create_task(redis_listener())
    
    yield
    
    # Shutdown
    redis_task.cancel()
    try:
        await redis_task
    except asyncio.CancelledError:
        pass
    await close_db()


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="App Console - Beehus Platform", lifespan=lifespan)

# CORS
_extra_origins = os.getenv("CORS_ORIGINS", "")
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
] + [o.strip() for o in _extra_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.console.routers import auth, credentials, users, downloads, processors
app.include_router(auth.router)
app.include_router(credentials.router)
app.include_router(users.router)
app.include_router(downloads.router)
app.include_router(processors.router)


# ============================================================================
# Workspaces Endpoints
# ============================================================================

@app.post("/workspaces", response_model=WorkspaceResponse)
async def create_workspace(ws_in: WorkspaceCreate):
    """Create a new workspace."""
    ws = Workspace(name=ws_in.name)
    await ws.save()
    return ws


@app.get("/workspaces", response_model=List[WorkspaceResponse])
async def list_workspaces():
    """List all workspaces."""
    workspaces = await Workspace.find_all().to_list()
    return workspaces



@app.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(workspace_id: str):
    """Get workspace by ID."""
    ws = await Workspace.get(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@app.delete("/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str):
    """Delete a workspace by ID."""
    workspace = await Workspace.get(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    
    # Also delete all jobs in this workspace
    jobs = await Job.find(Job.workspace_id == workspace_id).to_list()
    for job in jobs:
        await job.delete()
    
    await workspace.delete()
    return {"message": f"Workspace {workspace_id} and {len(jobs)} associated jobs deleted"}


# ============================================================================
# Inbox Integrations Endpoints
# ============================================================================

@app.post("/inbox_integrations", response_model=InboxIntegrationResponse)
async def create_inbox_integration(integration_in: InboxIntegrationCreate):
    """Create a new inbox integration (e.g., Gmail)."""
    encrypted_token = encrypt_token(integration_in.refresh_token)
    
    integration = InboxIntegration(
        workspace_id=integration_in.workspace_id,
        provider="gmail",
        email_address=integration_in.email_address,
        token_ciphertext=encrypted_token,
        scopes=integration_in.scopes or []
    )
    await integration.save()
    return integration


@app.get("/inbox_integrations", response_model=List[InboxIntegrationResponse])
async def list_inbox_integrations(workspace_id: str = None):
    """List inbox integrations, optionally filtered by workspace."""
    if workspace_id:
        integrations = await InboxIntegration.find(
            InboxIntegration.workspace_id == workspace_id
        ).to_list()
    else:
        integrations = await InboxIntegration.find_all().to_list()
    return integrations


# ============================================================================
# OTP Rules Endpoints
# ============================================================================

@app.post("/otp_rules", response_model=OtpRuleResponse)
async def create_otp_rule(rule_in: OtpRuleCreate):
    """Create a new OTP extraction rule."""
    rule = OtpRule(**rule_in.dict())
    await rule.save()
    return rule


@app.get("/otp_rules", response_model=List[OtpRuleResponse])
async def list_otp_rules(workspace_id: str = None):
    """List OTP rules, optionally filtered by workspace."""
    if workspace_id:
        rules = await OtpRule.find(OtpRule.workspace_id == workspace_id).to_list()
    else:
        rules = await OtpRule.find_all().to_list()
    return rules


# ============================================================================
# Jobs Endpoints
# ============================================================================

@app.post("/jobs", response_model=JobResponse)
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
                detail=(
                    "Itaú onshore manual jobs require username, password, agencia and conta"
                ),
            )

    job = Job(**job_in.dict())
    await job.save()
    return job


@app.get("/jobs", response_model=List[JobResponse])
async def list_jobs(workspace_id: str = None):
    """List jobs, optionally filtered by workspace."""
    if workspace_id:
        jobs = await Job.find(Job.workspace_id == workspace_id).to_list()
    else:
        jobs = await Job.find_all().to_list()
    return jobs


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """Get job by ID."""
    job = await Job.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job by ID."""
    job = await Job.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    await job.delete()
    return {"message": f"Job {job_id} deleted successfully"}


@app.delete("/jobs")
async def delete_all_jobs(workspace_id: str = None):
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


@app.post("/jobs/{job_id}/run", response_model=RunResponse)
async def trigger_run(job_id: str):
    """
    Trigger a job run.
    Creates a Run document and dispatches to Celery worker.
    """
    # 1. Fetch job
    job = await Job.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != "active":
        raise HTTPException(status_code=400, detail="Job is not active")
    
    # 2. Create run document
    run = Run(job_id=job.id, job_name=job.name, connector=job.connector, status="queued")
    await run.save()
    
    # Merge job configuration into params
    execution_params = job.params.copy()
    execution_params.update({
        "export_holdings": job.export_holdings,
        "export_history": job.export_history,
        "date_mode": job.date_mode,
        "holdings_lag_days": job.holdings_lag_days,
        "history_lag_days": job.history_lag_days,
        "holdings_date": job.holdings_date,
        "history_date": job.history_date,
    })

    # 3. Dispatch to Celery (replaces HTTP call to orchestrator)
    task = scrape_task.delay(
        job_id=job.id,
        run_id=str(run.id),  # Convert to string
        workspace_id=job.workspace_id,
        connector_name=job.connector,
        params=execution_params
    )
    
    # 4. Save task ID for cancellation support
    run.celery_task_id = task.id
    await run.save()
    
    return run


@app.post("/jobs/{job_id}/run/{run_id}/retry", response_model=RunResponse)
async def retry_run(job_id: str, run_id: str):
    """
    Retry a failed run.
    Increments attempt counter and re-dispatches to Celery.
    """
    # Fetch job and run
    job = await Job.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    run = await Run.get(run_id)
    if not run or run.job_id != job.id:
        raise HTTPException(status_code=404, detail="Run not found for this job")
    
    # Increment attempt and reset status
    run.attempt += 1
    run.status = "queued"
    run.error_summary = None
    run.started_at = None
    run.finished_at = None
    run.processing_status = "not_required"
    run.selected_filename = None
    run.selected_sheet = None
    run.processing_error = None
    # Ensure connector is set (for old runs that didn't have it)
    if not run.connector and job:
        run.connector = job.connector
    if not run.job_name and job:
        run.job_name = job.name
    await run.save()
    
    # Merge job configuration into params
    execution_params = job.params.copy()
    execution_params.update({
        "export_holdings": job.export_holdings,
        "export_history": job.export_history,
        "date_mode": job.date_mode,
        "holdings_lag_days": job.holdings_lag_days,
        "history_lag_days": job.history_lag_days,
        "holdings_date": job.holdings_date,
        "history_date": job.history_date,
    })

    # Re-dispatch to Celery
    task = scrape_task.delay(
        job_id=job.id,
        run_id=run.id,
        workspace_id=job.workspace_id,
        connector_name=job.connector,
        params=execution_params
    )
    
    # Save new task ID
    run.celery_task_id = task.id
    await run.save()
    
    return run


@app.post("/runs/{run_id}/stop")
async def stop_run(run_id: str):
    """
    Stop/cancel a running or queued job.
    """
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    if run.status not in ["queued", "running"]:
        raise HTTPException(status_code=400, detail=f"Cannot stop run with status '{run.status}'")
    
    # Revoke the Celery task if we have a task ID
    if run.celery_task_id:
        celery_app.control.revoke(run.celery_task_id, terminate=True)
    
    # Update run status
    run.status = "failed"
    run.error_summary = "Cancelled by user"
    run.logs.append(f"[{get_now().time()}] 🛑 Run cancelled by user")
    run.finished_at = get_now()
    await run.save()
    
    return {"message": f"Run {run_id} stopped successfully", "run_id": run_id}


# ============================================================================
# Runs Endpoints
# ============================================================================

@app.get("/runs", response_model=List[RunResponse])
async def list_runs(job_id: str = None, status: str = None):
    """List runs, optionally filtered by job_id and/or status."""
    query = Run.find()
    
    if job_id:
        query = query.find(Run.job_id == job_id)
    if status:
        query = query.find(Run.status == status)
    
    runs = await query.sort(-Run.created_at).to_list()
    return runs


@app.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str):
    """Get run by ID."""
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run



# ============================================================================
# Dashboard Endpoints
# ============================================================================

@app.get("/dashboard/stats")
async def get_dashboard_stats():
    """
    Get dashboard statistics from real database.
    """
    from datetime import datetime, timedelta
    
    # Count runs by status
    total_runs = await Run.count()
    successful_runs = await Run.find(Run.status == "success").count()
    failed_runs = await Run.find(Run.status == "failed").count()
    running_runs = await Run.find(Run.status == "running").count()
    queued_runs = await Run.find(Run.status == "queued").count()
    
    # Active includes running and queued
    active_total = running_runs + queued_runs
    
    # Count active jobs
    active_jobs = await Job.find(Job.status == "active").count()
    
    # Calculate trend (last 7 days vs previous 7 days)
    now = get_now()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    
    recent_success = await Run.find(
        Run.status == "success",
        Run.created_at >= week_ago
    ).count()
    
    previous_success = await Run.find(
        Run.status == "success",
        Run.created_at >= two_weeks_ago,
        Run.created_at < week_ago
    ).count()
    
    success_trend = 0
    if previous_success > 0:
        success_trend = round(((recent_success - previous_success) / previous_success) * 100, 1)
    
    return {
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "running_runs": running_runs,
        "queued_runs": queued_runs,
        "active_workers": active_total,
        "browser_sessions": running_runs,  # Only running jobs use browser
        "success_trend": success_trend,
        "total_runs": total_runs,
        "active_jobs": active_jobs
    }


@app.get("/dashboard/recent-runs")
async def get_recent_runs(limit: int = 10):
    """
    Get recent runs with job details for dashboard table.
    """
    runs = await Run.find().sort(-Run.created_at).limit(limit).to_list()
    
    result = []
    for run in runs:
        # Use connector and job name from run if available, otherwise fetch from job
        connector_name = run.connector if run.connector else "Unknown"
        job_name = run.job_name if run.job_name else None
        
        # If connector not in run, try to fetch from job (for backwards compatibility)
        if (not run.connector or not job_name) and run.job_id and run.job_id != "test-job":
            try:
                job = await Job.get(run.job_id)
                if job:
                    if not run.connector:
                        connector_name = job.connector
                    if not job_name:
                        job_name = job.name
            except Exception as e:
                logger.warning(f"Failed to fetch job {run.job_id}: {e}")
        
        # Convert created_at to local timezone for display
        created_at_str = None
        if run.created_at:
            from zoneinfo import ZoneInfo
            from core.config import settings
            
            # If datetime is naive, assume it's UTC
            if run.created_at.tzinfo is None:
                utc_time = run.created_at.replace(tzinfo=ZoneInfo("UTC"))
            else:
                utc_time = run.created_at
            
            # Convert to local timezone
            local_tz = ZoneInfo(settings.TIMEZONE)
            local_time = utc_time.astimezone(local_tz)
            created_at_str = local_time.isoformat()
        
        result.append({
            "run_id": str(run.id),
            "job_id": run.job_id or "N/A",
            "job_name": job_name or connector_name,
            "connector": connector_name,
            "status": run.status,
            "processing_status": run.processing_status or "not_required",
            "selected_filename": run.selected_filename,
            "selected_sheet": run.selected_sheet,
            "processing_error": run.processing_error,
            "report_date": run.report_date,
            "history_date": run.history_date,
            "node": "selenium-node-1",  # TODO: Add node tracking
            "created_at": created_at_str
        })
    
    return result


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "app-console"}


# ============================================================================
# Test Endpoints
# ============================================================================
@app.post("/test/jpmorgan", tags=["test"])
async def trigger_jpmorgan_test(user: str = "demo_user", password: str = "demo_pass"):
    """
    Triggers the JPMorgan login task for testing purposes.
    Creates a temporary valid Run ID for logging.
    """
    from core.tasks import login_to_jpmorgan_task
    
    # Create a placeholder run
    run = Run(job_id="test-job", status="queued", logs=["[System] Manual test triggered"])
    await run.save()
    
    task = login_to_jpmorgan_task.delay(user, password, str(run.id))
    
    return {"status": "triggered", "task_id": task.id, "run_id": str(run.id)}


# ============================================================================
# WebSocket Endpoints
# ============================================================================

@app.websocket("/ws/runs")
async def websocket_runs_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            # We don't expect messages from client, but we need to await something
            # to keep the connection open and detect disconnects
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

