"""
File processing service for transforming downloaded files.
Executes Python scripts associated with credentials.
"""

import logging
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from core.models.mongo_models import Credential, FileProcessor, Job, Run
from core.services.excel_introspection import is_excel_filename, list_sheet_names
from core.services.file_manager import FileManager
from core.utils.date_utils import get_now

logger = logging.getLogger(__name__)


class FileProcessorService:
    """Service for executing credential-bound file processors."""

    @staticmethod
    def _safe_job_name(job_name: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", (job_name or "").strip())
        safe = re.sub(r"_+", "_", safe).strip("_")
        return safe or "job"

    @staticmethod
    def _run_files_to_dicts(run: Run) -> List[Dict]:
        items: List[Dict] = []
        for f in run.files or []:
            if hasattr(f, "model_dump"):
                items.append(f.model_dump())
            elif hasattr(f, "dict"):
                items.append(f.dict())
            elif isinstance(f, dict):
                items.append(f)
        return items

    @staticmethod
    def _original_files(run: Run) -> List[Dict]:
        return [f for f in FileProcessorService._run_files_to_dicts(run) if f.get("file_type") == "original"]

    @staticmethod
    async def process_files(
        run_id: str,
        credential_id: str,
        selected_filename: Optional[str] = None,
        selected_sheet: Optional[str] = None,
        job_name: str = "job",
    ) -> List[str]:
        """
        Process files for a run using the credential's active processor.
        """
        try:
            processor = await FileProcessor.find_one(
                FileProcessor.credential_id == credential_id,
                FileProcessor.is_active == True,
            )
            if not processor:
                logger.info("No active processor for credential %s", credential_id)
                return []

            credential = await Credential.get(credential_id)
            if not credential:
                logger.warning("Credential %s not found", credential_id)
                return []

            artifacts_root = os.getenv("ARTIFACTS_DIR", "/app/artifacts")
            original_dir = Path(artifacts_root) / run_id / "original"
            processed_dir = Path(artifacts_root) / run_id / "processed"
            processed_dir.mkdir(parents=True, exist_ok=True)

            source_excel_path = ""
            if selected_filename and is_excel_filename(selected_filename):
                source_excel_path = str(original_dir / selected_filename)

            context = {
                "original_dir": str(original_dir),
                "processed_dir": str(processed_dir),
                "carteira": credential.carteira or "",
                "metadata": credential.metadata or {},
                "run_id": run_id,
                "credential_label": credential.label,
                "selected_filename": selected_filename or "",
                "selected_sheet": selected_sheet or "",
                "source_excel_path": source_excel_path,
            }

            logger.info(
                "Executing processor '%s' (v%s) for run %s",
                processor.name,
                processor.version,
                run_id,
            )

            processed_files = await FileProcessorService._execute_processor(
                processor.script_content,
                context,
            )

            renamed_files = FileProcessorService._normalize_processed_names(
                processed_files,
                job_name=job_name,
            )

            logger.info("Processor completed: %s file(s) generated", len(renamed_files))
            return renamed_files
        except Exception as exc:
            logger.error("File processing failed for run %s: %s", run_id, exc)
            return []

    @staticmethod
    def _normalize_processed_names(file_paths: List[str], job_name: str) -> List[str]:
        if not file_paths:
            return []
        safe_job = FileProcessorService._safe_job_name(job_name)
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        renamed: List[str] = []
        for idx, old_path in enumerate(sorted(file_paths), start=1):
            path = Path(old_path)
            ext = path.suffix or ".csv"
            suffix = f"_{idx:02d}" if len(file_paths) > 1 else ""
            target = path.parent / f"{safe_job}_{stamp}{suffix}{ext}"
            collision = 1
            while target.exists() and target != path:
                target = path.parent / f"{safe_job}_{stamp}{suffix}_{collision:02d}{ext}"
                collision += 1
            if target != path:
                path.rename(target)
            renamed.append(str(target))
        return renamed

    @staticmethod
    async def append_processed_to_run(run_id: str, processed_paths: List[str]) -> int:
        current_run = await Run.get(run_id)
        if not current_run:
            return 0

        current_files = FileProcessorService._run_files_to_dicts(current_run)
        for existing in current_files:
            if existing.get("file_type") == "processed":
                existing["is_latest"] = False

        for processed_path in processed_paths:
            current_files.append(
                {
                    "file_type": "processed",
                    "filename": os.path.basename(processed_path),
                    "path": FileManager.to_artifact_relative(processed_path),
                    "size_bytes": FileManager.get_file_size(processed_path),
                    "status": "ready",
                    "is_latest": True,
                }
            )

        await current_run.update({"$set": {"files": current_files}})
        return len(processed_paths)

    @staticmethod
    async def _set_run_processing_state(
        run: Run,
        processing_status: str,
        selected_filename: Optional[str] = None,
        selected_sheet: Optional[str] = None,
        processing_error: Optional[str] = None,
    ) -> None:
        await run.update(
            {
                "$set": {
                    "processing_status": processing_status,
                    "selected_filename": selected_filename,
                    "selected_sheet": selected_sheet,
                    "processing_error": processing_error,
                }
            }
        )

    @staticmethod
    async def _acquire_processing_lock(run_id: str) -> bool:
        """
        Acquire processing lock by atomically switching status to `processing`.
        Returns False when another processing action is already running.
        """
        result = await Run.get_motor_collection().update_one(
            {"_id": str(run_id), "processing_status": {"$ne": "processing"}},
            {"$set": {"processing_status": "processing", "processing_error": None}},
        )
        return bool(result and result.modified_count > 0)

    @staticmethod
    async def resolve_and_process_post_scrape(run_id: str, job_id: str, credential_id: str) -> str:
        """
        Auto-resolve file/sheet selection using persisted job preferences.
        Falls back to pending_* status when user interaction is needed.
        """
        run = await Run.get(run_id)
        job = await Job.get(job_id)
        if not run or not job:
            return "failed"

        originals = FileProcessorService._original_files(run)
        if not originals:
            await FileProcessorService._set_run_processing_state(run, "not_required")
            return "not_required"

        names = [f.get("filename") for f in originals if f.get("filename")]
        selected_filename: Optional[str] = None

        if job.last_selected_filename and job.last_selected_filename in names:
            selected_filename = job.last_selected_filename
        elif len(names) == 1:
            selected_filename = names[0]
        else:
            await FileProcessorService._set_run_processing_state(run, "pending_file_selection")
            return "pending_file_selection"

        if not selected_filename:
            await FileProcessorService._set_run_processing_state(
                run,
                "failed",
                processing_error="No selected filename available for processing.",
            )
            return "failed"

        selected_sheet: Optional[str] = None
        if is_excel_filename(selected_filename):
            artifacts_root = os.getenv("ARTIFACTS_DIR", "/app/artifacts")
            selected_path = Path(artifacts_root) / run_id / "original" / selected_filename
            sheet_options = list_sheet_names(str(selected_path)) if selected_path.exists() else []

            if not sheet_options:
                await FileProcessorService._set_run_processing_state(
                    run,
                    "failed",
                    selected_filename=selected_filename,
                    processing_error=f"Could not list sheets for {selected_filename}.",
                )
                return "failed"

            if job.last_selected_sheet and job.last_selected_sheet in sheet_options:
                selected_sheet = job.last_selected_sheet
            elif len(sheet_options) == 1:
                selected_sheet = sheet_options[0]
            else:
                await FileProcessorService._set_run_processing_state(
                    run,
                    "pending_sheet_selection",
                    selected_filename=selected_filename,
                )
                return "pending_sheet_selection"

        acquired = await FileProcessorService._acquire_processing_lock(run_id)
        if not acquired:
            return "processing"
        await FileProcessorService._set_run_processing_state(
            run,
            "processing",
            selected_filename=selected_filename,
            selected_sheet=selected_sheet,
        )

        processed_paths = await FileProcessorService.process_files(
            run_id=run_id,
            credential_id=credential_id,
            selected_filename=selected_filename,
            selected_sheet=selected_sheet,
            job_name=job.name or "job",
        )
        if not processed_paths:
            await FileProcessorService._set_run_processing_state(
                run,
                "failed",
                selected_filename=selected_filename,
                selected_sheet=selected_sheet,
                processing_error="Processor did not generate output files.",
            )
            return "failed"

        await FileProcessorService.append_processed_to_run(run_id, processed_paths)
        await job.update(
            {
                "$set": {
                    "last_selected_filename": selected_filename,
                    "last_selected_sheet": selected_sheet,
                    "selection_updated_at": get_now(),
                }
            }
        )
        await FileProcessorService._set_run_processing_state(
            run,
            "processed",
            selected_filename=selected_filename,
            selected_sheet=selected_sheet,
        )
        return "processed"

    @staticmethod
    async def process_with_user_selection(
        run_id: str,
        filename: str,
        selected_sheet: Optional[str] = None,
    ) -> str:
        run = await Run.get(run_id)
        if not run:
            return "failed"
        job = await Job.get(run.job_id) if run.job_id else None
        if not job or not job.credential_id:
            await FileProcessorService._set_run_processing_state(
                run, "failed", processing_error="Run has no linked credential/job."
            )
            return "failed"

        originals = FileProcessorService._original_files(run)
        names = {f.get("filename") for f in originals if f.get("filename")}
        if filename not in names:
            await FileProcessorService._set_run_processing_state(
                run, "failed", processing_error=f"Original file {filename} not found."
            )
            return "failed"

        if is_excel_filename(filename):
            artifacts_root = os.getenv("ARTIFACTS_DIR", "/app/artifacts")
            selected_path = Path(artifacts_root) / run_id / "original" / filename
            sheet_options = list_sheet_names(str(selected_path)) if selected_path.exists() else []
            if not selected_sheet:
                await FileProcessorService._set_run_processing_state(
                    run,
                    "pending_sheet_selection",
                    selected_filename=filename,
                )
                return "pending_sheet_selection"
            if selected_sheet not in sheet_options:
                await FileProcessorService._set_run_processing_state(
                    run,
                    "pending_sheet_selection",
                    selected_filename=filename,
                    processing_error=f"Sheet '{selected_sheet}' not found in {filename}.",
                )
                return "pending_sheet_selection"

        acquired = await FileProcessorService._acquire_processing_lock(run_id)
        if not acquired:
            await FileProcessorService._set_run_processing_state(
                run,
                "processing",
                selected_filename=filename,
                selected_sheet=selected_sheet,
                processing_error="Another processing execution is already running for this run.",
            )
            return "processing"
        await FileProcessorService._set_run_processing_state(
            run,
            "processing",
            selected_filename=filename,
            selected_sheet=selected_sheet,
            processing_error=None,
        )
        processed_paths = await FileProcessorService.process_files(
            run_id=run_id,
            credential_id=job.credential_id,
            selected_filename=filename,
            selected_sheet=selected_sheet,
            job_name=job.name or "job",
        )
        if not processed_paths:
            await FileProcessorService._set_run_processing_state(
                run,
                "failed",
                selected_filename=filename,
                selected_sheet=selected_sheet,
                processing_error="Processor did not generate output files.",
            )
            return "failed"

        await FileProcessorService.append_processed_to_run(run_id, processed_paths)
        await job.update(
            {
                "$set": {
                    "last_selected_filename": filename,
                    "last_selected_sheet": selected_sheet,
                    "selection_updated_at": get_now(),
                }
            }
        )
        await FileProcessorService._set_run_processing_state(
            run,
            "processed",
            selected_filename=filename,
            selected_sheet=selected_sheet,
            processing_error=None,
        )
        return "processed"

    @staticmethod
    async def _execute_processor(script: str, context: Dict) -> List[str]:
        """
        Execute a Python processor script in an isolated process.
        """
        script_path = None
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as handle:
            handle.write("# Auto-generated context\n")
            handle.write(f"original_dir = {context['original_dir']!r}\n")
            handle.write(f"processed_dir = {context['processed_dir']!r}\n")
            handle.write(f"carteira = {context.get('carteira', '')!r}\n")
            handle.write(f"metadata = {context.get('metadata', {})!r}\n")
            handle.write(f"run_id = {context['run_id']!r}\n")
            handle.write(f"credential_label = {context.get('credential_label', '')!r}\n")
            handle.write(f"selected_filename = {context.get('selected_filename', '')!r}\n")
            handle.write(f"selected_sheet = {context.get('selected_sheet', '')!r}\n")
            handle.write(f"source_excel_path = {context.get('source_excel_path', '')!r}\n\n")
            handle.write("# User script\n")
            handle.write(script)
            script_path = handle.name

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                timeout=300,
                capture_output=True,
                text=True,
                cwd=context["processed_dir"],
            )

            if result.returncode != 0:
                logger.error("Processor script failed: %s", result.stderr)
                raise RuntimeError(f"Processor failed: {result.stderr}")

            if result.stdout:
                logger.info("Processor output:\n%s", result.stdout)

            processed_dir = Path(context["processed_dir"])
            return [str(path) for path in processed_dir.glob("*") if path.is_file()]
        except subprocess.TimeoutExpired as exc:
            logger.error("Processor timeout (5 minutes)")
            raise RuntimeError("Processor timeout") from exc
        finally:
            if script_path:
                try:
                    os.unlink(script_path)
                except Exception:
                    pass
