"""
BTG Offshore connector - refactored structure.
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
from core.connectors.seletores.btg_offshore import SeletorBtgOffshore
from core.connectors.actions.btg_offshore_actions import BtgOffshoreActions
from core.utils.date_utils import get_previous_business_day, get_now, get_today

logger = logging.getLogger(__name__)


@dataclass
class BtgOffshoreCredentials:
    """Credentials for BTG Offshore access."""
    email: str
    password: str


class BtgOffshoreConnector(BaseConnector):
    """Conector para automacao do portal BTG Offshore."""

    @property
    def name(self) -> str:
        return "btg_offshore_login"

    # ========== SETUP E HELPERS ==========

    def _make_run_logger(self, logger, run):
        async def log(msg: str):
            logger.info(f"[BTG Offshore] {msg}")
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

    def _validate_credentials(self, params: Dict[str, Any]) -> Optional[BtgOffshoreCredentials]:
        email = params.get("email") or params.get("username") or params.get("user")
        password = params.get("password") or params.get("pass")

        if not all([email, password]):
            return None

        return BtgOffshoreCredentials(email=email, password=password)

    def _create_actions(self, driver: WebDriver, log_func) -> BtgOffshoreActions:
        helpers = SeleniumHelpers(driver, timeout=50)
        selectors = SeletorBtgOffshore()
        return BtgOffshoreActions(driver, helpers, selectors, log_func)

    def _success_result(self, run_id: Optional[str], email: str) -> ScrapeResult:
        return ScrapeResult(
            run_id=run_id,
            success=True,
            data={"message": "Logged in successfully", "user": email},
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
        credentials: Optional[BtgOffshoreCredentials] = None,
    ) -> ScrapeResult:
        error_msg = str(e)
        if credentials:
            await log_func(
                f"ERROR Login failed: {error_msg} (user={credentials.email})"
            )
        else:
            await log_func(f"ERROR Login failed: {error_msg}")

        try:
            timestamp = get_now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"/app/artifacts/error_btg_offshore_{timestamp}.png"
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

        logger.info(f"Starting BTG Offshore Login with params: {params}")

        # Validacao de credenciais
        credentials = self._validate_credentials(params)
        if not credentials:
            error_msg = "Missing credentials - check email and password"
            logger.error(error_msg)
            await log(f"ERROR {error_msg}")
            await log(f"INFO Available params: {list(params.keys())}")
            return self._error_result(run_id, error_msg)

        # Criar actions
        actions = self._create_actions(driver, log)

        try:
            # ========== FLUXO PRINCIPAL ==========
             
            # Resolve parameters
            export_holdings = params.get('export_holdings', True)
            export_history = params.get('export_history', False)
            export_holdings_cayman = params.get('export_holdings_cayman', export_holdings)
            export_history_cayman = (
                params.get('export_history_cayman')
                or params.get('export_extrato_cayman')
                or params.get('extrato_cayman')
                or export_history
            )

            # Initial Date Calculation
            holdings_date_us = None
            history_date_us = None
            holdings_date_ky = None
            history_date_ky = None

            if export_holdings:
                 from core.connectors.utils.date_calculator import calculate_holdings_date
                 holdings_date_us = calculate_holdings_date(params, output_format="%m/%d/%Y")  # US format

            if export_history:
                 from core.connectors.utils.date_calculator import calculate_history_date
                 history_date_us = calculate_history_date(params, output_format="%m/%d/%Y")  # US format
                 
            if export_holdings_cayman:
                 from core.connectors.utils.date_calculator import calculate_holdings_date
                 # Reuse utility but might need specific config if cayman differs? assuming params valid
                 holdings_date_ky = calculate_holdings_date(params, output_format="%m/%d/%Y")

            if export_history_cayman:
                from core.connectors.utils.date_calculator import calculate_history_date
                history_date_ky = calculate_history_date(params, output_format="%m/%d/%Y")

            await log(f"DEBUG Params Resolved - Holdings US: {export_holdings} ({holdings_date_us}), History US: {export_history} ({history_date_us})")

            # 1. Navegacao e login
            await actions.navigate_to_login(SeletorBtgOffshore.URL_BASE)
            await actions.click_portal_global()
            await actions.wait_for_login_form()
            await actions.fill_credentials(credentials.email, credentials.password)
            await actions.request_otp()
            await actions.wait_for_otp(timeout_seconds=240)

            # 2. Acesso (United States)
            await actions.wait_for_access_screen()
            await actions.select_country_us()
            await actions.select_all_accounts()
            await actions.submit_access()
            await actions.dismiss_biometric_modal()

            # 3. Export Holdings (if enabled)
            if export_holdings and holdings_date_us:
                await log(f"INFO Holdings date (US): {holdings_date_us}")
                await actions.export_holdings(holdings_date_us)

            # 4. Export History (if enabled)
            if export_history and history_date_us:
                await log(f"INFO History date (US): {history_date_us}")
                await actions.export_history(history_date_us)

            # 4. Troca de custodia para Cayman
            await actions.change_custody_to_cayman()

            # 5. Exportacao Cayman (same pattern as US)
            if export_holdings_cayman and holdings_date_ky:
                await log(f"INFO Holdings date (Cayman): {holdings_date_ky}")
                await actions.export_holdings(holdings_date_ky)

            if export_history_cayman and history_date_ky:
                await log(f"INFO History date (Cayman): {history_date_ky}")
                await actions.export_history(history_date_ky)

            # Save report dates to run
            if run:
                update_data = {}
                # Capture US dates (holdings/history) if available
                holdings_date = locals().get("holdings_date_us")
                history_date = locals().get("history_date_us")
                
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
            # Attempt to save dates if they were calculated before error
            try:
                if run:
                    update_data = {}
                    holdings_date = locals().get("holdings_date_us")
                    history_date = locals().get("history_date_us")
                    if holdings_date:
                        update_data["report_date"] = holdings_date
                    if history_date:
                        update_data["history_date"] = history_date
                    if update_data:
                        await run.update({"$set": update_data})
            except Exception:
                pass  # Ignore db errors during error handling

            try:
                await actions.logout()
            except Exception:
                pass
            return await self._handle_error(e, driver, run_id, log, credentials)
