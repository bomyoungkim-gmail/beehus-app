from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException

from core.models.mongo_models import Job
from core.models.mongo_models import Run
from core.services.excel_introspection import is_excel_filename
from core.services.file_processor import FileProcessorService
from core.utils.date_utils import get_now


class RunArtifactsModule:
    @staticmethod
    def artifacts_dir() -> Path:
        return Path(os.getenv("ARTIFACTS_DIR", "/app/artifacts"))

    @staticmethod
    def file_meta_to_dict(file_meta: Any) -> dict[str, Any]:
        if hasattr(file_meta, "model_dump"):
            return file_meta.model_dump()
        if hasattr(file_meta, "dict"):
            return getattr(file_meta, "dict")()
        if isinstance(file_meta, dict):
            return file_meta
        raise ValueError("Unsupported run file metadata format")

    @classmethod
    def resolve_artifact_path(cls, relative_path: str) -> Path:
        root = cls.artifacts_dir().resolve()
        candidate = (root / relative_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid artifact path")
        return candidate

    @classmethod
    def original_files(cls, run: Run) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for file_meta in run.files or []:
            candidate = cls.file_meta_to_dict(file_meta)
            if candidate.get("file_type") == "original":
                out.append(candidate)
        return out

    @classmethod
    def existing_files_only(cls, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        for file_meta in files:
            rel = file_meta.get("path")
            if not rel:
                filtered.append(file_meta)
                continue
            try:
                path = cls.resolve_artifact_path(rel)
                if path.exists() and path.is_file():
                    filtered.append(file_meta)
            except Exception:
                continue
        return filtered

    @staticmethod
    def to_iso8601_utc(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.isoformat()

    @classmethod
    def read_columns_from_file(
        cls, file_path: Path, filename: str, selected_sheet: Optional[str]
    ) -> list[str]:
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

    @staticmethod
    def _merge_aliases(current_aliases: list[str], values: list[str]) -> list[str]:
        merged = list(current_aliases)
        merged_lower = {m.lower() for m in merged if m}
        for value in values:
            normalized = (value or "").strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in merged_lower:
                continue
            merged.append(normalized)
            merged_lower.add(lowered)
        return merged

    @classmethod
    async def select_file_for_processing(
        cls,
        *,
        run: Run,
        job: Job,
        filename: str,
        sheet_options: list[str] | None = None,
    ) -> dict[str, Any]:
        originals = cls.original_files(run)
        selected = next((f for f in originals if f.get("filename") == filename), None)
        if not selected:
            raise HTTPException(status_code=404, detail="Selected file not found in run originals")

        now = get_now()
        if is_excel_filename(filename):
            options = sheet_options or []
            aliases = cls._merge_aliases(list(getattr(job, "sheet_aliases", []) or []), options)
            if len(options) == 1:
                await job.update(
                    {
                        "$set": {
                            "last_selected_filename": filename,
                            "last_selected_sheet": options[0],
                            "sheet_aliases": cls._merge_aliases(aliases, [options[0]]),
                            "selection_updated_at": now,
                        }
                    }
                )
                await run.update(
                    {
                        "$set": {
                            "processing_status": "pending_reprocess",
                            "selected_filename": filename,
                            "selected_sheet": options[0],
                            "processing_error": None,
                        }
                    }
                )
                return {
                    "status": "pending_reprocess",
                    "selected_filename": filename,
                    "selected_sheet": options[0],
                }

            await job.update(
                {
                    "$set": {
                        "last_selected_filename": filename,
                        "last_selected_sheet": None,
                        "sheet_aliases": aliases,
                        "selection_updated_at": now,
                    }
                }
            )
            await run.update(
                {
                    "$set": {
                        "processing_status": "pending_sheet_selection",
                        "selected_filename": filename,
                        "selected_sheet": None,
                        "processing_error": None,
                    }
                }
            )
            return {
                "status": "pending_sheet_selection",
                "selected_filename": filename,
                "sheet_options": options,
            }

        await job.update(
            {
                "$set": {
                    "last_selected_filename": filename,
                    "last_selected_sheet": None,
                    "selection_updated_at": now,
                }
            }
        )
        await run.update(
            {
                "$set": {
                    "processing_status": "pending_reprocess",
                    "selected_filename": filename,
                    "selected_sheet": None,
                    "processing_error": None,
                }
            }
        )
        return {"status": "pending_reprocess", "selected_filename": filename}

    @classmethod
    async def select_sheet_for_processing(
        cls,
        *,
        run: Run,
        job: Job,
        filename: str,
        selected_sheet: str,
    ) -> dict[str, Any]:
        merged_aliases = cls._merge_aliases(
            list(getattr(job, "sheet_aliases", []) or []),
            [selected_sheet],
        )
        await job.update(
            {
                "$set": {
                    "last_selected_filename": filename,
                    "last_selected_sheet": selected_sheet,
                    "sheet_aliases": merged_aliases,
                    "selection_updated_at": get_now(),
                }
            }
        )
        await run.update(
            {
                "$set": {
                    "processing_status": "pending_reprocess",
                    "selected_filename": filename,
                    "selected_sheet": selected_sheet,
                    "processing_error": None,
                }
            }
        )
        return {
            "status": "pending_reprocess",
            "selected_filename": filename,
            "selected_sheet": selected_sheet,
        }

    @classmethod
    async def resolve_reprocess_target(
        cls,
        *,
        run: Run,
        job: Job,
        filename: Optional[str],
    ) -> tuple[str, list[str]] | dict[str, str]:
        originals = cls.original_files(run)
        names = [f.get("filename") for f in originals if f.get("filename")]
        if not names:
            raise HTTPException(status_code=400, detail="Run has no original files to process")

        target = filename or getattr(run, "selected_filename", None) or job.last_selected_filename
        if not target:
            if len(names) == 1:
                target = names[0]
            else:
                await run.update({"$set": {"processing_status": "pending_file_selection", "processing_error": None}})
                return {"status": "pending_file_selection"}

        if target not in names:
            raise HTTPException(status_code=400, detail=f"File '{target}' not found among run originals")
        return target, names

    @classmethod
    async def process_with_selection(
        cls,
        *,
        run_id: str,
        run: Run,
        job: Job,
        filename: Optional[str],
        selected_sheet: Optional[str],
        file_processor_service: Any = FileProcessorService,
    ) -> dict[str, Any]:
        resolved = await cls.resolve_reprocess_target(run=run, job=job, filename=filename)
        if isinstance(resolved, dict):
            return resolved

        target_filename, _ = resolved
        target_sheet = selected_sheet or getattr(run, "selected_sheet", None) or job.last_selected_sheet
        state = await file_processor_service.process_with_user_selection(
            run_id=run_id,
            filename=target_filename,
            selected_sheet=target_sheet,
        )
        if state == "failed":
            refreshed = await Run.get(run_id)
            detail = refreshed.processing_error if refreshed else "Processing failed"
            raise HTTPException(status_code=400, detail=detail)

        return {
            "status": state,
            "selected_filename": target_filename,
            "selected_sheet": target_sheet,
        }

    @classmethod
    async def process_from_snapshot(
        cls,
        *,
        run_id: str,
        run: Run,
        job: Job,
        processed_filename: str,
        filename: Optional[str],
        selected_sheet: Optional[str],
        file_processor_service: Any = FileProcessorService,
    ) -> dict[str, Any]:
        processed_candidates = [
            cls.file_meta_to_dict(f)
            for f in (run.files or [])
            if cls.file_meta_to_dict(f).get("file_type") == "processed"
        ]
        source_processed = next(
            (f for f in processed_candidates if f.get("filename") == processed_filename),
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

        resolved = await cls.resolve_reprocess_target(run=run, job=job, filename=filename)
        if isinstance(resolved, dict):
            return resolved

        target_filename, _ = resolved
        target_sheet = selected_sheet or getattr(run, "selected_sheet", None) or job.last_selected_sheet
        snapshot_meta = {
            "processor_id": source_processed.get("processor_id"),
            "processor_version": source_processed.get("processor_version"),
            "processor_name": source_processed.get("processor_name"),
            "processor_script_snapshot": script_snapshot,
            "processor_source": "snapshot",
        }
        state = await file_processor_service.process_with_user_selection(
            run_id=run_id,
            filename=target_filename,
            selected_sheet=target_sheet,
            script_override=script_snapshot,
            processor_snapshot_override=snapshot_meta,
        )
        if state == "failed":
            refreshed = await Run.get(run_id)
            detail = refreshed.processing_error if refreshed else "Processing failed"
            raise HTTPException(status_code=400, detail=detail)

        return {
            "status": state,
            "selected_filename": target_filename,
            "selected_sheet": target_sheet,
            "source_processed_filename": processed_filename,
            "processor_source": "snapshot",
        }


run_artifacts = RunArtifactsModule()
