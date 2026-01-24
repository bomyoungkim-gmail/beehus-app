"""
BTG MFO connector - refactored to application standard.
"""

import asyncio
import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional

from selenium.webdriver.remote.webdriver import WebDriver

from core.connectors.base import BaseConnector
from core.schemas.messages import ScrapeResult
from core.connectors.helpers.selenium_helpers import SeleniumHelpers
from core.connectors.seletores.btg_mfo import SeletorBtgMfo
from core.connectors.actions.btg_mfo_actions import BtgMfoActions
from core.connectors.utils.date_calculator import calculate_holdings_date, calculate_history_date
from core.utils.date_utils import get_now

logger = logging.getLogger(__name__)


@dataclass
class BtgMfoCredentials:
    """Credentials for BTG MFO access."""
    username: str
    password: str


class BtgMfoConnector(BaseConnector):
    """Connector for BTG MFO portal automation."""

    @property
    def name(self) -> str:
        return "btg_mfo_login"

    # ========== SETUP E HELPERS ==========

    def _make_run_logger(self, run):
        async def log(msg: str):
            logger.info(f"[BTG MFO] {msg}")
            if run:
                timestamped_msg = f"[{get_now().time()}] {msg}"
                await run.update({"$push": {"logs": timestamped_msg}})
        return log

    async def _setup_run(self, params: Dict[str, Any]):
        from core.models.mongo_models import Run

        run_id = params.get("run_id")
        run = await Run.get(run_id) if run_id else None
        log = self._make_run_logger(run)
        return run, log

    def _validate_credentials(self, params: Dict[str, Any]) -> Optional[BtgMfoCredentials]:
        username = params.get("username") or params.get("user")
        password = params.get("password") or params.get("pass")
        if not username or not password:
            return None
        return BtgMfoCredentials(username=username, password=password)

    def _create_actions(self, driver: WebDriver, log_func) -> BtgMfoActions:
        helpers = SeleniumHelpers(driver, timeout=50)
        selectors = SeletorBtgMfo()
        return BtgMfoActions(driver, helpers, selectors, log_func)

    def _categorize_file_type(self, filename: str) -> str:
        lower_name = filename.lower()
        if "moviment" in lower_name:
            return "transactions"
        if "posi" in lower_name:
            return "positions"
        return "unknown"

    async def _wait_for_downloads(
        self,
        downloads_dir: Path,
        expected_count: int,
        log,
        timeout_seconds: int = 180,
    ) -> list[Path]:
        start_time = time.time()
        last_sizes: Dict[str, int] = {}

        await log("Waiting for downloaded files...")
        while time.time() - start_time < timeout_seconds:
            files = list(downloads_dir.glob("*.xlsx"))
            if len(files) >= expected_count:
                sizes = {str(path): path.stat().st_size for path in files}
                if sizes == last_sizes and all(size > 0 for size in sizes.values()):
                    return files
                last_sizes = sizes
            await asyncio.sleep(2)

        raise RuntimeError("Timed out waiting for downloads")

    async def _organize_downloads(
        self,
        run_id: str,
        log,
        expect_positions: bool,
        expect_transactions: bool,
    ) -> Dict[str, str]:
        downloads_dir = Path(os.getenv("DOWNLOADS_DIR", "/downloads"))
        artifacts_dir = Path(f"/app/artifacts/{run_id}")
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        expected_count = int(expect_positions) + int(expect_transactions)
        if expected_count == 0:
            await log("No exports requested; skipping download organization.")
            return {}
        files = await self._wait_for_downloads(downloads_dir, expected_count, log)

        latest_by_type: Dict[str, Path] = {}
        for file_path in files:
            file_type = self._categorize_file_type(file_path.name)
            if file_type == "unknown":
                continue
            existing = latest_by_type.get(file_type)
            if not existing or file_path.stat().st_mtime > existing.stat().st_mtime:
                latest_by_type[file_type] = file_path

        ordered_files = sorted(files, key=lambda p: p.stat().st_mtime)
        assigned = set(latest_by_type.values())
        fallback_iter = (p for p in ordered_files if p not in assigned)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        result_paths: Dict[str, str] = {}

        if expect_positions:
            source = latest_by_type.get("positions")
            if not source:
                source = next(fallback_iter, None)
            if not source:
                raise RuntimeError("Positions file not found in downloads")
            dest = artifacts_dir / f"btg_mfo_positions_{timestamp}.xlsx"
            shutil.copy2(source, dest)
            result_paths["positions"] = str(dest)

        if expect_transactions:
            source = latest_by_type.get("transactions")
            if not source:
                source = next(fallback_iter, None)
            if not source:
                raise RuntimeError("Transactions file not found in downloads")
            dest = artifacts_dir / f"btg_mfo_transactions_{timestamp}.xlsx"
            shutil.copy2(source, dest)
            result_paths["transactions"] = str(dest)

        await log(f"Files organized in: {artifacts_dir}")
        return result_paths

    def _success_result(self, run_id: Optional[str], data: Dict[str, Any]) -> ScrapeResult:
        return ScrapeResult(run_id=run_id, success=True, data=data)

    def _error_result(self, run_id: Optional[str], error: str) -> ScrapeResult:
        return ScrapeResult(run_id=run_id, success=False, error=error)

    async def _handle_error(
        self,
        e: Exception,
        driver: WebDriver,
        run_id: Optional[str],
        log_func,
        credentials: Optional[BtgMfoCredentials] = None,
    ) -> ScrapeResult:
        error_msg = str(e)
        if credentials:
            await log_func(
                f"ERROR BTG MFO failed for user {credentials.username}: {error_msg}"
            )
        else:
            await log_func(f"ERROR BTG MFO failed: {error_msg}")

        try:
            timestamp = get_now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"/app/artifacts/error_btg_mfo_{timestamp}.png"
            driver.save_screenshot(screenshot_path)
            await log_func(f"SCREEN Screenshot saved: {screenshot_path}")
        except Exception as ss_e:
            await log_func(f"WARN Screenshot failed: {ss_e}")

        return self._error_result(run_id, error_msg)

    # ========== MAIN SCRAPE METHOD ==========

    async def scrape(self, driver: WebDriver, params: Dict[str, Any]) -> ScrapeResult:
        run, log = await self._setup_run(params)
        run_id = params.get("run_id")

        logger.info(f"Starting BTG MFO flow with params: {params}")

        credentials = self._validate_credentials(params)
        if not credentials:
            error_msg = "Missing credentials - check username and password"
            logger.error(error_msg)
            await log(f"ERROR {error_msg}")
            await log(f"INFO Available params: {list(params.keys())}")
            return self._error_result(run_id, error_msg)

        actions = self._create_actions(driver, log)

        try:
            # Resolve parameters
            export_holdings = params.get("export_holdings", True)
            export_history = params.get("export_history", False)
            
            # Initial Date Calculation
            holdings_date = None
            history_date = None
            
            if export_holdings:
                holdings_date = calculate_holdings_date(params, output_format="%d/%m/%Y")
            
            if export_history:
                history_date = calculate_history_date(params, output_format="%d/%m/%Y")
            
            await log(f"DEBUG Params Resolved - Holdings: {export_holdings} ({holdings_date}), History: {export_history} ({history_date})")

            await log("Phase 1: Authenticating...")
            login_result = await actions.login_step(
                username=credentials.username,
                password=credentials.password,
                token=None,
                token_timeout_seconds=int(params.get("token_timeout_seconds", 240)),
                login_timeout_seconds=int(params.get("login_timeout_seconds", 50)),
            )

            if not login_result.get("logged"):
                error_msg = login_result.get("message", "Login failed")
                await log(f"Login failed: {error_msg}")
                return self._error_result(run_id, error_msg)

            await log("Phase 2: Navigating to reports...")
            nav_result = await actions.navigate_step()
            if not nav_result.get("step_finished"):
                return self._error_result(run_id, "Navigation failed")

            await log("Phase 3: Selecting report type...")
            select_result = await actions.select_report_step(report_type="positions")
            if not select_result.get("step_finished"):
                return self._error_result(run_id, "Report selection failed")


            if export_holdings and holdings_date:
                await log(f"Phase 4: Downloading holdings report (Date: {holdings_date})...")

                holdings_result = await actions.export_holdings(date=holdings_date)
                if not holdings_result.get("step_finished"):
                    return self._error_result(run_id, "Holdings download failed")

            if export_history and history_date:
                await log(f"Phase 5: Downloading history report (Date: {history_date})...")

                history_result = await actions.export_history(date=history_date)
                if not history_result.get("step_finished"):
                    return self._error_result(run_id, "History download failed")

            await log("Phase 6: Organizing downloaded files...")
            file_paths = await self._organize_downloads(
                run_id,
                log,
                expect_positions=export_holdings,
                expect_transactions=export_history,
            )

            if run:
                update_data = {}
                if holdings_date:
                    update_data["report_date"] = holdings_date
                if history_date:
                    update_data["history_date"] = history_date
                if update_data:
                    await run.update({"$set": update_data})

            await log("OK BTG MFO scraping completed successfully")

            return self._success_result(
                run_id,
                {
                    "files": file_paths,
                    "message": "BTG MFO scraping completed successfully",
                },
            )

        except Exception as e:
            # Attempt to save dates if they were calculated before error
            try:
                if run:
                    update_data = {}
                    holdings_date = locals().get("holdings_date")
                    history_date = locals().get("history_date")
                    if holdings_date:
                        update_data["report_date"] = holdings_date
                    if history_date:
                        update_data["history_date"] = history_date
                    if update_data:
                        await run.update({"$set": update_data})
            except Exception:
                pass

            return await self._handle_error(e, driver, run_id, log, credentials)
