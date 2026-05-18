from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable

from core.models.mongo_models import Run
from core.worker.executor import SeleniumExecutor


@dataclass(frozen=True)
class RunExecutionPlan:
    connector_name: str
    use_local: bool
    mode_label: str


@dataclass(frozen=True)
class DownloadCaptureContext:
    download_root: str
    run_download_dir: str
    scan_start_ts: float
    exclude_paths: set[str]
    exclude_signatures: dict[str, tuple[int, int, str]]


class RunExecutionModule:
    @staticmethod
    def build_plan(connector_name: str) -> RunExecutionPlan:
        ms_local_flag = str(os.getenv("MORGAN_STANLEY_USE_LOCAL_EVASION", "false")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        use_local = ("jpmorgan" in connector_name.lower()) or (
            connector_name == "morgan_stanley_login" and ms_local_flag
        )
        return RunExecutionPlan(
            connector_name=connector_name,
            use_local=use_local,
            mode_label="LOCAL_UC" if use_local else "REMOTE_GRID",
        )

    @staticmethod
    def start_executor(plan: RunExecutionPlan, download_dir: str) -> SeleniumExecutor:
        executor = SeleniumExecutor(use_local=plan.use_local, download_dir=download_dir)
        executor.start()
        return executor

    @staticmethod
    def prepare_download_context(run_id: str, download_root: str = "/downloads") -> DownloadCaptureContext:
        from core.services.file_manager import FileManager
        from core.utils.date_utils import get_now

        run_download_dir = os.path.join(download_root, run_id)
        os.makedirs(run_download_dir, exist_ok=True)
        try:
            os.chmod(run_download_dir, 0o777)
        except Exception:
            pass

        scan_start_ts = get_now().timestamp()
        preexisting_run_files: set[str] = set()
        if os.path.isdir(run_download_dir):
            for name in os.listdir(run_download_dir):
                candidate = os.path.join(run_download_dir, name)
                if os.path.isfile(candidate):
                    preexisting_run_files.add(os.path.abspath(candidate))

        preexisting_root_files: set[str] = set()
        if os.path.isdir(download_root):
            for name in os.listdir(download_root):
                candidate = os.path.join(download_root, name)
                if os.path.isfile(candidate):
                    preexisting_root_files.add(os.path.abspath(candidate))

        exclude_paths = preexisting_run_files | preexisting_root_files
        exclude_signatures = FileManager.build_file_signatures(exclude_paths)
        return DownloadCaptureContext(
            download_root=download_root,
            run_download_dir=run_download_dir,
            scan_start_ts=scan_start_ts,
            exclude_paths=exclude_paths,
            exclude_signatures=exclude_signatures,
        )

    @staticmethod
    async def capture_download_artifacts(
        *,
        run_id: str,
        run: Run,
        connector_name: str,
        execution_params: dict,
        context: DownloadCaptureContext,
        to_ddmmyyyy: Callable[[str | None, bool], str | None],
        is_history_file: Callable[[str], bool],
        log: Callable[[str], Awaitable[None]],
    ) -> bool:
        from core.services.excel_introspection import is_excel_filename, list_sheet_names
        from core.services.file_manager import FileManager

        original_paths = FileManager.capture_downloads(
            run_id,
            pattern="*",
            timeout_seconds=30,
            source_dir=context.run_download_dir,
            exclude_paths=context.exclude_paths,
            min_modified_time=context.scan_start_ts,
            preexisting_signatures=context.exclude_signatures,
        )

        if not original_paths:
            try:
                run_dir_entries = sorted(os.listdir(context.run_download_dir)) if os.path.isdir(context.run_download_dir) else []
                root_dir_entries = sorted(os.listdir(context.download_root)) if os.path.isdir(context.download_root) else []
                run_suffix = " ..." if len(run_dir_entries) > 50 else ""
                root_suffix = " ..." if len(root_dir_entries) > 50 else ""
                await log(
                    "DEBUG download dir snapshot "
                    f"run_dir={context.run_download_dir} entries={run_dir_entries[:50]}{run_suffix}"
                )
                await log(
                    "DEBUG download root snapshot "
                    f"root_dir={context.download_root} entries={root_dir_entries[:50]}{root_suffix}"
                )
            except Exception as debug_list_error:
                await log(f"DEBUG download snapshot error: {debug_list_error}")
            await log("No files downloaded")
            return False

        refreshed_run = await Run.get(run_id)
        prefer_month_first_dates = connector_name in {"btg_us_login", "btg_cayman_login"}
        report_date_ddmmyyyy = to_ddmmyyyy(
            (refreshed_run.report_date if refreshed_run else None)
            or execution_params.get("holdings_date")
            or execution_params.get("report_date"),
            prefer_month_first_dates,
        )
        history_date_ddmmyyyy = to_ddmmyyyy(
            (refreshed_run.history_date if refreshed_run else None)
            or execution_params.get("history_date"),
            prefer_month_first_dates,
        )
        default_date_ddmmyyyy = report_date_ddmmyyyy or history_date_ddmmyyyy or datetime.now().strftime("%d%m%Y")

        files_metadata = []
        for original_path in original_paths:
            current_name = os.path.basename(original_path)
            selected_date = (
                history_date_ddmmyyyy if is_history_file(current_name) else report_date_ddmmyyyy
            ) or default_date_ddmmyyyy
            renamed_original = FileManager.append_date_suffix(original_path, selected_date) or original_path
            files_metadata.append(
                {
                    "file_type": "original",
                    "filename": os.path.basename(renamed_original),
                    "path": FileManager.to_artifact_relative(renamed_original),
                    "size_bytes": FileManager.get_file_size(renamed_original),
                    "status": "ready",
                    "is_excel": is_excel_filename(os.path.basename(renamed_original)),
                    "sheet_options": (
                        list_sheet_names(renamed_original)
                        if is_excel_filename(os.path.basename(renamed_original))
                        else []
                    ),
                    "is_latest": False,
                }
            )

        if files_metadata:
            await run.update({"$set": {"files": files_metadata}})
            await log(f"Files captured: {len(files_metadata)} original file(s)")
        return True

    @staticmethod
    async def close_execution(
        *,
        executor: SeleniumExecutor,
        slot_token: str | None,
        run_download_dir: str | None,
        release_slot: Callable[[str], Awaitable[None]],
        log: Callable[[str], Awaitable[None]],
    ) -> None:
        executor.stop()
        if slot_token:
            await release_slot(slot_token)
        await log("Selenium session ended")

        if run_download_dir and os.path.isdir(run_download_dir):
            try:
                shutil.rmtree(run_download_dir, ignore_errors=True)
            except Exception:
                pass


run_execution = RunExecutionModule()
