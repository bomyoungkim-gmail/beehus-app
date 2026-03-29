"""
BTG Cayman connector - refactored structure.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from selenium.webdriver.remote.webdriver import WebDriver

from core.connectors.actions.btg_cayman_actions import BtgCaymanActions
from core.connectors.base import BaseConnector
from core.connectors.helpers.selenium_helpers import SeleniumHelpers
from core.connectors.seletores.btg_cayman import SeletorBtgCayman
from core.schemas.messages import ScrapeResult
from core.utils.date_utils import get_now

logger = logging.getLogger(__name__)


@dataclass
class BtgCaymanCredentials:
    """Credentials for BTG Cayman access."""

    email: str
    password: str


class BtgCaymanConnector(BaseConnector):
    """Conector para automacao do portal BTG Cayman."""

    @property
    def name(self) -> str:
        return "btg_cayman_login"

    def _make_run_logger(self, logger, run):
        async def log(msg: str):
            logger.info(f"[BTG Cayman] {msg}")
            if run:
                timestamped_msg = f"[{get_now().time()}] {msg}"
                await run.update({"$push": {"logs": timestamped_msg}})

        return log

    async def _setup_run(self, params: Dict[str, Any]):
        from core.models.mongo_models import Run

        run_id = params.get("run_id")
        run = await Run.get(run_id) if run_id else None
        log = self._make_run_logger(logger, run)
        return run, log

    def _validate_credentials(self, params: Dict[str, Any]) -> Optional[BtgCaymanCredentials]:
        email = params.get("email") or params.get("username") or params.get("user")
        password = params.get("password") or params.get("pass")

        if not all([email, password]):
            return None

        return BtgCaymanCredentials(email=email, password=password)

    def _create_actions(self, driver: WebDriver, log_func) -> BtgCaymanActions:
        helpers = SeleniumHelpers(driver, timeout=50)
        selectors = SeletorBtgCayman()
        return BtgCaymanActions(driver, helpers, selectors, log_func)

    def _success_result(self, run_id: Optional[str], email: str) -> ScrapeResult:
        return ScrapeResult(
            run_id=run_id,
            success=True,
            data={"message": "Logged in successfully", "user": email},
        )

    def _error_result(self, run_id: Optional[str], error: str) -> ScrapeResult:
        return ScrapeResult(run_id=run_id, success=False, error=error)

    async def _handle_error(
        self,
        e: Exception,
        driver: WebDriver,
        run_id: Optional[str],
        log_func,
        credentials: Optional[BtgCaymanCredentials] = None,
    ) -> ScrapeResult:
        error_msg = str(e)
        if credentials:
            await log_func(f"ERROR BTG Cayman flow failed: {error_msg} (user={credentials.email})")
        else:
            await log_func(f"ERROR BTG Cayman flow failed: {error_msg}")

        try:
            timestamp = get_now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"/app/artifacts/error_btg_cayman_{timestamp}.png"
            driver.save_screenshot(screenshot_path)
            await log_func(f"SCREEN Screenshot saved to: {screenshot_path}")
        except Exception as ss_e:
            await log_func(f"WARN Failed to save screenshot: {ss_e}")

        return self._error_result(run_id, error_msg)

    async def scrape(self, driver: WebDriver, params: Dict[str, Any]) -> ScrapeResult:
        run, log = await self._setup_run(params)
        run_id = params.get("run_id")

        logger.info(f"Starting BTG Cayman Login with params: {params}")

        credentials = self._validate_credentials(params)
        if not credentials:
            error_msg = "Missing credentials - check email and password"
            logger.error(error_msg)
            await log(f"ERROR {error_msg}")
            await log(f"INFO Available params: {list(params.keys())}")
            return self._error_result(run_id, error_msg)

        actions = self._create_actions(driver, log)

        try:
            export_holdings = params.get("export_holdings", True)
            export_history = params.get("export_history", False)

            holdings_date = None
            history_date = None

            if export_holdings:
                from core.connectors.utils.date_calculator import calculate_holdings_date

                holdings_date = calculate_holdings_date(params, output_format="%m/%d/%Y")

            if export_history:
                from core.connectors.utils.date_calculator import calculate_history_date

                history_date = calculate_history_date(params, output_format="%m/%d/%Y")

            await log(
                "DEBUG Params Resolved - "
                f"Holdings Cayman: {export_holdings} ({holdings_date}), "
                f"History Cayman: {export_history} ({history_date})"
            )

            await actions.navigate_to_login(SeletorBtgCayman.URL_BASE)
            await actions.click_portal_global()
            await actions.wait_for_login_form()
            await actions.fill_credentials(credentials.email, credentials.password)
            await actions.request_otp()
            await actions.wait_for_otp(timeout_seconds=240)

            await actions.wait_for_access_screen()
            await actions.select_country_cayman()
            await actions.select_all_accounts()
            await actions.submit_access()
            await actions.dismiss_modal_overlay("post-access")

            if export_holdings and holdings_date:
                await log(f"INFO Holdings date (Cayman): {holdings_date}")
                await actions.export_holdings(holdings_date)

            if export_history and history_date:
                await log(f"INFO History date (Cayman): {history_date}")
                await actions.export_history(history_date)

            if run:
                update_data = {}
                if holdings_date:
                    update_data["report_date"] = holdings_date
                if history_date:
                    update_data["history_date"] = history_date
                if update_data:
                    await run.update({"$set": update_data})

            await log("Sleeping for 10s for visual check.")
            await asyncio.sleep(10)

            await actions.logout()
            return self._success_result(run_id, credentials.email)

        except Exception as e:
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
