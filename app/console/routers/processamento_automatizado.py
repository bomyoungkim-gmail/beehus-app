from __future__ import annotations

import mimetypes
from pathlib import Path
import shutil

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from core.services.automated_folder_processor import (
    AutomatedProcessingError,
    AutomatedProcessingResult,
    SandboxHealthResult,
    UploadedArtifact,
    run_folder_processing_batch,
    run_server_path_processing_batch,
    validate_sandbox_health,
)

router = APIRouter(prefix="/processamento-automatizado", tags=["processamento-automatizado"])


def _cleanup_directory(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def _single_output_file_path(result: AutomatedProcessingResult) -> Path | None:
    output_files = [
        output_file
        for folder in result.folders
        for output_file in folder.output_files
    ]
    if len(output_files) != 1:
        return None

    outputs_root = (result.working_dir / "outputs").resolve()
    candidate = (outputs_root / Path(output_files[0])).resolve()

    try:
        candidate.relative_to(outputs_root)
    except ValueError:
        return None

    if not candidate.is_file():
        return None

    return candidate


def _resolve_download_target(
    *,
    result: AutomatedProcessingResult,
    download_mode: str,
) -> tuple[Path, str, str]:
    normalized_mode = (download_mode or "zip").strip().lower()
    if normalized_mode not in {"zip", "single", "auto"}:
        raise AutomatedProcessingError(
            "download_mode invalido: use zip, single ou auto."
        )

    if normalized_mode == "zip":
        return result.archive_path, result.archive_path.name, "application/zip"

    single_file = _single_output_file_path(result)
    if single_file:
        media_type = mimetypes.guess_type(single_file.name)[0] or "application/octet-stream"
        return single_file, single_file.name, media_type

    if normalized_mode == "single":
        raise AutomatedProcessingError(
            "Nao foi possivel baixar sem compactacao: processamento gerou mais de um arquivo de saida."
        )

    return result.archive_path, result.archive_path.name, "application/zip"


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
        file_path, file_name, media_type = _resolve_download_target(
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
