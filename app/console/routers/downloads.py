"""
Downloads API router - Provides endpoints for listing and downloading processed files.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
import logging

from core.models.mongo_models import Job, Run
from core.services.excel_introspection import is_excel_filename, list_sheet_names
from core.services.file_processor import FileProcessorService
from core.services.run_artifacts import run_artifacts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/downloads", tags=["downloads"])


class FileMetadata(BaseModel):
    """File metadata response model."""

    file_type: str
    filename: str
    path: str
    size_bytes: Optional[int]
    status: str
    is_latest: bool = False
    processor_id: Optional[str] = None
    processor_version: Optional[int] = None
    processor_name: Optional[str] = None
    processor_script_snapshot: Optional[str] = None
    processor_source: Optional[str] = None


class DownloadItem(BaseModel):
    """Download item with run and file information."""

    run_id: str
    job_id: str
    job_name: Optional[str]
    connector: Optional[str]
    status: str
    created_at: str
    files: List[FileMetadata]

class ProcessingFileOption(BaseModel):
    filename: str
    size_bytes: Optional[int]
    is_excel: bool
    sheet_options: List[str] = Field(default_factory=list)


class ProcessingColumnsResponse(BaseModel):
    filename: str
    selected_sheet: Optional[str] = None
    columns: List[str] = Field(default_factory=list)


class SelectFileRequest(BaseModel):
    filename: str


class SelectSheetRequest(BaseModel):
    filename: str
    selected_sheet: str


class ReprocessRequest(BaseModel):
    filename: Optional[str] = None
    selected_sheet: Optional[str] = None


class ReprocessFromProcessedRequest(BaseModel):
    processed_filename: str
    filename: Optional[str] = None
    selected_sheet: Optional[str] = None


def _artifacts_dir() -> Path:
    return run_artifacts.artifacts_dir()


def _file_meta_to_dict(file_meta: Any) -> Dict[str, Any]:
    return run_artifacts.file_meta_to_dict(file_meta)


def _resolve_artifact_path(relative_path: str) -> Path:
    return run_artifacts.resolve_artifact_path(relative_path)


def _original_files(run: Run) -> List[Dict[str, Any]]:
    return run_artifacts.original_files(run)


def _existing_files_only(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return run_artifacts.existing_files_only(files)


def _to_iso8601_utc(value: datetime) -> str:
    return run_artifacts.to_iso8601_utc(value)


def _read_columns_from_file(file_path: Path, filename: str, selected_sheet: Optional[str]) -> List[str]:
    return run_artifacts.read_columns_from_file(file_path, filename, selected_sheet)


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
            existing_files = _existing_files_only(normalized_files)
            if len(existing_files) != len(normalized_files):
                await run.update({"$set": {"files": existing_files}})
                normalized_files = existing_files
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
                    created_at=_to_iso8601_utc(run.created_at),
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


@router.get("/{run_id}/processing/options", response_model=List[ProcessingFileOption])
async def get_processing_options(run_id: str):
    """List original files that can be selected for processing."""
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    originals = _original_files(run)
    options: List[ProcessingFileOption] = []
    for file_meta in originals:
        filename = file_meta.get("filename", "")
        is_excel = is_excel_filename(filename)
        sheet_options: List[str] = []
        if is_excel:
            try:
                file_path = _resolve_artifact_path(file_meta["path"])
                if file_path.exists():
                    sheet_options = list_sheet_names(str(file_path))
            except Exception as exc:
                logger.warning("Failed to list sheet options for %s: %s", filename, exc)
        options.append(
            ProcessingFileOption(
                filename=filename,
                size_bytes=file_meta.get("size_bytes"),
                is_excel=is_excel,
                sheet_options=sheet_options,
            )
        )
    return options


@router.get("/{run_id}/processing/excel-options", response_model=List[str])
async def get_excel_options(run_id: str, filename: Optional[str] = Query(default=None)):
    """Return sheet names for selected excel file."""
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    target_name = filename or run.selected_filename
    if not target_name:
        raise HTTPException(status_code=400, detail="No filename provided")
    if not is_excel_filename(target_name):
        raise HTTPException(status_code=400, detail="Selected file is not an Excel file")

    file_meta = next((f for f in _original_files(run) if f.get("filename") == target_name), None)
    if not file_meta:
        raise HTTPException(status_code=404, detail="Original file not found")

    file_path = _resolve_artifact_path(file_meta["path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    try:
        return list_sheet_names(str(file_path))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read sheets: {exc}") from exc


@router.get("/{run_id}/processing/columns", response_model=ProcessingColumnsResponse)
async def get_file_columns(
    run_id: str,
    filename: Optional[str] = Query(default=None),
    selected_sheet: Optional[str] = Query(default=None),
):
    """Return detected input columns for one original file."""
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    target_name = filename or run.selected_filename
    if not target_name:
        raise HTTPException(status_code=400, detail="No filename provided")

    file_meta = next((f for f in _original_files(run) if f.get("filename") == target_name), None)
    if not file_meta:
        raise HTTPException(status_code=404, detail="Original file not found")

    file_path = _resolve_artifact_path(file_meta["path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    try:
        columns = _read_columns_from_file(file_path, target_name, selected_sheet)
        return ProcessingColumnsResponse(
            filename=target_name,
            selected_sheet=selected_sheet,
            columns=columns,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to inspect columns: {exc}") from exc


@router.post("/{run_id}/processing/select-file")
async def select_file_for_processing(run_id: str, payload: SelectFileRequest):
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    job = await Job.get(run.job_id) if run.job_id else None
    if not job:
        raise HTTPException(status_code=400, detail="Run has no linked job")

    if is_excel_filename(payload.filename):
        sheet_options = await get_excel_options(run_id, payload.filename)
        return await run_artifacts.select_file_for_processing(
            run=run,
            job=job,
            filename=payload.filename,
            sheet_options=sheet_options,
        )

    return await run_artifacts.select_file_for_processing(
        run=run,
        job=job,
        filename=payload.filename,
    )


@router.post("/{run_id}/processing/select-sheet")
async def select_sheet_for_processing(run_id: str, payload: SelectSheetRequest):
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    job = await Job.get(run.job_id) if run.job_id else None
    if not job:
        raise HTTPException(status_code=400, detail="Run has no linked job")

    return await run_artifacts.select_sheet_for_processing(
        run=run,
        job=job,
        filename=payload.filename,
        selected_sheet=payload.selected_sheet,
    )


@router.post("/{run_id}/processing/process")
async def reprocess_run(run_id: str, payload: ReprocessRequest):
    """
    Reprocess a run using explicit selection or persisted latest selection.
    Creates a new processed version and marks it as latest.
    """
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    job = await Job.get(run.job_id) if run.job_id else None
    if not job:
        raise HTTPException(status_code=400, detail="Run has no linked job")

    return await run_artifacts.process_with_selection(
        run_id=run_id,
        run=run,
        job=job,
        filename=payload.filename,
        selected_sheet=payload.selected_sheet,
        file_processor_service=FileProcessorService,
    )


@router.post("/{run_id}/processing/reprocess-from-processed")
async def reprocess_from_processed(run_id: str, payload: ReprocessFromProcessedRequest):
    """
    Reprocess a run using the script snapshot stored in a previously processed file.
    """
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    job = await Job.get(run.job_id) if run.job_id else None
    if not job:
        raise HTTPException(status_code=400, detail="Run has no linked job")

    return await run_artifacts.process_from_snapshot(
        run_id=run_id,
        run=run,
        job=job,
        processed_filename=payload.processed_filename,
        filename=payload.filename,
        selected_sheet=payload.selected_sheet,
        file_processor_service=FileProcessorService,
    )
