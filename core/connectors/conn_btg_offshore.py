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

        await log_func("PAUSE Sleeping for 120s for visual inspection (error)...")
        await asyncio.sleep(120)

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

            # 1. Navegacao e login
            await actions.navigate_to_login(SeletorBtgOffshore.URL_BASE)
            await actions.click_portal_global()
            await actions.wait_for_login_form()
            await actions.fill_credentials(credentials.email, credentials.password)
            await actions.wait_for_otp()

            # 2. Acesso (United States)
            await actions.select_country_us()
            await actions.select_all_accounts()
            await actions.submit_access()
            await actions.dismiss_biometric_modal()

            # 3. Exportacao US
            date_d1_us = self._get_business_day(region="US", state="NY", days=1, fmt="%m/%d/%Y")
            await actions.open_start_date_input()
            await actions.select_calendar_date(date_d1_us)
            await actions.open_check_all_anchor()
            await actions.open_export_options()
            await actions.select_export_all()
            await actions.open_portfolio()
            await actions.click_portfolio_check_all()
            date_d2_us = self._get_business_day(region="US", state="NY", days=2, fmt="%m/%d/%Y")
            await actions.open_filters()
            await actions.open_time_period()
            await actions.select_custom_period()
            await actions.set_custom_period_dates(date_d2_us)
            await actions.click_filter()
            await actions.click_export()
            await actions.click_download()

            # 4. Troca de custodia para Cayman
            await actions.change_custody_to_cayman()

            # 5. Exportacao Cayman
            date_d1_ky = self._get_business_day(region="KY", days=1, fmt="%m/%d/%Y")
            await actions.open_start_date_input()
            await actions.select_calendar_date(date_d1_ky)
            await actions.open_check_all_anchor()
            await actions.open_export_options()
            await actions.select_export_all()
            await actions.open_portfolio()
            await actions.click_portfolio_check_all()
            date_d2_ky = self._get_business_day(region="KY", days=2, fmt="%m/%d/%Y")
            await actions.open_filters()
            await actions.open_time_period()
            await actions.select_custom_period()
            await actions.set_custom_period_dates(date_d2_ky)
            await actions.click_filter()
            await actions.click_export()
            await actions.click_download()

            await log("OK Login and exports completed. Sleeping for 120s for visual check.")
            await asyncio.sleep(120)

            await actions.logout()
            return self._success_result(run_id, credentials.email)

        except Exception as e:
            try:
                await actions.logout()
            except Exception:
                pass
            return await self._handle_error(e, driver, run_id, log, credentials)
