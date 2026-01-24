"""
BTG MFO Actions - Automation logic for BTG MFO portal.
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from core.connectors.helpers.selenium_helpers import SeleniumHelpers
from core.connectors.seletores.btg_mfo import SeletorBtgMfo

logger = logging.getLogger(__name__)


class BtgMfoActions:
    """Actions for BTG MFO portal automation."""

    def __init__(
        self,
        driver: WebDriver,
        helpers: SeleniumHelpers,
        selectors: SeletorBtgMfo,
        log_func,
    ):
        self.driver = driver
        self.helpers = helpers
        self.selectors = selectors
        self.log = log_func

    async def login_step(
        self,
        username: str,
        password: str,
        token: Optional[str] = None,
        token_timeout_seconds: int = 300,
        login_timeout_seconds: int = 60,
    ) -> Dict[str, Any]:
        """
        Perform login to BTG MFO portal.

        Token is expected to be typed by the user in the Selenium grid.
        """
        try:
            await self.log("Navigating to BTG MFO login page...")
            self.driver.get(self.selectors.URL_BASE)

            login_field = self.helpers.wait_for_element(*self.selectors.LOGIN_FIELD)
            password_field = self.helpers.wait_for_element(*self.selectors.PASSWORD_FIELD)
            token_field = self.helpers.wait_for_element(*self.selectors.TOKEN_FIELD)

            login_field.clear()
            password_field.clear()
            token_field.clear()

            await self.log(f"Username: {username}")

            login_field.send_keys(str(username))
            password_field.send_keys(str(password))

            if token:
                token_field.send_keys(str(token))
            else:
                await self.log("Waiting for token input in the grid...")
                self.helpers.wait_until(
                    lambda d: (token_field.get_attribute("value") or "").strip() != "",
                    timeout=token_timeout_seconds,
                )
                await self.log("Token filled by user")

            try:
                submit_button = self.helpers.find_element(*self.selectors.SUBMIT_BUTTON)
                if submit_button.is_displayed() and submit_button.is_enabled():
                    submit_button.click()
            except Exception:
                pass

            await self.log("Verifying login...")
            login_verified = self._wait_for_login_result(
                timeout_seconds=login_timeout_seconds
            )

            if not login_verified.get("logged"):
                error_msg = login_verified.get("message", "Unknown login error")
                await self.log(f"Login failed: {error_msg}")
                return {
                    "step": "login",
                    "step_finished": False,
                    "logged": False,
                    "message": error_msg,
                }

            await self.log("Login successful")
            return {
                "step": "login",
                "step_finished": True,
                "logged": True,
                "message": "Login realizado com sucesso.",
            }

        except Exception as e:
            error_msg = f"Unexpected error during login: {str(e)}"
            await self.log(f"{error_msg}")
            logger.exception(error_msg)
            return {
                "step": "login",
                "step_finished": False,
                "logged": False,
                "message": error_msg,
            }

    def _wait_for_login_result(self, timeout_seconds: int = 60) -> Dict[str, Any]:
        """
        Wait for login to complete or show error.
        """
        def condition(driver):
            try:
                error_element = driver.find_element(*self.selectors.LOGIN_ERROR)
                if error_element and error_element.is_displayed():
                    return {
                        "logged": False,
                        "message": error_element.text,
                    }
            except Exception:
                pass

            if driver.find_elements(*self.selectors.CLIENT_SELECTION_BUTTONS):
                return {"logged": True}

            return False

        return WebDriverWait(self.driver, timeout_seconds).until(condition)

    async def navigate_step(self) -> Dict[str, Any]:
        """
        Navigate to WM reports section.
        """
        try:
            await self.log("Navigating to reports page...")

            await self.log("Looking for FAMILY OFFICE WM access type...")
            client_selections = self.driver.find_elements(
                *self.selectors.CLIENT_SELECTION_BUTTONS
            )

            correct_client_selection = None
            for index, element in enumerate(client_selections):
                if "FAMILY OFFICE WM" in element.text:
                    await self.log(
                        f"Found access type: {element.text} (index {index})"
                    )
                    correct_client_selection = element
                    break

            if not correct_client_selection:
                error_msg = "Access type 'FAMILY OFFICE WM' not found"
                await self.log(f"{error_msg}")
                return {
                    "step": "navigation",
                    "step_finished": False,
                    "message": error_msg,
                }

            await self.log("Clicking access button...")
            access_button = correct_client_selection.find_element(
                *self.selectors.ACCESS_BUTTON
            )
            access_button.click()
            await asyncio.sleep(2)

            await self.log("Clicking operations button...")
            operation_button = self.helpers.wait_for_element(
                *self.selectors.OPERATION_BUTTON
            )
            operation_button.click()
            await asyncio.sleep(1)

            await self.log("Looking for WM reports feature...")
            reports_types = self.driver.find_elements(*self.selectors.REPORTS_WM_FEATURE)

            correct_report_element = None
            for element in reports_types:
                text_lower = element.text.lower()
                if "relat" in text_lower and "wm" in text_lower:
                    correct_report_element = element
                    break

            if not correct_report_element:
                error_msg = "WM reports feature not found"
                await self.log(f"{error_msg}")
                return {
                    "step": "navigation",
                    "step_finished": False,
                    "message": error_msg,
                }

            await self.log("Clicking WM reports button...")
            correct_report_element.click()

            await self.log("Navigation successful")
            return {
                "step": "navigation",
                "step_finished": True,
                "message": "Navegacao realizada com sucesso.",
            }

        except Exception as e:
            error_msg = f"Unexpected error during navigation: {str(e)}"
            await self.log(f"{error_msg}")
            logger.exception(error_msg)
            return {
                "step": "navigation",
                "step_finished": False,
                "message": error_msg,
            }

    async def select_report_step(self, report_type: str = "positions") -> Dict[str, Any]:
        """
        Select report category and type.
        """
        try:
            await self.log("Selecting 'Investimento' category...")
            category_select = self.helpers.wait_for_element(
                *self.selectors.CATEGORY_SELECT
            )
            await asyncio.sleep(1)
            category_select.click()

            category_investment = self.helpers.wait_for_element(
                *self.selectors.CATEGORY_INVESTMENT
            )
            await asyncio.sleep(1)
            category_investment.click()

            await self.log("Selecting 'Investimentos (WM Externo) (D-1 e D0)' report...")
            report_select = self.helpers.wait_for_element(*self.selectors.REPORT_SELECT)
            await asyncio.sleep(1)
            report_select.click()

            report_investment = self.helpers.wait_for_element(
                *self.selectors.REPORT_INVESTMENT_WM
            )
            await asyncio.sleep(1)
            report_investment.click()

            await self.log("Clicking filter button...")
            filter_button = self.helpers.wait_for_element(*self.selectors.FILTER_BUTTON)
            filter_button.click()

            await self.log("Waiting for Power BI to load...")
            await asyncio.sleep(5)

            await self.log("Report selected successfully")
            return {
                "step": "select_report",
                "step_finished": True,
                "message": "Relatorio selecionado com sucesso.",
            }

        except Exception as e:
            error_msg = f"Unexpected error during report selection: {str(e)}"
            await self.log(f"{error_msg}")
            logger.exception(error_msg)
            return {
                "step": "select_report",
                "step_finished": False,
                "message": error_msg,
            }

    async def export_holdings(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Download positions D0 report from Power BI.
        """
        try:
            await self.log(f"Starting positions download (Target date: {date or 'D0'})...")

            self.driver.switch_to.default_content()

            await self.log("Waiting for Power BI iframe...")
            powerbi_iframe = WebDriverWait(self.driver, 35).until(
                EC.presence_of_element_located(self.selectors.POWERBI_IFRAME)
            )
            self.driver.switch_to.frame(powerbi_iframe)
            await self.log("Switched to Power BI iframe")

            await self.log("Clicking positions button...")
            positions_container = WebDriverWait(self.driver, 30).until(
                EC.element_to_be_clickable(self.selectors.POSITIONS_BUTTON_CONTAINER)
            )
            self.driver.execute_script(
                "arguments[0].scrollIntoView(true);", positions_container
            )

            tile = positions_container.find_element(*self.selectors.POSITIONS_TILE)
            positions_button = tile.find_element(*self.selectors.POSITIONS_BUTTON)

            await asyncio.sleep(0.5)
            positions_button.click()
            await self.log("Navigated to positions page")
            await asyncio.sleep(5)

            await self.log("Selecting D0 date...")
            date_select = WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located(self.selectors.POSITIONS_DATE_SELECT)
            )
            date_select.click()
            await asyncio.sleep(1)

            dzero_option = WebDriverWait(self.driver, 6).until(
                EC.presence_of_element_located(self.selectors.POSITIONS_DZERO_OPTION)
            )
            dzero_option.click()
            await self.log("D0 date selected")
            await asyncio.sleep(1)

            await self.log("Opening export menu...")
            positions_title = WebDriverWait(self.driver, 6).until(
                EC.presence_of_element_located(self.selectors.POSITIONS_TITLE)
            )
            positions_title.click()

            menu_button = WebDriverWait(self.driver, 12).until(
                EC.presence_of_element_located(self.selectors.POSITIONS_MENU_BUTTON)
            )
            menu_button.click()

            export_button = WebDriverWait(self.driver, 6).until(
                EC.presence_of_element_located(self.selectors.EXPORT_DATA_BUTTON)
            )
            export_button.click()
            await asyncio.sleep(0.5)

            await self.log("Downloading positions file...")
            download_button = WebDriverWait(self.driver, 6).until(
                EC.presence_of_element_located(self.selectors.DOWNLOAD_BUTTON)
            )
            download_button.click()
            await asyncio.sleep(3)

            self.driver.switch_to.default_content()
            filter_button = self.driver.find_element(*self.selectors.FILTER_BUTTON)
            filter_button.click()
            await asyncio.sleep(5)

            await self.log("Positions report downloaded successfully")
            return {
                "step": "positions_dzero_download",
                "step_finished": True,
                "message": "Relatorio de posicoes D0 baixado com sucesso.",
            }

        except Exception as e:
            error_msg = f"Unexpected error during positions download: {str(e)}"
            await self.log(f"{error_msg}")
            logger.exception(error_msg)

            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass

            return {
                "step": "positions_dzero_download",
                "step_finished": False,
                "message": error_msg,
            }

    async def export_history(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Download transactions report from Power BI.
        """
        try:
            await self.log(f"Starting transactions download (Target date: {date})...")

            self.driver.switch_to.default_content()

            await self.log("Waiting for Power BI iframe...")
            powerbi_iframe = WebDriverWait(self.driver, 35).until(
                EC.presence_of_element_located(self.selectors.POWERBI_IFRAME)
            )
            self.driver.switch_to.frame(powerbi_iframe)
            await self.log("Switched to Power BI iframe")

            await self.log("Clicking transactions button...")
            transactions_container = WebDriverWait(self.driver, 30).until(
                EC.element_to_be_clickable(self.selectors.TRANSACTIONS_BUTTON_CONTAINER)
            )
            self.driver.execute_script(
                "arguments[0].scrollIntoView(true);", transactions_container
            )

            tile = transactions_container.find_element(*self.selectors.POSITIONS_TILE)
            transactions_button = tile.find_element(*self.selectors.POSITIONS_BUTTON)

            await asyncio.sleep(0.5)
            transactions_button.click()
            await self.log("Navigated to transactions page")
            await asyncio.sleep(4)

            await self.log("Opening export menu...")
            transactions_title = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located(self.selectors.TRANSACTIONS_TITLE)
            )
            transactions_title.click()

            menu_button = WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located(self.selectors.TRANSACTIONS_MENU_BUTTON)
            )
            menu_button.click()

            export_button = WebDriverWait(self.driver, 6).until(
                EC.presence_of_element_located(self.selectors.EXPORT_DATA_BUTTON)
            )
            export_button.click()
            await asyncio.sleep(0.5)

            await self.log("Downloading transactions file...")
            download_button = WebDriverWait(self.driver, 6).until(
                EC.presence_of_element_located(self.selectors.DOWNLOAD_BUTTON)
            )
            download_button.click()
            await asyncio.sleep(3)

            self.driver.switch_to.default_content()
            filter_button = self.driver.find_element(*self.selectors.FILTER_BUTTON)
            filter_button.click()

            await self.log("Transactions report downloaded successfully")
            return {
                "step": "transactions_download",
                "step_finished": True,
                "message": "Relatorio de movimentacoes baixado com sucesso.",
            }

        except Exception as e:
            error_msg = f"Unexpected error during transactions download: {str(e)}"
            await self.log(f"{error_msg}")
            logger.exception(error_msg)

            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass

            return {
                "step": "transactions_download",
                "step_finished": False,
                "message": error_msg,
            }
