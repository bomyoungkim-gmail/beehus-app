"""
Downloads API router - Provides endpoints for listing and downloading processed files.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import csv
import logging
import os

from core.models.mongo_models import Job, Run
from core.services.excel_introspection import is_excel_filename, list_sheet_names
from core.services.file_processor import FileProcessorService
from core.utils.date_utils import get_now

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
    sheet_options: List[str] = []


class ProcessingColumnsResponse(BaseModel):
    filename: str
    selected_sheet: Optional[str] = None
    columns: List[str] = []


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


def _original_files(run: Run) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for file_meta in run.files or []:
        candidate = _file_meta_to_dict(file_meta)
        if candidate.get("file_type") == "original":
            out.append(candidate)
    return out


def _existing_files_only(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for file_meta in files:
        rel = file_meta.get("path")
        if not rel:
            filtered.append(file_meta)
            continue
        try:
            path = _resolve_artifact_path(rel)
            if path.exists() and path.is_file():
                filtered.append(file_meta)
        except Exception:
            continue
    return filtered


def _to_iso8601_utc(value: datetime) -> str:
    """
    Return a timezone-aware ISO-8601 UTC string.
    Handles legacy naive datetimes by assuming they are UTC.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _read_columns_from_file(file_path: Path, filename: str, selected_sheet: Optional[str]) -> List[str]:
    try:
        import pandas as pd
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Pandas is required to inspect file columns") from exc

    if is_excel_filename(filename):
        sheet_name = selected_sheet if selected_sheet else 0
        df = pd.read_excel(str(file_path), sheet_name=sheet_name, nrows=0)
        return [str(c).strip() for c in list(df.columns)]

    sniff_text = ""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
            sniff_text = handle.read(2048)
    except Exception:
        sniff_text = ""

    delimiters = [",", ";", "\t", "|"]
    sep = ","
    if sniff_text:
        try:
            sep = csv.Sniffer().sniff(sniff_text, delimiters=delimiters).delimiter
        except Exception:
            sep = ";"

    df = pd.read_csv(str(file_path), sep=sep, nrows=0, dtype=str, encoding="utf-8")
    return [str(c).strip() for c in list(df.columns)]


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

    originals = _original_files(run)
    selected = next((f for f in originals if f.get("filename") == payload.filename), None)
    if not selected:
        raise HTTPException(status_code=404, detail="Selected file not found in run originals")

    if is_excel_filename(payload.filename):
        sheet_options = await get_excel_options(run_id, payload.filename)
        current_aliases = list(getattr(job, "sheet_aliases", []) or [])

        def _merge_aliases(values: List[str]) -> List[str]:
            merged = list(current_aliases)
            for v in values:
                value = (v or "").strip()
                if value and value.lower() not in [m.lower() for m in merged]:
                    merged.append(value)
            return merged

        if len(sheet_options) == 1:
            await job.update(
                {
                    "$set": {
                        "last_selected_filename": payload.filename,
                        "last_selected_sheet": sheet_options[0],
                        "sheet_aliases": _merge_aliases([sheet_options[0]]),
                        "selection_updated_at": get_now(),
                    }
                }
            )
            await run.update(
                {
                    "$set": {
                        "processing_status": "pending_reprocess",
                        "selected_filename": payload.filename,
                        "selected_sheet": sheet_options[0],
                        "processing_error": None,
                    }
                }
            )
            return {
                "status": "pending_reprocess",
                "selected_filename": payload.filename,
                "selected_sheet": sheet_options[0],
            }
        await job.update(
            {
                "$set": {
                    "last_selected_filename": payload.filename,
                    "last_selected_sheet": None,
                    "sheet_aliases": _merge_aliases(sheet_options),
                    "selection_updated_at": get_now(),
                }
            }
        )
        await run.update(
            {
                "$set": {
                    "processing_status": "pending_sheet_selection",
                    "selected_filename": payload.filename,
                    "selected_sheet": None,
                    "processing_error": None,
                }
            }
        )
        return {"status": "pending_sheet_selection", "selected_filename": payload.filename, "sheet_options": sheet_options}

    await job.update(
        {
            "$set": {
                "last_selected_filename": payload.filename,
                "last_selected_sheet": None,
                "selection_updated_at": get_now(),
            }
        }
    )
    await run.update(
        {
            "$set": {
                "processing_status": "pending_reprocess",
                "selected_filename": payload.filename,
                "selected_sheet": None,
                "processing_error": None,
            }
        }
    )
    return {"status": "pending_reprocess", "selected_filename": payload.filename}


