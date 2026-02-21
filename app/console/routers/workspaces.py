"""
Workspaces Router - API endpoints for workspace management.
"""

from fastapi import APIRouter, HTTPException
from typing import List

from core.models.mongo_models import Workspace, Job, Run
from core.schemas.otp import WorkspaceCreate, WorkspaceResponse

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceResponse)
async def create_workspace(ws_in: WorkspaceCreate):
    """Create a new workspace."""
    ws = Workspace(name=ws_in.name)
    await ws.save()
    return ws


@router.get("", response_model=List[WorkspaceResponse])
async def list_workspaces():
    """List all workspaces."""
    return await Workspace.find_all().to_list()


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(workspace_id: str):
    """Get workspace by ID."""
    ws = await Workspace.get(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@router.delete("/{workspace_id}")
async def delete_workspace(workspace_id: str):
    """Delete a workspace and all its jobs/runs."""
    workspace = await Workspace.get(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    jobs = await Job.find(Job.workspace_id == workspace_id).to_list()
    for job in jobs:
        await Run.find(Run.job_id == str(job.id)).delete()
        await job.delete()

    await workspace.delete()
    return {"message": f"Workspace {workspace_id} and {len(jobs)} associated jobs deleted"}
