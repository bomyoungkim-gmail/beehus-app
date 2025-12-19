"""
App Console API - FastAPI application for managing workspaces, jobs, and runs.
Migrated to use Beanie (MongoDB) and Celery for task execution.
"""

from fastapi import FastAPI, HTTPException
from cryptography.fernet import Fernet
import os
from typing import List

from core.db import init_db, close_db
from core.config import settings
from core.models.mongo_models import Workspace, InboxIntegration, OtpRule, Job, Run, OtpAudit
from core.tasks import scrape_task
from core.schemas.otp import (
    WorkspaceCreate, WorkspaceResponse,
    InboxIntegrationCreate, InboxIntegrationResponse,
    OtpRuleCreate, OtpRuleResponse
)
from app.console.schemas import JobCreate, JobResponse, RunResponse


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


# Lifecycle for Beanie initialization
async def lifespan(app: FastAPI):
    """Initialize and cleanup Beanie connection."""
    await init_db()
    yield
    await close_db()


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="App Console - Beehus Platform", lifespan=lifespan)

# CORS
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.console.routers import auth
app.include_router(auth.router)


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
    run = Run(job_id=job.id, status="queued")
    await run.save()
    
    # 3. Dispatch to Celery (replaces HTTP call to orchestrator)
    scrape_task.delay(
        job_id=job.id,
        run_id=str(run.id),  # Convert to string
        workspace_id=job.workspace_id,
        connector_name=job.connector,
        params=job.params
    )
    
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
    await run.save()
    
    # Re-dispatch to Celery
    scrape_task.delay(
        job_id=job.id,
        run_id=run.id,
        workspace_id=job.workspace_id,
        connector_name=job.connector,
        params=job.params
    )
    
    return run


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
    week_ago = datetime.utcnow() - timedelta(days=7)
    two_weeks_ago = datetime.utcnow() - timedelta(days=14)
    
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
        # Get job details - handle case where job might not exist
        job = None
        connector_name = "Unknown"
        
        if run.job_id and run.job_id != "test-job":
            try:
                job = await Job.get(run.job_id)
                if job:
                    connector_name = job.connector
            except Exception as e:
                logger.warning(f"Failed to fetch job {run.job_id}: {e}")
        
        result.append({
            "run_id": str(run.id),
            "job_id": run.job_id or "N/A",
            "connector": connector_name,
            "status": run.status,
            "node": "selenium-node-1",  # TODO: Add node tracking
            "created_at": run.created_at.isoformat() if run.created_at else None
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

