"""
Actions module for Jefferies connector.
Encapsulates portal interactions into reusable methods.
"""

from typing import Callable
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
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

    def _click_with_fallback(self, locator) -> bool:
        try:
            self.helpers.click_element(*locator)
            return True
        except Exception:
            pass

        try:
            elements = self.driver.find_elements(*locator)
            for el in elements:
                if el.is_displayed():
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", el)
                    self.driver.execute_script("arguments[0].click();", el)
                    return True
        except Exception:
            pass
        return False

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

    def _click_switch_checked(self, timeout: int = 10) -> bool:
        """
        Ensure history toggle switch is checked.
        Performs real user-like clicks on the toggle component until aria-checked becomes true.
        """
        labeled_switch_locator = (
            By.XPATH,
            "//mat-slide-toggle[.//*[contains(normalize-space(.), 'Include money market and bank deposit sweep transactions')]]//input[@role='switch']",
        )
        labeled_switch_bar_locator = (
            By.XPATH,
            "//mat-slide-toggle[.//*[contains(normalize-space(.), 'Include money market and bank deposit sweep transactions')]]//*[contains(@class, 'mat-slide-toggle-bar') or contains(@class, 'mat-mdc-slide-toggle-bar')]",
        )
        labeled_switch_host_locator = (
            By.XPATH,
            "//mat-slide-toggle[.//*[contains(normalize-space(.), 'Include money market and bank deposit sweep transactions')]]",
        )
        generic_switch_locator = (By.CSS_SELECTOR, "input[role='switch'].mat-slide-toggle-input")

        def _find_target():
            labeled = self.driver.find_elements(*labeled_switch_locator)
            if labeled:
                return labeled[0]
            generic = self.driver.find_elements(*generic_switch_locator)
            return generic[0] if generic else None

        try:
            self.helpers.wait_until(lambda d: _find_target() is not None, timeout=timeout)
        except Exception:
            return False

        for _ in range(5):
            target = _find_target()
            if target is None:
                return False

            current_state = (target.get_attribute("aria-checked") or "").lower()
            if current_state == "true":
                return True

            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
            except Exception:
                pass

            clicked = False
            if not clicked:
                clicked = self._click_if_visible(labeled_switch_bar_locator)

            if not clicked:
                clicked = self._click_if_visible(labeled_switch_host_locator)

            if not clicked:
                try:
                    clickable = self.driver.execute_script(
                        """
                        const input = arguments[0];
                        const host = input.closest('mat-slide-toggle');
                        if (!host) return null;
                        return (
                            host.querySelector('.mat-slide-toggle-bar') ||
                            host.querySelector('.mat-slide-toggle-thumb-container') ||
                            host.querySelector('label.mat-slide-toggle-label') ||
                            host
                        );
                        """,
                        target,
                    )
                    if clickable:
                        self.driver.execute_script("arguments[0].click();", clickable)
                        clicked = True
                except Exception:
                    pass

            if not clicked:
                try:
                    target.click()
                    clicked = True
                except Exception:
                    pass

            if not clicked:
                try:
                    target.send_keys(Keys.SPACE)
                    clicked = True
                except Exception:
                    pass

            try:
                self.helpers.sleep(0.3)
            except Exception:
                pass

            # Re-check after each interaction
            target = _find_target()
            if target is not None and (target.get_attribute("aria-checked") or "").lower() == "true":
                return True

        return (target.get_attribute("aria-checked") or "").lower() == "true"

    # ========== NAVIGATION ==========

    async def navigate_to_login(self, url: str) -> None:
        await self.log(f"NAVIGATE: {url}")
        self.driver.get(url)
        try:
            self.helpers.wait_ready_state()
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
        self._click_with_fallback(self.sel.CONTACT_METHOD)
        self._click_with_fallback(self.sel.CONTACT_METHOD_OPTION)
        await self.log("OK Contact method selected")

        self._click_with_fallback(self.sel.SEND_CODE)
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
        self._click_with_fallback(self.sel.NAV_ACCOUNTS)
        self._click_with_fallback(self.sel.NAV_HOLDINGS)
        await self.log(f"OK Holdings opened (Target date: {date})")

        self._click_with_fallback(self.sel.SHOWING_SELECT)
        self._click_with_fallback(self.sel.PRIOR_CLOSE_OPTION)
        await self.log("OK Prior Close selected")

        if self._wait_for_data(self.sel.HOLDINGS_ROWS):
            await self.log("OK Holdings data loaded")
        else:
            await self.log("WARN Holdings rows not detected, continuing to export")

        self._wait_for_export_ready()

        self._click_with_fallback(self.sel.DOWNLOAD_BTN)
        self._click_with_fallback(self.sel.EXPORT_EXCEL)
        await self.log("OK Holdings exported")

    async def export_history(self, date: str = None, start_date: str = None, end_date: str = None) -> None:
        self._click_with_fallback(self.sel.NAV_HISTORY)
        await self.log(f"OK History opened (Target date: {date})")

        self._click_with_fallback(self.sel.TIME_PERIOD)
        self._click_with_fallback(self.sel.PREV_BUSINESS_DAY)
        self._click_with_fallback(self.sel.APPLY_FILTERS)
        await self.log("OK History filter applied")

        if self._click_switch_checked():
            await self.log("OK History switch set to aria-checked=true")
        else:
            await self.log("WARN Could not set history switch to aria-checked=true")

        if self._wait_for_data(self.sel.HISTORY_ROWS):
            await self.log("OK History data loaded")
        else:
            await self.log("WARN History rows not detected, continuing to export")

        self._wait_for_export_ready()

        self._click_with_fallback(self.sel.DOWNLOAD_BTN)
        self._click_with_fallback(self.sel.EXPORT_EXCEL)
        await self.log("OK History exported")

    # ========== LOGOUT ==========

    async def logout(self) -> None:
        if self._click_if_visible(self.sel.USER_MENU):
            self._click_with_fallback(self.sel.LOGOUT_BTN)
            await self.log("OK Logged out")
