"""
Downloads API router - Provides endpoints for listing and downloading processed files.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging
import os

from core.models.mongo_models import Job, Run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/downloads", tags=["downloads"])


class FileMetadata(BaseModel):
    """File metadata response model."""

    file_type: str
    filename: str
    path: str
    size_bytes: Optional[int]
    status: str


class DownloadItem(BaseModel):
    """Download item with run and file information."""

    run_id: str
    job_id: str
    job_name: Optional[str]
    connector: Optional[str]
    status: str
    created_at: str
    files: List[FileMetadata]


def _artifacts_dir() -> Path:
    return Path(os.getenv("ARTIFACTS_DIR", "/app/artifacts"))


def _file_meta_to_dict(file_meta: Any) -> Dict[str, Any]:
    if hasattr(file_meta, "model_dump"):
        return file_meta.model_dump()
    if hasattr(file_meta, "dict"):
        return file_meta.dict()
    if isinstance(file_meta, dict):
        return file_meta
    raise ValueError("Unsupported run file metadata format")


def _resolve_artifact_path(relative_path: str) -> Path:
    root = _artifacts_dir().resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    return candidate


@router.get("/", response_model=List[DownloadItem])
async def list_downloads(
    status: Optional[str] = None,
    connector: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
):
    """
    List all runs with downloadable files.

    Query Parameters:
    - status: Filter by run status (success, failed, etc.)
    - connector: Filter by connector name
    - limit: Maximum number of results (default 50)
    - skip: Number of results to skip for pagination
    """
    try:
        query = {}
        if status:
            query["status"] = status
        if connector:
            query["connector"] = connector

        query["files"] = {"$exists": True, "$ne": []}

        runs = await Run.find(query).sort("-created_at").skip(skip).limit(limit).to_list()

        items = []
        for run in runs:
            normalized_files = [_file_meta_to_dict(f) for f in (run.files or [])]
            job_name = run.job_name
            if not job_name and run.job_id:
                job = await Job.get(run.job_id)
                if job:
                    job_name = job.name
            items.append(
                DownloadItem(
                    run_id=run.id,
                    job_id=run.job_id,
                    job_name=job_name or run.connector or "Unknown",
                    connector=run.connector,
                    status=run.status,
                    created_at=run.created_at.isoformat(),
                    files=[FileMetadata(**f) for f in normalized_files],
                )
            )

        return items

    except Exception as e:
        logger.error(f"Error listing downloads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{run_id}/{file_type}")
async def download_file(run_id: str, file_type: str, filename: Optional[str] = None):
    """
    Download a file for a specific run.

    Path Parameters:
    - run_id: Run ID
    - file_type: File type (original or processed)
    """
    try:
        run = await Run.get(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        selected: Optional[Dict[str, Any]] = None
        for f in run.files or []:
            candidate = _file_meta_to_dict(f)
            if candidate.get("file_type") != file_type:
                continue
            if filename and candidate.get("filename") != filename:
                continue
            selected = candidate
            break

        if not selected:
            raise HTTPException(status_code=404, detail=f"No {file_type} file found for this run")

        file_path = _resolve_artifact_path(selected["path"])
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found on disk")

        requested_name = selected["filename"]
        return FileResponse(
            path=str(file_path),
            filename=requested_name,
            media_type="application/octet-stream",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{run_id}/files", response_model=List[FileMetadata])
async def get_run_files(run_id: str):
    """
    Get all files for a specific run.

    Path Parameters:
    - run_id: Run ID
    """
    try:
        run = await Run.get(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        return [FileMetadata(**_file_meta_to_dict(f)) for f in (run.files or [])]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching run files: {e}")
        raise HTTPException(status_code=500, detail=str(e))
