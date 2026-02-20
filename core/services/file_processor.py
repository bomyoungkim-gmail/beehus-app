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
import textwrap
import traceback
import unicodedata
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.models.mongo_models import Credential, Job, Run
from core.services.excel_introspection import is_excel_filename, list_sheet_names
from core.services.file_manager import FileManager
from core.services.visual_processing import build_script_from_processing_config
from core.utils.date_utils import get_now

logger = logging.getLogger(__name__)


class FileProcessorService:
    """Service for executing job-bound file processors."""

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
    def _normalize_sheet_key(name: str) -> str:
        text = (name or "").strip().lower()
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r"[^a-z0-9]+", " ", text).strip()
        return text

    @staticmethod
    def _patch_legacy_visual_script(script: str) -> str:
        s = script or ""
        if "VISUAL_BUILDER_" not in s:
            return s
        # Sanitiza bug legado onde "\\n" literal foi salvo dentro da linha de código.
        s = s.replace(
            ')\\ncaixa = caixa | caixa_raw.str.contains("caixa|conta corrente|saldo em conta", na=False)',
            ')\ncaixa = caixa | caixa_raw.str.contains("caixa|conta corrente|saldo em conta", na=False)',
        )
        s = s.replace(
            '"Data": (report_date or data_do_arquivo(arquivo)),\\n    "Carteira": carteira,',
            '"Data": (report_date or data_do_arquivo(arquivo)),\n    "Carteira": carteira,',
        )
        legacy_line_patterns = [
            '        return pd.to_numeric(df[col], errors="coerce").fillna(default)',
            "        return pd.to_numeric(df[col], errors='coerce').fillna(default)",
        ]
        improved_block = "\n".join(
            [
                "        raw = df[col]",
                "        parsed = pd.to_numeric(raw, errors='coerce')",
                "        if parsed.notna().any():",
                "            return parsed.fillna(default)",
                "        return raw.apply(ptbr_to_float).fillna(default)",
            ]
        )
        for pattern in legacy_line_patterns:
            if pattern in s:
                s = s.replace(pattern, improved_block)
        if 'caixa = caixa_raw.isin(["1", "true", "sim", "s", "yes", "y"])' in s and "conta corrente" not in s:
            s = s.replace(
                'caixa = caixa_raw.isin(["1", "true", "sim", "s", "yes", "y"])',
                'caixa = caixa_raw.isin(["1", "true", "sim", "s", "yes", "y"])\n'
                'caixa = caixa | caixa_raw.str.contains("caixa|conta corrente|saldo em conta", na=False)',
            )
        if '"Data": data_do_arquivo(arquivo),' in s:
            s = s.replace(
                '"Data": data_do_arquivo(arquivo),',
                '"Data": (report_date or data_do_arquivo(arquivo)),\n    "Carteira": carteira,',
            )
        if "return out" not in s and "out = out.loc[mask].reset_index(drop=True)" in s:
            s = s.rstrip() + "\n\nreturn out\n"
        return s

    @staticmethod
    def _pick_sheet_by_aliases(
        sheet_options: List[str],
        preferred: Optional[str],
        aliases: Optional[List[str]] = None,
    ) -> Optional[str]:
        if not sheet_options:
            return None
        normalized_options = {
            FileProcessorService._normalize_sheet_key(opt): opt for opt in sheet_options
        }

        candidates: List[str] = []
        if preferred:
            candidates.append(preferred)
        for alias in aliases or []:
            if alias and alias not in candidates:
                candidates.append(alias)

        for candidate in candidates:
            key = FileProcessorService._normalize_sheet_key(candidate)
            if key in normalized_options:
                return normalized_options[key]

        # token-overlap fallback
        for candidate in candidates:
            c_key = FileProcessorService._normalize_sheet_key(candidate)
            if not c_key:
                continue
            c_tokens = set(c_key.split())
            if not c_tokens:
                continue
            best = None
            best_score = 0
            for opt in sheet_options:
                o_key = FileProcessorService._normalize_sheet_key(opt)
                o_tokens = set(o_key.split())
                score = len(c_tokens & o_tokens)
                if score > best_score:
                    best_score = score
                    best = opt
            if best and best_score >= max(1, len(c_tokens) // 2):
                return best
        return None

    @staticmethod
    def _count_input_rows(
        original_dir: str,
        selected_filename: Optional[str],
        selected_sheet: Optional[str],
    ) -> Optional[int]:
        if not selected_filename:
            return None
        try:
            import pandas as pd
            input_path = Path(original_dir) / selected_filename
            if not input_path.exists():
                return None
            ext = input_path.suffix.lower()
            if ext in {".xlsx", ".xls", ".xlsm", ".xlsb"}:
                sheet_name = selected_sheet if selected_sheet not in (None, "") else 0
                df = pd.read_excel(str(input_path), sheet_name=sheet_name)
                return int(len(df.index))
            if ext == ".csv":
                try:
                    df = pd.read_csv(str(input_path), sep=None, engine="python")
                except Exception:
                    df = pd.read_csv(str(input_path), sep=";", decimal=",")
                return int(len(df.index))
        except Exception:
            return None
        return None

    @staticmethod
    def _validate_processed_outputs(
        file_paths: List[str],
        expected_input_rows: Optional[int] = None,
    ) -> Optional[str]:
        if not file_paths:
            return "Processor did not generate output files."
        required_cols = {"Data", "Ativo", "Quant", "PU", "SaldoBruto", "Caixa", "Moeda"}
        for path in file_paths:
            p = Path(path)
            if p.suffix.lower() != ".csv":
                continue
            try:
                import pandas as pd
                df = pd.read_csv(str(p), sep=None, engine="python")
                cols = set(map(str, df.columns))
                missing = sorted(required_cols - cols)
                if missing:
                    return f"Processed output missing required columns: {', '.join(missing)}."
                output_rows = len(df.index)
                if output_rows == 0:
                    return "Processed output generated 0 rows."
                if (
                    expected_input_rows is not None
                    and expected_input_rows > 0
                    and output_rows < expected_input_rows
                ):
                    return (
                        "Data loss detected in processing: "
                        f"input_rows={expected_input_rows}, output_rows={output_rows}. "
                        "Output cannot have fewer rows than input."
                    )
                return None
            except Exception as exc:
                return f"Failed to validate processed CSV output: {exc}"
        return None

    @staticmethod
    def resolve_job_processing_script(job: Job) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        script = None
        processing_config = getattr(job, "processing_config_json", None)
        if processing_config:
            script, normalized = build_script_from_processing_config(processing_config)
            if normalized is not None:
                processing_config = normalized
        if not script:
            script = getattr(job, "processing_script", None)
        if script:
            script = str(script).strip()
        if not script:
            return None, processing_config if isinstance(processing_config, dict) else None
        script = FileProcessorService._patch_legacy_visual_script(script)
        snapshot = {
            "processor_id": None,
            "processor_version": None,
            "processor_name": f"job:{job.name}",
            "processor_script_snapshot": script,
            "processor_source": "job",
        }
        return script, snapshot

    @staticmethod
    async def _append_processing_log(run_id: str, message: str) -> None:
        run = await Run.get(run_id)
        if not run:
            return
        timestamped = f"[{get_now().time()}] {message}"
        await run.update({"$push": {"processing_logs": timestamped}})

    @staticmethod
    async def process_files(
        run_id: str,
        credential_id: Optional[str],
        selected_filename: Optional[str] = None,
        selected_sheet: Optional[str] = None,
        job_name: str = "job",
        script_override: Optional[str] = None,
        processor_snapshot_override: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[str], Optional[Dict[str, Any]], Optional[str]]:
        """
        Process files for a run using explicit script (job/snapshot).
        """
        try:
            processor_script = script_override
            processor_snapshot = processor_snapshot_override

            if not processor_script:
                logger.info("No script provided for run %s processing", run_id)
                await FileProcessorService._append_processing_log(run_id, "No script provided for processing")
                return [], None, "No script provided for processing."

            credential = await Credential.get(credential_id) if credential_id else None

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
                "carteira": credential.carteira if credential else "",
                "metadata": credential.metadata if credential else {},
                "run_id": run_id,
                "credential_label": credential.label if credential else "",
                "selected_filename": selected_filename or "",
                "selected_sheet": selected_sheet or "",
                "source_excel_path": source_excel_path,
                "report_date": "",
                "history_date": "",
            }
            run_doc = await Run.get(run_id)
            if run_doc:
                context["report_date"] = run_doc.report_date or ""
                context["history_date"] = run_doc.history_date or ""

            logger.info("Executing script snapshot for run %s", run_id)
            await FileProcessorService._append_processing_log(
                run_id,
                f"Executing processor script for file={selected_filename or '-'} sheet={selected_sheet or '-'}",
            )

            processed_files = await FileProcessorService._execute_processor(
                processor_script,
                context,
            )

            renamed_files = FileProcessorService._normalize_processed_names(
                processed_files,
                job_name=job_name,
            )

            expected_input_rows = FileProcessorService._count_input_rows(
                str(original_dir),
                selected_filename,
                selected_sheet,
            )
            validation_error = FileProcessorService._validate_processed_outputs(
                renamed_files,
                expected_input_rows=expected_input_rows,
            )
            if validation_error:
                await FileProcessorService._append_processing_log(run_id, validation_error)
                return [], processor_snapshot, validation_error

            logger.info("Processor completed: %s file(s) generated", len(renamed_files))
            await FileProcessorService._append_processing_log(
                run_id,
                f"Processing finished successfully. Output files: {len(renamed_files)}",
            )
            return renamed_files, processor_snapshot, None
        except Exception as exc:
            logger.error("File processing failed for run %s: %s", run_id, exc)
            detail = str(exc) or "Unknown processing error"
            await FileProcessorService._append_processing_log(
                run_id,
                f"Processing failed: {detail}\n{traceback.format_exc()}",
            )
            return [], None, detail

    @staticmethod
    def _normalize_processed_names(file_paths: List[str], job_name: str) -> List[str]:
        if not file_paths:
            return []
        processing_stamp = get_now().strftime("%d-%m-%Y--%H-%M-%S")
        renamed: List[str] = []
        for idx, old_path in enumerate(sorted(file_paths), start=1):
            path = Path(old_path)
            ext = path.suffix or ".csv"
            suffix = f"_{idx:02d}" if len(file_paths) > 1 else ""
            target = path.parent / f"positions_processado-{processing_stamp}{suffix}{ext}"
            collision = 1
            while target.exists() and target != path:
                target = path.parent / f"positions_processado-{processing_stamp}{suffix}_{collision:02d}{ext}"
                collision += 1
            if target != path:
                path.rename(target)
            renamed.append(str(target))
        return renamed

    @staticmethod
    async def append_processed_to_run(
        run_id: str,
        processed_paths: List[str],
        processor_snapshot: Optional[Dict[str, Any]] = None,
    ) -> int:
        current_run = await Run.get(run_id)
        if not current_run:
            return 0

        current_files_raw = FileProcessorService._run_files_to_dicts(current_run)
        artifacts_root = Path(os.getenv("ARTIFACTS_DIR", "/app/artifacts"))
        current_files: List[Dict[str, Any]] = []
        for existing in current_files_raw:
            raw_path = str(existing.get("path") or "").strip()
            if not raw_path:
                current_files.append(existing)
                continue
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = artifacts_root / raw_path
            if candidate.exists():
                current_files.append(existing)
            else:
                logger.warning("Dropping stale run file metadata (missing on disk): %s", raw_path)
        for existing in current_files:
            if existing.get("file_type") == "processed":
                existing["is_latest"] = False

        for processed_path in processed_paths:
            snapshot = processor_snapshot or {}
            current_files.append(
                {
                    "file_type": "processed",
                    "filename": os.path.basename(processed_path),
                    "path": FileManager.to_artifact_relative(processed_path),
                    "size_bytes": FileManager.get_file_size(processed_path),
                    "status": "ready",
                    "is_latest": True,
                    "processor_id": snapshot.get("processor_id"),
                    "processor_version": snapshot.get("processor_version"),
                    "processor_name": snapshot.get("processor_name"),
                    "processor_script_snapshot": snapshot.get("processor_script_snapshot"),
                    "processor_source": snapshot.get("processor_source"),
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
    async def resolve_and_process_post_scrape(
        run_id: str,
        job_id: str,
        credential_id: Optional[str] = None,
    ) -> str:
        """
        Auto-resolve file/sheet selection using persisted job preferences.
        Falls back to pending_* status when user interaction is needed.
        """
        run = await Run.get(run_id)
        job = await Job.get(job_id)
        if not run or not job:
            return "failed"
        await FileProcessorService._append_processing_log(
            run_id,
            f"Starting auto-processing for job={job_id}",
        )

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

            preferred_sheet = FileProcessorService._pick_sheet_by_aliases(
                sheet_options,
                job.last_selected_sheet,
                getattr(job, "sheet_aliases", []),
            )
            if preferred_sheet:
                selected_sheet = preferred_sheet
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

        script_override = None
        snapshot_override = None
        if getattr(job, "enable_processing", False):
            script_override, snapshot_override = FileProcessorService.resolve_job_processing_script(job)
        if not script_override:
            await FileProcessorService._set_run_processing_state(
                run,
                "failed",
                selected_filename=selected_filename,
                selected_sheet=selected_sheet,
                processing_error="No processing script configured for this job.",
            )
            return "failed"
        processed_paths, processor_snapshot, process_error = await FileProcessorService.process_files(
            run_id=run_id,
            credential_id=credential_id,
            selected_filename=selected_filename,
            selected_sheet=selected_sheet,
            job_name=job.name or "job",
            script_override=script_override,
            processor_snapshot_override=snapshot_override,
        )
        if not processed_paths:
            await FileProcessorService._set_run_processing_state(
                run,
                "failed",
                selected_filename=selected_filename,
                selected_sheet=selected_sheet,
                processing_error=process_error or "Processor did not generate output files.",
            )
            return "failed"

        await FileProcessorService.append_processed_to_run(
            run_id,
            processed_paths,
            processor_snapshot=processor_snapshot,
        )
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
        script_override: Optional[str] = None,
        processor_snapshot_override: Optional[Dict[str, Any]] = None,
    ) -> str:
        run = await Run.get(run_id)
        if not run:
            return "failed"
        job = await Job.get(run.job_id) if run.job_id else None
        await FileProcessorService._append_processing_log(
            run_id,
            f"Starting manual processing for file={filename} sheet={selected_sheet or '-'}",
        )
        if not job:
            await FileProcessorService._set_run_processing_state(
                run, "failed", processing_error="Run has no linked job."
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
                alias_sheet = FileProcessorService._pick_sheet_by_aliases(
                    sheet_options,
                    selected_sheet,
                    getattr(job, "sheet_aliases", []),
                )
                if alias_sheet:
                    selected_sheet = alias_sheet
                else:
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
        local_script_override = script_override
        local_snapshot_override = processor_snapshot_override
        if not local_script_override and getattr(job, "enable_processing", False):
            local_script_override, local_snapshot_override = FileProcessorService.resolve_job_processing_script(job)
        if not local_script_override:
            await FileProcessorService._set_run_processing_state(
                run,
                "failed",
                selected_filename=filename,
                selected_sheet=selected_sheet,
                processing_error="No processing script configured for this job.",
            )
            return "failed"
        processed_paths, processor_snapshot, process_error = await FileProcessorService.process_files(
            run_id=run_id,
            credential_id=job.credential_id,
            selected_filename=filename,
            selected_sheet=selected_sheet,
            job_name=job.name or "job",
            script_override=local_script_override,
            processor_snapshot_override=local_snapshot_override,
        )
        if not processed_paths:
            await FileProcessorService._set_run_processing_state(
                run,
                "failed",
                selected_filename=filename,
                selected_sheet=selected_sheet,
                processing_error=process_error or "Processor did not generate output files.",
            )
            return "failed"

        await FileProcessorService.append_processed_to_run(
            run_id,
            processed_paths,
            processor_snapshot=processor_snapshot,
        )
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
        final_processed_dir = Path(context["processed_dir"])
        final_processed_dir.mkdir(parents=True, exist_ok=True)
        staging_dir = final_processed_dir / f".tmp_exec_{uuid.uuid4().hex}"
        staging_dir.mkdir(parents=True, exist_ok=True)

        exec_context = dict(context)
        exec_context["processed_dir"] = str(staging_dir)

        wrapped_script = FileProcessorService._build_wrapped_script(script, exec_context)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as handle:
            handle.write(wrapped_script)
            script_path = handle.name

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                timeout=300,
                capture_output=True,
                text=True,
                cwd=str(staging_dir),
            )

            if result.returncode != 0:
                logger.error("Processor script failed: %s", result.stderr)
                raise RuntimeError(f"Processor failed: {result.stderr}")

            if result.stdout:
                logger.info("Processor output:\n%s", result.stdout)

            staged_files = [path for path in staging_dir.glob("*") if path.is_file()]
            promoted_files: List[str] = []
            for staged_file in sorted(staged_files):
                target = final_processed_dir / staged_file.name
                if target.exists():
                    stem = target.stem
                    suffix = target.suffix
                    counter = 1
                    while target.exists():
                        target = final_processed_dir / f"{stem}_{counter:02d}{suffix}"
                        counter += 1
                staged_file.replace(target)
                promoted_files.append(str(target))
            return promoted_files
        except subprocess.TimeoutExpired as exc:
            logger.error("Processor timeout (5 minutes)")
            raise RuntimeError("Processor timeout") from exc
        finally:
            if script_path:
                try:
                    os.unlink(script_path)
                except Exception:
                    pass
            try:
                if staging_dir.exists():
                    for leftovers in staging_dir.glob("*"):
                        try:
                            leftovers.unlink(missing_ok=True)
                        except Exception:
                            pass
                    staging_dir.rmdir()
            except Exception:
                pass

    @staticmethod
    def _is_full_script(script: str) -> bool:
        if not script:
            return False
        return bool(
            re.search(
                r"(^|\n)\s*(import\s+|from\s+\S+\s+import\s+|def\s+|if\s+__name__\s*==)",
                script,
            )
        )

    @staticmethod
    def _should_force_low_code(script: str) -> bool:
        """
        Treat script as low-code when it clearly expects wrapper-provided context.
        This prevents false positives from helper `def` lines in visual scripts.
        """
        s = script or ""
        markers = [
            "VISUAL_BUILDER_",
            "df_input",
            "arquivo",
            "aba",
            "carteira",
            "original_dir",
            "processado_dir",
        ]
        return any(m in s for m in markers)

    @staticmethod
    def _build_preamble_and_context(context: Dict) -> str:
        return "\n".join(
            [
                "import logging",
                "import os",
                "import re",
                "import sys",
                "from datetime import datetime",
                "from pathlib import Path",
                "",
                "try:",
                "    import pandas as pd",
                "    import numpy as np",
                "except ImportError:",
                "    pass",
                "",
                "def ptbr_to_float(x):",
                "    if x is None:",
                "        return None",
                "    s = str(x).strip()",
                "    if not s:",
                "        return None",
                "    s = s.replace('.', '').replace(',', '.')",
                "    try:",
                "        return float(s)",
                "    except Exception:",
                "        return None",
                "",
                "def data_do_arquivo(nome):",
                "    m = re.search(r'(\\d{2})-(\\d{2})-(\\d{4})', str(nome or ''))",
                "    if m:",
                "        return f\"{m.group(1)}/{m.group(2)}/{m.group(3)}\"",
                "    m = re.search(r'(\\d{2})(\\d{2})(\\d{4})', str(nome or ''))",
                "    if m:",
                "        return f\"{m.group(1)}/{m.group(2)}/{m.group(3)}\"",
                "    return datetime.now().strftime('%d/%m/%Y')",
                "",
                "# Auto-generated context",
                f"original_dir = {context['original_dir']!r}",
                f"processed_dir = {context['processed_dir']!r}",
                f"carteira = {context.get('carteira', '')!r}",
                f"metadata = {context.get('metadata', {})!r}",
                f"run_id = {context['run_id']!r}",
                f"credential_label = {context.get('credential_label', '')!r}",
                f"selected_filename = {context.get('selected_filename', '')!r}",
                f"selected_sheet = {context.get('selected_sheet', '')!r}",
                f"source_excel_path = {context.get('source_excel_path', '')!r}",
                f"report_date = {context.get('report_date', '')!r}",
                f"history_date = {context.get('history_date', '')!r}",
                "",
                "# Aliases em portugues",
                "arquivo = selected_filename",
                "aba = selected_sheet",
                "saida_dir = processed_dir",
                "",
            ]
        )

    @staticmethod
    def _build_wrapped_script(script: str, context: Dict) -> str:
        preamble = FileProcessorService._build_preamble_and_context(context)
        normalized_script = (script or "").rstrip() + "\n"

        if (
            FileProcessorService._is_full_script(normalized_script)
            and not FileProcessorService._should_force_low_code(normalized_script)
        ):
            return f"{preamble}\n# User script (advanced mode)\n{normalized_script}"

        user_body = normalized_script.strip("\n")
        if not user_body:
            user_body = "return None"
        indented_body = textwrap.indent(user_body, "    ")
        auto_wrapper = "\n".join(
            [
                "def _load_input_dataframe(arquivo, aba):",
                "    if not arquivo:",
                "        return None",
                "    caminho = Path(original_dir) / arquivo",
                "    if not caminho.exists():",
                "        raise FileNotFoundError(f'Input file not found: {caminho}')",
                "    ext = caminho.suffix.lower()",
                "    if ext in ('.xlsx', '.xls', '.xlsm', '.xlsb'):",
                "        sheet_name = aba if aba not in (None, '') else 0",
                "        return pd.read_excel(caminho, sheet_name=sheet_name)",
                "    if ext == '.csv':",
                "        try:",
                "            return pd.read_csv(caminho, sep=None, engine='python')",
                "        except Exception:",
                "            return pd.read_csv(caminho, sep=';', decimal=',')",
                "    if ext == '.parquet':",
                "        return pd.read_parquet(caminho)",
                "    raise RuntimeError(f'Unsupported input file type: {ext}')",
                "",
                "def process_auto_generated(arquivo, aba, carteira, df_input):",
                indented_body,
                "",
                "if __name__ == '__main__':",
                "    try:",
                "        df_input = _load_input_dataframe(arquivo, aba)",
                "        resultado = process_auto_generated(arquivo, aba, carteira, df_input)",
                "        if hasattr(resultado, 'to_csv'):",
                "            if hasattr(resultado, 'columns') and 'Carteira' not in resultado.columns:",
                "                resultado = resultado.copy()",
                "                resultado['Carteira'] = carteira",
                "            base_name = Path(arquivo).stem if arquivo else 'output'",
                "            nome_saida = f'processed_{base_name}.csv'",
                "            caminho_saida = Path(processed_dir) / nome_saida",
                "            resultado.to_csv(caminho_saida, index=False, sep=';', decimal=',')",
                "            print(f'Auto-saved: {caminho_saida}')",
                "    except Exception as e:",
                "        print(f'Error in auto-generated script: {e}', file=sys.stderr)",
                "        raise e",
                "",
            ]
        )
        return f"{preamble}\n# User script (low-code mode)\n{auto_wrapper}"
