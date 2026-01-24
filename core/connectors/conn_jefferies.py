"""
Jefferies connector - refactored structure.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional

from selenium.webdriver.remote.webdriver import WebDriver

from core.connectors.base import BaseConnector
from core.schemas.messages import ScrapeResult
from core.connectors.helpers.selenium_helpers import SeleniumHelpers
from core.connectors.seletores.jefferies import SeletorJefferies
from core.connectors.actions.jefferies_actions import JefferiesActions
from core.connectors.utils.date_calculator import calculate_holdings_date, calculate_history_date
from core.utils.date_utils import get_now

logger = logging.getLogger(__name__)


@dataclass
class JefferiesCredentials:
    """Credentials for Jefferies access."""
    username: str
    password: str


class JefferiesConnector(BaseConnector):
    """Conector para automacao do portal Jefferies."""

    @property
    def name(self) -> str:
        return "jefferies_login"

    # ========== SETUP E HELPERS ==========

    def _make_run_logger(self, logger, run):
        async def log(msg: str):
            logger.info(f"[Jefferies] {msg}")
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

    def _validate_credentials(self, params: Dict[str, Any]) -> Optional[JefferiesCredentials]:
        username = params.get("username") or params.get("user")
        password = params.get("password") or params.get("pass")

        if not all([username, password]):
            return None

        return JefferiesCredentials(username=username, password=password)

    def _create_actions(self, driver: WebDriver, log_func) -> JefferiesActions:
        helpers = SeleniumHelpers(driver, timeout=50)
        selectors = SeletorJefferies()
        return JefferiesActions(driver, helpers, selectors, log_func)

    def _success_result(self, run_id: Optional[str], username: str) -> ScrapeResult:
        return ScrapeResult(
            run_id=run_id,
            success=True,
            data={"message": "Logged in successfully", "user": username},
        )

    def _error_result(self, run_id: Optional[str], error: str) -> ScrapeResult:
        return ScrapeResult(run_id=run_id, success=False, error=error)

    def _get_business_day(
        self,
        region: str = "BR",
        state: str = "SP",
        days: int = 1,
        fmt: str = "%d/%m/%Y",
    ) -> str:
        """
        Obtem o dia util anterior.

        Returns:
            Data formatada pelo formato informado.
        """
        previous_day = get_previous_business_day(
            ref_date=get_today(),
            region=region,
            state=state,
            days=days,
        )
        return previous_day.strftime(fmt)

    def _parse_report_date(self, date_str: str) -> Optional[str]:
        """
        Normaliza datas para DD/MM/YYYY.

        Aceita DD/MM/YYYY ou YYYY-MM-DD.
        """
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str, fmt).strftime("%d/%m/%Y")
            except ValueError:
                continue
        return None

    async def _handle_error(
        self,
        e: Exception,
        driver: WebDriver,
        run_id: Optional[str],
        log_func,
        credentials: Optional[JefferiesCredentials] = None,
    ) -> ScrapeResult:
        error_msg = str(e)
        if credentials:
            await log_func(
                f"ERROR Login failed: {error_msg} (user={credentials.username})"
            )
        else:
            await log_func(f"ERROR Login failed: {error_msg}")

        try:
            timestamp = get_now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"/app/artifacts/error_jefferies_{timestamp}.png"
            driver.save_screenshot(screenshot_path)
            await log_func(f"SCREEN Screenshot saved to: {screenshot_path}")
        except Exception as ss_e:
            await log_func(f"WARN Failed to save screenshot: {ss_e}")

        return self._error_result(run_id, error_msg)

    # ========== METODO PRINCIPAL ==========

    async def scrape(self, driver: WebDriver, params: Dict[str, Any]) -> ScrapeResult:
        # Setup
        run, log = await self._setup_run(params)
        run_id = params.get("run_id")

        logger.info(f"Starting Jefferies Login with params: {params}")

        # Validacao de credenciais
        credentials = self._validate_credentials(params)
        if not credentials:
            error_msg = "Missing credentials - check username and password"
            logger.error(error_msg)
            await log(f"ERROR {error_msg}")
            await log(f"INFO Available params: {list(params.keys())}")
            return self._error_result(run_id, error_msg)

        # Criar actions
        actions = self._create_actions(driver, log)

        try:
            # Resolve parameters
            export_holdings = params.get("export_holdings", True)
            export_history = params.get("export_history", False)
            
            # Initial Date Calculation
            holdings_date = None
            history_date = None
            
            if export_holdings:
                from core.connectors.utils.date_calculator import calculate_holdings_date
                holdings_date = calculate_holdings_date(params, output_format="%m/%d/%Y")
            
            if export_history:
                from core.connectors.utils.date_calculator import calculate_history_date
                history_date = calculate_history_date(params, output_format="%m/%d/%Y")
            
            await log(f"DEBUG Params Resolved - Holdings: {export_holdings} ({holdings_date}), History: {export_history} ({history_date})")

            # 1. Navegacao e Login
            await actions.navigate_to_login(SeletorJefferies.URL_BASE)
            await actions.accept_cookies_if_needed()
            await actions.ensure_login_dialog()
            await actions.fill_credentials(credentials.username, credentials.password)
            await actions.request_otp()
            await actions.wait_for_otp(timeout_seconds=240)

            # 2. Exportacoes
            if export_holdings and holdings_date:
                await actions.export_holdings(holdings_date)
            
            if export_history and history_date:
                await actions.export_history(history_date)

            # Save report date to run
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

            await log("Sleeping for 10s for visual check.")
            await asyncio.sleep(10)

            # 3. Logout
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
