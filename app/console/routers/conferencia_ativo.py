"""
Conferencia Ativo router - process CSV and enrich with ANBIMA data.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from core.services.anbima_conferencia_service import processar_csv_arquivo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conferencia-ativo", tags=["conferencia-ativo"])
_progress_lock = threading.Lock()
_progress_store: dict[str, dict] = {}


def _artifacts_dir() -> Path:
    return Path(os.getenv("ARTIFACTS_DIR", "/app/artifacts"))


def _init_progress(trace_id: str) -> None:
    with _progress_lock:
        _progress_store[trace_id] = {
            "status": "running",
            "logs": [],
            "error": None,
            "output_path": None,
            "filename": None,
        }


def _append_progress(trace_id: str, message: str) -> None:
    now = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")
    entry = f"[{now}] {message}"
    with _progress_lock:
        state = _progress_store.setdefault(
            trace_id,
            {"status": "running", "logs": [], "error": None, "output_path": None, "filename": None},
        )
        state["logs"].append(entry)
        if len(state["logs"]) > 2000:
            state["logs"] = state["logs"][-2000:]


def _finish_progress(trace_id: str, status: str, error: str | None = None) -> None:
    with _progress_lock:
        state = _progress_store.setdefault(
            trace_id,
            {"status": status, "logs": [], "error": None, "output_path": None, "filename": None},
        )
        state["status"] = status
        state["error"] = error


@router.get("/progress/{trace_id}")
async def get_conferencia_ativo_progress(trace_id: str):
    with _progress_lock:
        state = _progress_store.get(trace_id)
        if not state:
            return {"status": "not_found", "logs": [], "error": None}
        return {
            "status": state.get("status", "running"),
            "logs": list(state.get("logs", [])),
            "error": state.get("error"),
            "has_output": bool(state.get("output_path")),
        }


@router.get("/result/{trace_id}")
async def get_conferencia_ativo_result(trace_id: str):
    with _progress_lock:
        state = _progress_store.get(trace_id)
        if not state:
            raise HTTPException(status_code=404, detail="Trace not found")
        status = state.get("status")
        output_path = state.get("output_path")
        filename = state.get("filename") or f"conferencia_ativo_{trace_id}.csv"
        error = state.get("error")

    if status != "done" or not output_path:
        raise HTTPException(status_code=409, detail=f"Result not ready (status={status}, error={error})")
    path_obj = Path(str(output_path))
    if not path_obj.exists():
        raise HTTPException(status_code=410, detail="Result file no longer exists")

    return FileResponse(
        path=str(path_obj),
        media_type="text/csv",
        filename=filename,
    )


@router.post("/process-csv")
async def processar_conferencia_ativo_csv(
    file: UploadFile = File(...),
    use_selenium: bool = Query(True),
    headless: bool = Query(True),
    save_every: int = Query(10, ge=1, le=1000),
    trace_id: str | None = Query(None),
):
    """
    Process an input CSV with "Ativo Original" and return enriched CSV.
    """
    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    base_dir = _artifacts_dir() / "conferencia_ativo"
    work_dir = base_dir / ts
    input_path = work_dir / "entrada.csv"
    output_path = work_dir / "saida_final.csv"
    progress_key = (trace_id or "").strip()

    try:
        if progress_key:
            _init_progress(progress_key)

        work_dir.mkdir(parents=True, exist_ok=True)
        raw = await file.read()
        input_path.write_bytes(raw)
        if progress_key:
            _append_progress(progress_key, f"Arquivo recebido ({len(raw)} bytes)")

        await run_in_threadpool(
            processar_csv_arquivo,
            input_path,
            output_path,
            use_selenium=use_selenium,
            headless=headless,
            save_every=save_every,
            log_func=(lambda msg: _append_progress(progress_key, msg)) if progress_key else None,
        )

        if not output_path.exists():
            if progress_key:
                _finish_progress(progress_key, "error", "Failed to generate output CSV")
            raise HTTPException(status_code=500, detail="Failed to generate output CSV")

        if progress_key:
            with _progress_lock:
                state = _progress_store.setdefault(
                    progress_key,
                    {"status": "running", "logs": [], "error": None, "output_path": None, "filename": None},
                )
                state["output_path"] = str(output_path)
                state["filename"] = f"conferencia_ativo_{ts}.csv"
            _finish_progress(progress_key, "done")
        return FileResponse(
            path=str(output_path),
            media_type="text/csv",
            filename=f"conferencia_ativo_{ts}.csv",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error processing conferencia ativo csv")
        if progress_key:
            _append_progress(progress_key, f"Erro: {exc}")
            _finish_progress(progress_key, "error", str(exc))
        raise HTTPException(status_code=500, detail=f"Processing failed: {exc}") from exc
