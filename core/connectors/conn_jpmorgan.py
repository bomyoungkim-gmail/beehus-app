import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional

from selenium.webdriver.remote.webdriver import WebDriver

from core.connectors.base import BaseConnector
from core.schemas.messages import ScrapeResult
from core.connectors.helpers.selenium_helpers import SeleniumHelpers
from core.connectors.seletores.jpmorgan import SeletorJPMorgan
from core.connectors.actions.jpmorgan_actions import JPMorganActions
from core.connectors.utils.date_calculator import calculate_history_date, calculate_holdings_date
from core.utils.date_utils import get_now

logger = logging.getLogger(__name__)


@dataclass
class JPMorganCredentials:
    username: str
    password: str


class JPMorganConnector(BaseConnector):
    @property
    def name(self) -> str:
        return "jpmorgan_login"

    def _make_run_logger(self, run):
        async def log(msg: str):
            logger.info(f"[JPMorgan] {msg}")
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

    def _validate_credentials(self, params: Dict[str, Any]) -> Optional[JPMorganCredentials]:
        username = params.get("username") or params.get("user")
        password = params.get("password")
        if not username or not password:
            return None
        return JPMorganCredentials(username=username, password=password)

    def _create_actions(self, driver: WebDriver, log_func) -> JPMorganActions:
        helpers = SeleniumHelpers(driver, timeout=50)
        selectors = SeletorJPMorgan()
        return JPMorganActions(driver, helpers, selectors, log_func)

    def _parse_date(self, date_str: str) -> Optional[str]:
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str, fmt).strftime("%m/%d/%Y")
            except ValueError:
                continue
        return None

    async def _get_transaction_range(self, params: Dict[str, Any], log_func) -> tuple[str, str]:
        history_date = calculate_history_date(params, output_format="%m/%d/%Y")
        start_date = params.get("transactions_start_date") or history_date
        end_date = params.get("transactions_end_date") or history_date

        parsed_start = self._parse_date(start_date)
        parsed_end = self._parse_date(end_date)
        if not parsed_start or not parsed_end:
            await log_func("WARN Invalid transaction date range, using history date.")
            parsed_start = history_date
            parsed_end = history_date

        await log_func(f"INFO Transaction range: {parsed_start} - {parsed_end}")
        return parsed_start, parsed_end

    def _success_result(self, run_id: Optional[str], username: str) -> ScrapeResult:
        return ScrapeResult(
            run_id=run_id,
            success=True,
            data={"message": "Export completed", "user": username},
        )

    def _error_result(self, run_id: Optional[str], error: str) -> ScrapeResult:
        return ScrapeResult(
            run_id=run_id,
            success=False,
            error=error,
        )

    async def _handle_error(
        self,
        e: Exception,
        driver: WebDriver,
        run_id: Optional[str],
        log_func,
        credentials: Optional[JPMorganCredentials] = None,
    ) -> ScrapeResult:
        error_msg = str(e)
        if credentials:
            await log_func(f"ERROR JPMorgan failure for user {credentials.username}: {error_msg}")
        else:
            await log_func(f"ERROR JPMorgan failure: {error_msg}")

        try:
            timestamp = get_now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"/app/artifacts/error_jpmorgan_{timestamp}.png"
            driver.save_screenshot(screenshot_path)
            await log_func(f"SCREEN Screenshot saved: {screenshot_path}")
        except Exception as ss_e:
            await log_func(f"WARN Screenshot failed: {ss_e}")

        return self._error_result(run_id, error_msg)

    async def scrape(self, driver: WebDriver, params: Dict[str, Any]) -> ScrapeResult:
        run, log = await self._setup_run(params)
        run_id = params.get("run_id")

        logger.info(f"Starting JPMorgan flow with params: {params}")

        credentials = self._validate_credentials(params)
        if not credentials:
            error_msg = "Missing credentials - check username and password"
            logger.error(error_msg)
            await log(f"ERROR {error_msg}")
            await log(f"INFO Available params: {list(params.keys())}")
            return self._error_result(run_id, error_msg)

        # LOGIC REMOVED: Redundant Local Driver Creation
        # The Executor (core/worker/executor.py) now handles creating the correct driver 
        # (Local UC vs Remote Grid) based on the connector type.
        # We simply use the `driver` passed to this method.

        actions = self._create_actions(driver, log)


        try:
            # Resolve parameters
            export_holdings = params.get("export_holdings", True)
            export_history = params.get("export_history", False)

            # Initial Date Calculation
            holdings_date = None
            history_date = None

            if export_holdings:
                 holdings_date = calculate_holdings_date(params, output_format="%m/%d/%Y")
            
            if export_history:
                 history_date = calculate_history_date(params, output_format="%m/%d/%Y")
                 start_date, end_date = await self._get_transaction_range(params, log)

            await log(f"DEBUG Params Resolved - Holdings: {export_holdings} ({holdings_date}), History: {export_history} ({history_date})")

            await actions.navigate_to_login(
                retries=int(params.get("login_redirect_retries", 2))
            )
            await actions.fill_credentials(credentials.username, credentials.password)
            await actions.submit_login()

            await actions.open_mfa_dropdown()
            await actions.select_mfa_option(params.get("mfa_option_id"))
            await actions.request_mfa_code()
            await actions.confirm_mfa_login()

            await actions.wait_for_login_complete(
                timeout_seconds=int(params.get("mfa_timeout_seconds", 240))
            )

            # Export Holdings
            if export_holdings and holdings_date:
                await actions.export_holdings(holdings_date)
                await log(f"OK Holdings exported for date: {holdings_date}")

            # Export History
            if export_history and history_date:
                await actions.export_history(history_date, start_date=start_date, end_date=end_date)
            if run:
                update_data = {}
                holdings_date = locals().get("holdings_date")
                # For JPMorgan history uses start/end range, we typically use the query date or end date
                history_date = locals().get("history_date") 
                
                if holdings_date:
                    update_data["report_date"] = holdings_date
                if history_date:
                    update_data["history_date"] = history_date
                
                if update_data:
                    await run.update({"$set": update_data})
                await log(f"OK History exported for range: {start_date} - {end_date}")



            await log("Sleeping for 10s for verification...")
            await asyncio.sleep(10)

            await actions.logout()
            return self._success_result(run_id, credentials.username)
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

            try:
                await actions.logout()
            except Exception:
                pass
            return await self._handle_error(e, driver, run_id, log, credentials)
