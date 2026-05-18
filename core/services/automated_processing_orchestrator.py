from __future__ import annotations

import mimetypes
from pathlib import Path

from core.services.automated_folder_processor import (
    AutomatedProcessingError,
    AutomatedProcessingResult,
    SandboxHealthResult,
    UploadedArtifact,
    run_folder_processing_batch,
    run_server_path_processing_batch,
    validate_sandbox_health,
)


class AutomatedProcessingOrchestrator:
    @staticmethod
    def health_check(
        *,
        sandbox_mode: str,
        pull_image: bool,
        run_probe: bool,
        timeout_seconds: int,
    ) -> SandboxHealthResult:
        return validate_sandbox_health(
            sandbox_mode=sandbox_mode,
            pull_image=pull_image,
            run_probe=run_probe,
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def process_uploaded_batch(
        artifacts: list[UploadedArtifact],
        *,
        timeout_seconds: int,
        sandbox_mode: str,
    ) -> AutomatedProcessingResult:
        return run_folder_processing_batch(
            artifacts,
            timeout_seconds=timeout_seconds,
            sandbox_mode=sandbox_mode,
        )

    @staticmethod
    def process_server_paths_batch(
        folder_paths: list[str],
        *,
        timeout_seconds: int,
        sandbox_mode: str,
        write_to_source: bool,
    ) -> AutomatedProcessingResult:
        return run_server_path_processing_batch(
            folder_paths,
            timeout_seconds=timeout_seconds,
            sandbox_mode=sandbox_mode,
            write_to_source=write_to_source,
        )

    @staticmethod
    def resolve_download_target(
        *,
        result: AutomatedProcessingResult,
        download_mode: str,
    ) -> tuple[Path, str, str]:
        normalized_mode = (download_mode or "zip").strip().lower()
        if normalized_mode not in {"zip", "single", "auto"}:
            raise AutomatedProcessingError("download_mode invalido: use zip, single ou auto.")

        if normalized_mode == "zip":
            return result.archive_path, result.archive_path.name, "application/zip"

        single_file = AutomatedProcessingOrchestrator._single_output_file_path(result)
        if single_file:
            media_type = mimetypes.guess_type(single_file.name)[0] or "application/octet-stream"
            return single_file, single_file.name, media_type

        if normalized_mode == "single":
            raise AutomatedProcessingError(
                "Nao foi possivel baixar sem compactacao: processamento gerou mais de um arquivo de saida."
            )

        return result.archive_path, result.archive_path.name, "application/zip"

    @staticmethod
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


orchestrator = AutomatedProcessingOrchestrator()

