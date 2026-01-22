"""
Actions module for Jefferies connector.
Encapsulates portal interactions into reusable methods.
"""

from typing import Callable
from selenium.webdriver.remote.webdriver import WebDriver

from core.connectors.helpers.selenium_helpers import SeleniumHelpers
from core.connectors.seletores.jefferies import SeletorJefferies


class JefferiesActions:
    """Encapsulates Jefferies portal actions."""

    def __init__(
        self,
        driver: WebDriver,
        helpers: SeleniumHelpers,
        selectors: SeletorJefferies,
        log_func: Callable,
    ):
        self.driver = driver
        self.helpers = helpers
        self.sel = selectors
        self.log = log_func

    def _is_visible(self, locator) -> bool:
        elements = self.driver.find_elements(*locator)
        return any(el.is_displayed() for el in elements)

    def _click_if_visible(self, locator) -> bool:
        elements = self.driver.find_elements(*locator)
        for el in elements:
            if el.is_displayed() and el.is_enabled():
                el.click()
                return True
        return False

    def _wait_enabled(self, locator):
        el = self.helpers.find_element(*locator)
        self.helpers.wait_until(lambda d: el.is_displayed() and el.is_enabled())
        return el

    # ========== NAVIGATION ==========

    async def navigate_to_login(self, url: str) -> None:
        await self.log(f"NAVIGATE: {url}")
        self.driver.get(url)

    async def accept_cookies_if_needed(self) -> None:
        if self._click_if_visible(self.sel.COOKIES_ACCEPT):
            await self.log("OK Cookies accepted")

    async def ensure_login_dialog(self) -> None:
        if self._is_visible(self.sel.USER_ID):
            return

        await self.log("INFO Login dialog not visible, opening it")
        if not self._click_if_visible(self.sel.LOGIN_OPEN_BTN):
            self.helpers.click_element(*self.sel.LOGIN_OPEN_BTN_TEXT)

        self.helpers.wait_for_visible(*self.sel.USER_ID)

    # ========== LOGIN ==========

    async def fill_credentials(self, username: str, password: str) -> None:
        self.helpers.clear_and_send_keys(*self.sel.USER_ID, username)
        self.helpers.clear_and_send_keys(*self.sel.PASSWORD, password)
        await self.log("OK Credentials filled")

        login_btn = self._wait_enabled(self.sel.LOGIN_SUBMIT)
        login_btn.click()
        await self.log("OK Login submitted")

    # ========== OTP ==========

    async def request_otp(self) -> None:
        self.helpers.click_element(*self.sel.CONTACT_METHOD)
        self.helpers.click_element(*self.sel.CONTACT_METHOD_OPTION)
        await self.log("OK Contact method selected")

        self.helpers.click_element(*self.sel.SEND_CODE)
        await self.log("OK OTP requested")

        self.helpers.wait_for_element(*self.sel.OTP_INPUT)
        await self.log("INFO Waiting for OTP entry")

        verify_btn = self._wait_enabled(self.sel.VERIFY_OTP)
        verify_btn.click()
        await self.log("OK OTP verified")

    # ========== EXPORTS ==========

    async def export_holdings(self) -> None:
        self.helpers.click_element(*self.sel.NAV_ACCOUNTS)
        self.helpers.click_element(*self.sel.NAV_HOLDINGS)
        await self.log("OK Holdings opened")

        self.helpers.click_element(*self.sel.SHOWING_SELECT)
        self.helpers.click_element(*self.sel.PRIOR_CLOSE_OPTION)
        await self.log("OK Prior Close selected")

        self.helpers.click_element(*self.sel.DOWNLOAD_BTN)
        self.helpers.click_element(*self.sel.EXPORT_EXCEL)
        await self.log("OK Holdings exported")

    async def export_history(self) -> None:
        self.helpers.click_element(*self.sel.NAV_HISTORY)
        await self.log("OK History opened")

        self.helpers.click_element(*self.sel.TIME_PERIOD)
        self.helpers.click_element(*self.sel.PREV_BUSINESS_DAY)
        self.helpers.click_element(*self.sel.APPLY_FILTERS)
        await self.log("OK History filter applied")

        self.helpers.click_element(*self.sel.DOWNLOAD_BTN)
        self.helpers.click_element(*self.sel.EXPORT_EXCEL)
        await self.log("OK History exported")

    # ========== LOGOUT ==========

    async def logout(self) -> None:
        if self._click_if_visible(self.sel.USER_MENU):
            self.helpers.click_element(*self.sel.LOGOUT_BTN)
            await self.log("OK Logged out")