@router.post("/{run_id}/processing/select-sheet")
async def select_sheet_for_processing(run_id: str, payload: SelectSheetRequest):
    run = await Run.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    job = await Job.get(run.job_id) if run.job_id else None
    if not job:
        raise HTTPException(status_code=400, detail="Run has no linked job")

    current_aliases = list(getattr(job, "sheet_aliases", []) or [])
    merged_aliases = list(current_aliases)
    if payload.selected_sheet and payload.selected_sheet.lower() not in [m.lower() for m in merged_aliases]:
        merged_aliases.append(payload.selected_sheet)

    await job.update(
        {
            "$set": {
                "last_selected_filename": payload.filename,
                "last_selected_sheet": payload.selected_sheet,
                "sheet_aliases": merged_aliases,
                "selection_updated_at": get_now(),
            }
        }
    )

    await run.update(
        {
            "$set": {
                "processing_status": "pending_reprocess",
                "selected_filename": payload.filename,
                "selected_sheet": payload.selected_sheet,
                "processing_error": None,
            }
        }
    )
    return {
        "status": "pending_reprocess",
        "selected_filename": payload.filename,
        "selected_sheet": payload.selected_sheet,
    }


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

    originals = _original_files(run)
    names = [f.get("filename") for f in originals if f.get("filename")]
    if not names:
        raise HTTPException(status_code=400, detail="Run has no original files to process")

    filename = payload.filename or getattr(run, "selected_filename", None) or job.last_selected_filename
    if not filename:
        if len(names) == 1:
            filename = names[0]
        else:
            await run.update({"$set": {"processing_status": "pending_file_selection", "processing_error": None}})
            return {"status": "pending_file_selection"}

    if filename not in names:
        raise HTTPException(status_code=400, detail=f"File '{filename}' not found among run originals")

    selected_sheet = payload.selected_sheet or getattr(run, "selected_sheet", None) or job.last_selected_sheet
    state = await FileProcessorService.process_with_user_selection(
        run_id=run_id,
        filename=filename,
        selected_sheet=selected_sheet,
    )
    if state == "failed":
        run = await Run.get(run_id)
        detail = run.processing_error if run else "Processing failed"
        raise HTTPException(status_code=400, detail=detail)

    return {
        "status": state,
        "selected_filename": filename,
        "selected_sheet": selected_sheet,
    }


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

    processed_candidates = [
        _file_meta_to_dict(f)
        for f in (run.files or [])
        if _file_meta_to_dict(f).get("file_type") == "processed"
    ]
    source_processed = next(
        (f for f in processed_candidates if f.get("filename") == payload.processed_filename),
        None,
    )
    if not source_processed:
        raise HTTPException(status_code=404, detail="Processed file not found in run")

    script_snapshot = source_processed.get("processor_script_snapshot")
    if not script_snapshot:
        raise HTTPException(
            status_code=400,
            detail="Processed file does not contain script snapshot for reprocessing.",
        )

    originals = _original_files(run)
    names = [f.get("filename") for f in originals if f.get("filename")]
    if not names:
        raise HTTPException(status_code=400, detail="Run has no original files to process")

    filename = payload.filename or getattr(run, "selected_filename", None) or job.last_selected_filename
    if not filename:
        if len(names) == 1:
            filename = names[0]
        else:
            await run.update({"$set": {"processing_status": "pending_file_selection", "processing_error": None}})
            return {"status": "pending_file_selection"}
    if filename not in names:
        raise HTTPException(status_code=400, detail=f"File '{filename}' not found among run originals")

    selected_sheet = payload.selected_sheet or getattr(run, "selected_sheet", None) or job.last_selected_sheet
    snapshot_meta = {
        "processor_id": source_processed.get("processor_id"),
        "processor_version": source_processed.get("processor_version"),
        "processor_name": source_processed.get("processor_name"),
        "processor_script_snapshot": script_snapshot,
        "processor_source": "snapshot",
    }
    state = await FileProcessorService.process_with_user_selection(
        run_id=run_id,
        filename=filename,
        selected_sheet=selected_sheet,
        script_override=script_snapshot,
        processor_snapshot_override=snapshot_meta,
    )
    if state == "failed":
        run = await Run.get(run_id)
        detail = run.processing_error if run else "Processing failed"
        raise HTTPException(status_code=400, detail=detail)

    return {
        "status": state,
        "selected_filename": filename,
        "selected_sheet": selected_sheet,
        "source_processed_filename": payload.processed_filename,
        "processor_source": "snapshot",
    }
