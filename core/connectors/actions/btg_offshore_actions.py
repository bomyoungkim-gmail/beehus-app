"""
Actions module for BTG Offshore connector.
Encapsulates portal interactions into reusable methods.
"""

from typing import Callable, Optional
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
import time
import random

from core.connectors.helpers.selenium_helpers import SeleniumHelpers
from core.connectors.seletores.btg_offshore import SeletorBtgOffshore
from core.utils.date_utils import get_previous_business_day, get_today


class BtgOffshoreActions:
    """Encapsulates BTG Offshore portal actions."""

    def __init__(
        self,
        driver: WebDriver,
        helpers: SeleniumHelpers,
        selectors: SeletorBtgOffshore,
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

    def _find_first_visible(self, locators):
        for loc in locators:
            elements = self.driver.find_elements(*loc)
            for el in elements:
                if el.is_displayed() and el.is_enabled():
                    return el
        return None

    def _wait_enabled(self, locator, timeout: Optional[int] = None):
        el = self.helpers.find_element(*locator)
        self.helpers.wait_until(lambda d: el.is_displayed() and el.is_enabled(), timeout=timeout)
        return el

    def _wait_any_visible(self, locators, timeout_msg: str):
        try:
            return self.helpers.wait_until(
                lambda d: any(
                    el.is_displayed()
                    for loc in locators
                    for el in d.find_elements(*loc)
                )
            )
        except Exception as exc:
            raise TimeoutException(timeout_msg) from exc

    def _overlay_visible(self) -> bool:
        return self._is_visible(self.sel.MODAL_OVERLAY)

    def _wait_overlay_gone(self, timeout_seconds: int = 10) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self._overlay_visible():
                return True
            time.sleep(0.25)
        return not self._overlay_visible()

    async def dismiss_modal_overlay(self, context: str = "", wait_seconds: float = 0) -> None:
        if wait_seconds > 0:
            deadline = time.time() + wait_seconds
            while time.time() < deadline and not self._overlay_visible():
                time.sleep(0.25)
        if not self._overlay_visible():
            return

        suffix = f" ({context})" if context else ""
        await self.log(f"INFO Modal overlay detected{suffix}")

        for _ in range(3):
            if not self._overlay_visible():
                return

            if self._click_if_visible(self.sel.DONT_SHOW_AGAIN):
                await self.log("OK Dismissed modal (Don't show again)")
            elif self._click_if_visible(self.sel.MODAL_CLOSE):
                await self.log("OK Dismissed modal (Close icon/btn)")
            elif self._click_if_visible(self.sel.MODAL_CLOSE_BUTTON):
                await self.log("OK Dismissed modal (Close button)")
            elif self._click_if_visible(self.sel.MODAL_SKIP):
                await self.log("OK Dismissed modal (Skip/Close text)")

            time.sleep(1)

        if self._overlay_visible():
            if self._wait_overlay_gone():
                await self.log("OK Modal overlay gone after close")
                return

        if self._overlay_visible():
            overlays = self.driver.find_elements(*self.sel.MODAL_OVERLAY)
            if overlays:
                try:
                    self.driver.execute_script("arguments[0].click();", overlays[-1])
                    time.sleep(1)
                except Exception:
                    pass

        if self._overlay_visible():
            self._wait_overlay_gone()

        if self._overlay_visible():
            await self.log("WARN Modal overlay still visible after attempts")

    # ========== NAVIGATION ==========

    async def navigate_to_login(self, url: str) -> None:
        await self.log(f"NAVIGATE: {url}")
        self.driver.get(url)

    async def click_portal_global(self) -> None:
        before_handles = set(self.driver.window_handles)
        deadline = time.time() + 12
        while time.time() < deadline:
            el = self._find_first_visible(
                [self.sel.PORTAL_GLOBAL_CARD, self.sel.PORTAL_GLOBAL, self.sel.PORTAL_GLOBAL_ALT]
            )
            if el:
                try:
                    el.click()
                except Exception:
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", el)
                    self.driver.execute_script("arguments[0].click();", el)
                self._switch_to_new_window(before_handles)
                await self.log("OK Portal Global clicked")
                return

            if self._is_visible(self.sel.EMAIL):
                await self.log("INFO Global login form visible, skipping Portal Global")
                return

            time.sleep(0.5)

        await self.log("WARN Portal Global not visible after wait, continuing")

    def _switch_to_new_window(self, before_handles) -> None:
        try:
            self.helpers.wait_until(lambda d: len(d.window_handles) > len(before_handles))
        except Exception:
            return

        for handle in self.driver.window_handles:
            if handle not in before_handles:
                self.driver.switch_to.window(handle)
                return

    async def wait_for_login_form(self) -> None:
        self.helpers.wait_for_visible(*self.sel.EMAIL)
        await self.log("OK Login form visible")

    # ========== LOGIN ==========

    async def fill_credentials(self, email: str, password: str) -> None:
        email_input = self.helpers.wait_for_visible(*self.sel.EMAIL)
        password_input = self.helpers.wait_for_visible(*self.sel.PASSWORD)

        self._type_human(email_input, email)
        self._type_human(password_input, password)
        await self.log("OK Credentials filled")

        sign_in_btn = self._wait_enabled(self.sel.SIGN_IN)
        sign_in_btn.click()
        await self.log("OK Sign in submitted")

    # ========== OTP ==========

    async def request_otp(self) -> None:
        await self.log("INFO OTP already sent, waiting for user input")

    async def wait_for_otp(self, timeout_seconds: int = 240) -> None:
        self.helpers.wait_for_element(*self.sel.OTP_CODE)
        await self.log("INFO Waiting for OTP entry")

        continue_btn = self._wait_enabled(self.sel.OTP_CONTINUE, timeout=timeout_seconds)
        continue_btn.click()
        await self.log("OK OTP continued")

    # ========== ACCESS ==========

    async def wait_for_access_screen(self) -> None:
        try:
            self._wait_any_visible(
                [self.sel.COUNTRY_US, self.sel.ACCOUNT_CHECKBOXES],
                "Access screen not visible after OTP.",
            )
            await self.log("OK Access screen visible")
        except TimeoutException:
            await self.log("WARN Access screen not visible after OTP")

    async def select_country_us(self) -> None:
        try:
            self.helpers.wait_for_visible(*self.sel.COUNTRY_US)
            self.helpers.click_element(*self.sel.COUNTRY_US)
            await self.log("OK Country selected: United States")
        except TimeoutException:
            await self.log("WARN Country tab not visible: United States")

    async def select_all_accounts(self) -> None:
        """Selects all available accounts using JS click for reliability."""
        try:
            # Try specific "Select All" checkbox first
            total_chk = self.driver.find_elements(*self.sel.CHECKBOX_TOTAL)
            if total_chk:
                self.log("INFO Found Total Checkbox, attempting click...")
                # Use JS click as the input might be hidden/overlayed
                self.driver.execute_script("arguments[0].click();", total_chk[0])
                time.sleep(1) # Wait for UI to update
                await self.log("OK Total Checkbox clicked")
                return

            # Fallback to individual checkboxes
            await self.log("INFO Total Checkbox not found, selecting individually")
            checkboxes = self.driver.find_elements(*self.sel.ACCOUNT_CHECKBOXES)
            clicked_count = 0
            for chk in checkboxes:
                if not chk.is_selected():
                    self.driver.execute_script("arguments[0].click();", chk)
                    clicked_count += 1
            
            if clicked_count > 0:
                await self.log(f"OK Selected {clicked_count} individual accounts")
            else:
                await self.log("INFO No unselected accounts found")

        except Exception as e:
            await self.log(f"WARN Error selecting accounts: {e}")

    async def submit_access(self) -> None:
        access_btn = self._wait_enabled(self.sel.ACCESS_BTN)
        access_btn.click()
        await self.log("OK Access submitted")
        await self.dismiss_modal_overlay("post-access", wait_seconds=6)

    # ========== FILTER / EXPORT ==========

    async def open_start_date_input(self) -> None:
        await self.dismiss_modal_overlay("before start date input")
        self.helpers.click_element(*self.sel.DATE_INPUT)
        await self.log("OK Start date input opened")

    async def select_calendar_date(self, date_str: str) -> None:
        day_cell = (By.XPATH, f"//td[@title='{date_str}']")
        self.helpers.click_element(*day_cell)
        await self.log(f"OK Date selected: {date_str}")

    async def open_check_all_anchor(self) -> None:
        if self._click_if_visible(self.sel.CHECK_ALL_ANCHOR):
            await self.log("OK Check all opened")
        else:
            await self.log("INFO Check all already open or not visible")

    async def open_export_options(self) -> None:
        self.helpers.click_element(*self.sel.EXPORT_OPTIONS_BTN)
        await self.log("OK Export options opened")

    async def select_export_all(self) -> None:
        self.helpers.click_element(*self.sel.EXPORT_ALL_OPTION)
        await self.log("OK Export all selected")

    async def open_portfolio(self) -> None:
        if not self._is_visible(self.sel.SIDEBAR_PORTFOLIO):
            self._click_if_visible(self.sel.SIDEBAR_TOGGLE)
        self.helpers.click_element(*self.sel.SIDEBAR_PORTFOLIO)
        await self.log("OK Portfolio opened")

    async def click_portfolio_check_all(self) -> None:
        self.helpers.click_element(*self.sel.PORTFOLIO_CHECK_ALL)
        await self.log("OK Portfolio check all selected")

    async def open_filters(self) -> None:
        self.helpers.click_element(*self.sel.FILTERS_BTN)
        await self.log("OK Filters opened")

    async def open_time_period(self) -> None:
        self.helpers.click_element(*self.sel.TIME_PERIOD)
        await self.log("OK Time Period opened")

    async def select_custom_period(self) -> None:
        self.helpers.click_element(*self.sel.CUSTOM_PERIOD)
        await self.log("OK Custom period selected")

    async def set_custom_period_dates(self, date_str: str) -> None:
        date_inputs = self.driver.find_elements(*self.sel.CUSTOM_DATE_INPUTS)
        if len(date_inputs) >= 2:
            date_inputs[0].click()
            await self.select_calendar_date(date_str)
            date_inputs[1].click()
            await self.select_calendar_date(date_str)
        else:
            self.helpers.click_element(*self.sel.CUSTOM_DATE_INPUTS)
            await self.select_calendar_date(date_str)
        await self.log(f"OK Custom period dates set: {date_str}")

    async def click_filter(self) -> None:
        self.helpers.click_element(*self.sel.FILTER_BTN)
        await self.log("OK Filter applied")

    async def click_export(self) -> None:
        self.helpers.click_element(*self.sel.EXPORT_BTN)
        await self.log("OK Export requested")

    async def click_download(self) -> None:
        self.helpers.click_element(*self.sel.DOWNLOAD_BTN)
        await self.log("OK Download started")

    def _type_human(self, el, value: str) -> None:
        el.click()
        el.send_keys(Keys.CONTROL, "a")
        el.send_keys(Keys.BACKSPACE)
        for ch in value:
            ActionChains(self.driver).send_keys(ch).perform()
            time.sleep(random.uniform(0.03, 0.09))

    async def change_custody_to_cayman(self) -> None:
        if await self.open_profile_menu():
            await self.click_change_custody()
            await self.select_cayman_country()
            await self.log("OK Changed custody to Cayman Islands")

    async def open_profile_menu(self) -> bool:
        if self._click_if_visible(self.sel.PROFILE_MENU):
            await self.log("OK Profile menu opened")
            return True
        await self.log("WARN Profile menu not visible")
        return False

    async def click_change_custody(self) -> None:
        self.helpers.click_element(*self.sel.CHANGE_CUSTODY)
        await self.log("OK Change custody clicked")

    async def select_cayman_country(self) -> None:
        self.helpers.click_element(*self.sel.COUNTRY_CAYMAN)
        await self.log("OK Cayman Islands selected")

    # ========== LOGOUT ==========

    async def logout(self) -> None:
        if await self.open_profile_menu():
            await self.click_sign_out()
            await self.log("OK Signed out")

    async def click_sign_out(self) -> None:
        self.helpers.click_element(*self.sel.SIGN_OUT)
        await self.log("OK Sign out clicked")

    # ========== EXPORT METHODS ==========

    async def export_holdings(self, date: str) -> None:
        """
        Export holdings/portfolio report.
        
        Args:
            date: Report date in MM/DD/YYYY format (US format)
        """
        await self.log(f"Exporting holdings for date: {date}")
        
        # Set date and configure export
        await self.open_start_date_input()
        await self.select_calendar_date(date)
        await self.open_check_all_anchor()
        await self.open_export_options()
        await self.select_export_all()
        await self.open_portfolio()
        await self.click_portfolio_check_all()
        
        await self.log("OK Holdings export completed")

    async def export_history(self, date: str) -> None:
        """
        Export transaction history report.
        
        Args:
            date: Report date in MM/DD/YYYY format (US format)
        """
        await self.log(f"Exporting history for date: {date}")
        
        # Set custom period and export
        await self.open_filters()
        await self.open_time_period()
        await self.select_custom_period()
        await self.set_custom_period_dates(date)
        await self.click_filter()
        await self.click_export()
        await self.click_download()
        
        await self.log("OK History export completed")
