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

    def _wait_enabled(self, locator, timeout: int = None):
        el = self.helpers.find_element(*locator)
        self.helpers.wait_until(lambda d: el.is_displayed() and el.is_enabled(), timeout=timeout)
        return el

    def _wait_for_data(self, rows_locator, timeout: int = 40) -> bool:
        try:
            self.helpers.wait_for_invisibility(*self.sel.LOADING_SPINNER)
        except Exception:
            pass

        def _has_rows(_):
            rows = self.driver.find_elements(*rows_locator)
            return any(row.is_displayed() for row in rows)

        try:
            self.helpers.wait_until(_has_rows)
            return True
        except Exception:
            return False

    def _wait_for_export_ready(self, timeout: int = 40) -> None:
        try:
            self.helpers.wait_for_invisibility(*self.sel.LOADING_SPINNER)
        except Exception:
            pass

        def _download_ready(_):
            btn = self.driver.find_element(*self.sel.DOWNLOAD_BTN)
            return btn.is_displayed() and btn.is_enabled()

        self.helpers.wait_until(_download_ready)

    # ========== NAVIGATION ==========

    async def navigate_to_login(self, url: str) -> None:
        await self.log(f"NAVIGATE: {url}")
        self.driver.get(url)
        try:
            self.helpers.wait_until(lambda d: d.execute_script("return document.readyState") == "complete")
        except Exception:
            pass

    async def accept_cookies_if_needed(self) -> None:
        if self._click_if_visible(self.sel.COOKIES_ACCEPT):
            await self.log("OK Cookies accepted")
            # Wait for banner to disappear to avoid interception
            try:
                self.helpers.wait_for_invisibility((By.ID, "onetrust-consent-sdk"))
            except Exception:
                pass
            
            try:
                self.helpers.wait_for_visible(*self.sel.LOGIN_OPEN_BTN)
            except Exception:
                pass

    async def ensure_login_dialog(self) -> None:
        # Check if already visible (input field)
        if self._is_visible(self.sel.USER_ID) or self._is_visible(self.sel.USER_ID_ALT):
            return

        await self.log("INFO Login dialog not visible, opening it")

        try:
            self.helpers.wait_for_element(*self.sel.LOGIN_OPEN_BTN)
        except Exception:
            pass
        
        # Aggressive overlay cleanupwait
        try:
             self.helpers.wait_for_invisibility((By.CSS_SELECTOR, "div.cdk-overlay-backdrop"))
             self.helpers.wait_for_invisibility((By.CSS_SELECTOR, "div.onetrust-pc-dark-filter"))
        except Exception:
             pass

        # Use JS Click to bypass simple overlay interruptions if element is present
        try:
            login_btn = self.helpers.find_element(*self.sel.LOGIN_OPEN_BTN)
            # Scroll to view
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", login_btn)
            await self.helpers.sleep(1) # tiny pause for scroll
            
            try:
                login_btn.click()
            except Exception:
                await self.log("WARN Standard click failed, trying JS click")
                self.driver.execute_script("arguments[0].click();", login_btn)
                
        except Exception as e:
            await self.log(f"WARN Could not click login opening button: {e}")

        # Ensure the dialog is ready; some flows render a backdrop first.
        try:
            self.helpers.wait_for_invisibility(*self.sel.OVERLAY_BACKDROP)
        except Exception:
            pass
        self._wait_for_login_input()

    def _wait_for_login_input(self) -> None:
        self._find_visible_input(
            [
                self.sel.USER_ID,
                self.sel.USER_ID_ALT,
            ]
        )

    def _find_visible_input(self, locators):
        for locator in locators:
            elements = self.driver.find_elements(*locator)
            for el in elements:
                if el.is_displayed() and el.is_enabled():
                    return el
        raise RuntimeError("No visible input found")

    # ========== LOGIN ==========

    async def fill_credentials(self, username: str, password: str) -> None:
        user_input = self._find_visible_input(
            [
                self.sel.USER_ID,
                self.sel.USER_ID_ALT,
            ]
        )
        user_input.clear()
        user_input.send_keys(username)

        password_input = self._find_visible_input(
            [
                self.sel.PASSWORD,
            ]
        )
        password_input.clear()
        password_input.send_keys(password)
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

    async def wait_for_otp(self, timeout_seconds: int = 240, max_attempts: int = 3) -> None:
        self.helpers.wait_for_element(*self.sel.OTP_INPUT)
        await self.log("INFO Waiting for OTP entry")

        attempts = 0
        while attempts < max_attempts:
            verify_btn = self._wait_enabled(self.sel.VERIFY_OTP, timeout=timeout_seconds)
            verify_btn.click()

            try:
                self.helpers.wait_for_visible(*self.sel.OTP_ERROR)
                attempts += 1
                await self.log("WARN OTP invalid, requesting new code")
                self.helpers.click_element(*self.sel.OTP_RESEND)
                self.helpers.wait_for_invisibility(*self.sel.OTP_ERROR)
                self.helpers.wait_for_element(*self.sel.OTP_INPUT)
                await self.log("INFO Waiting for new OTP entry")
                continue
            except Exception:
                await self.log("OK OTP verified")
                return

        raise RuntimeError("OTP attempts exceeded")

    # ========== EXPORTS ==========

    async def export_holdings(self, date: str = None) -> None:
        self.helpers.click_element(*self.sel.NAV_ACCOUNTS)
        self.helpers.click_element(*self.sel.NAV_HOLDINGS)
        await self.log(f"OK Holdings opened (Target date: {date})")

        self.helpers.click_element(*self.sel.SHOWING_SELECT)
        self.helpers.click_element(*self.sel.PRIOR_CLOSE_OPTION)
        await self.log("OK Prior Close selected")

        if self._wait_for_data(self.sel.HOLDINGS_ROWS):
            await self.log("OK Holdings data loaded")
        else:
            await self.log("WARN Holdings rows not detected, continuing to export")

        self._wait_for_export_ready()

        self.helpers.click_element(*self.sel.DOWNLOAD_BTN)
        self.helpers.click_element(*self.sel.EXPORT_EXCEL)
        await self.log("OK Holdings exported")

    async def export_history(self, date: str = None, start_date: str = None, end_date: str = None) -> None:
        self.helpers.click_element(*self.sel.NAV_HISTORY)
        await self.log(f"OK History opened (Target date: {date})")

        self.helpers.click_element(*self.sel.TIME_PERIOD)
        self.helpers.click_element(*self.sel.PREV_BUSINESS_DAY)
        self.helpers.click_element(*self.sel.APPLY_FILTERS)
        await self.log("OK History filter applied")

        if self._wait_for_data(self.sel.HISTORY_ROWS):
            await self.log("OK History data loaded")
        else:
            await self.log("WARN History rows not detected, continuing to export")

        self._wait_for_export_ready()

        self.helpers.click_element(*self.sel.DOWNLOAD_BTN)
        self.helpers.click_element(*self.sel.EXPORT_EXCEL)
        await self.log("OK History exported")

    # ========== LOGOUT ==========

    async def logout(self) -> None:
        if self._click_if_visible(self.sel.USER_MENU):
            self.helpers.click_element(*self.sel.LOGOUT_BTN)
            await self.log("OK Logged out")
