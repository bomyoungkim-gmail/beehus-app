from __future__ import annotations

from pathlib import Path
import shutil

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from core.services.automated_folder_processor import (
    AutomatedProcessingError,
    SandboxHealthResult,
    UploadedArtifact,
)
from core.services.automated_processing_orchestrator import orchestrator

router = APIRouter(prefix="/processamento-automatizado", tags=["processamento-automatizado"])

# Backward-compatible names used by endpoint tests monkeypatches.
run_folder_processing_batch = orchestrator.process_uploaded_batch
run_server_path_processing_batch = orchestrator.process_server_paths_batch
validate_sandbox_health = orchestrator.health_check


def _cleanup_directory(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


class ProcessServerPathsRequest(BaseModel):
    folder_paths: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=300, ge=30, le=1800)
    sandbox_mode: str = "none"
    write_to_source: bool = False


class SandboxHealthResponse(BaseModel):
    ready: bool
    sandbox_mode: str
    docker_available: bool
    image: str
    image_pull_ok: bool
    docker_version: str | None = None
    message: str


def _serialize_sandbox_health(result: SandboxHealthResult) -> SandboxHealthResponse:
    return SandboxHealthResponse(
        ready=result.ready,
        sandbox_mode=result.sandbox_mode,
        docker_available=result.docker_available,
        image=result.image,
        image_pull_ok=result.image_pull_ok,
        docker_version=result.docker_version,
        message=result.message,
    )


def _map_processing_exception(exc: AutomatedProcessingError) -> HTTPException:
    detail: dict[str, object] | str
    if exc.details:
        detail = {"message": str(exc), "errors": exc.details}
    else:
        detail = str(exc)
    return HTTPException(status_code=400, detail=detail)


@router.get("/sandbox-health", response_model=SandboxHealthResponse)
async def sandbox_health_check(
    sandbox_mode: str = Query("docker"),
    pull_image: bool = Query(True),
    run_probe: bool = Query(True),
    timeout_seconds: int = Query(600, ge=10, le=3600),
):
    try:
        health = validate_sandbox_health(
            sandbox_mode=sandbox_mode,
            pull_image=pull_image,
            run_probe=run_probe,
            timeout_seconds=timeout_seconds,
        )
        return _serialize_sandbox_health(health)
    except AutomatedProcessingError as exc:
        raise _map_processing_exception(exc) from exc


@router.post("/process")
async def processar_pastas(
    files: list[UploadFile] = File(...),
    timeout_seconds: int = Query(300, ge=30, le=1800),
    sandbox_mode: str = Query("none"),
    download_mode: str = Query("zip"),
):
    if not files:
        raise HTTPException(status_code=400, detail="Envie ao menos uma pasta com arquivos.")

    artifacts: list[UploadedArtifact] = []
    for uploaded in files:
        filename = (uploaded.filename or "").strip()
        if not filename:
            continue
        content = await uploaded.read()
        artifacts.append(UploadedArtifact(relative_path=filename, content=content))

    if not artifacts:
        raise HTTPException(status_code=400, detail="Nenhum arquivo valido foi recebido.")

    try:
        result = run_folder_processing_batch(
            artifacts,
            timeout_seconds=timeout_seconds,
            sandbox_mode=sandbox_mode,
        )
    except AutomatedProcessingError as exc:
        raise _map_processing_exception(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao processar pastas: {exc}") from exc

    try:
        file_path, file_name, media_type = orchestrator.resolve_download_target(
            result=result,
            download_mode=download_mode,
        )
    except AutomatedProcessingError as exc:
        raise _map_processing_exception(exc) from exc

    background = BackgroundTask(_cleanup_directory, result.working_dir)
    return FileResponse(
        path=file_path,
        filename=file_name,
        media_type=media_type,
        background=background,
    )


@router.post("/process-server-paths")
async def processar_pastas_por_caminhos(body: ProcessServerPathsRequest):
    if not body.folder_paths:
        raise HTTPException(status_code=400, detail="Envie ao menos um caminho de pasta do servidor.")

    try:
        result = run_server_path_processing_batch(
            body.folder_paths,
            timeout_seconds=body.timeout_seconds,
            sandbox_mode=body.sandbox_mode,
            write_to_source=body.write_to_source,
        )
    except AutomatedProcessingError as exc:
        raise _map_processing_exception(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao processar pastas por caminho: {exc}") from exc

    background = BackgroundTask(_cleanup_directory, result.working_dir)
    return FileResponse(
        path=result.archive_path,
        filename=result.archive_path.name,
        media_type="application/zip",
        background=background,
    )
