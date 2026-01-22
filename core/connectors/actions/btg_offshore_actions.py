"""
Actions module for BTG Offshore connector.
Encapsulates portal interactions into reusable methods.
"""

from typing import Callable, Optional
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
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

    def _wait_enabled(self, locator):
        el = self.helpers.find_element(*locator)
        self.helpers.wait_until(lambda d: el.is_displayed() and el.is_enabled())
        return el

    # ========== NAVIGATION ==========

    async def navigate_to_login(self, url: str) -> None:
        await self.log(f"NAVIGATE: {url}")
        self.driver.get(url)

    async def click_portal_global(self) -> None:
        before_handles = set(self.driver.window_handles)
        elements = self.driver.find_elements(*self.sel.PORTAL_GLOBAL)
        for el in elements:
            if el.is_displayed() and el.is_enabled():
                try:
                    el.click()
                except Exception:
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", el)
                    self.driver.execute_script("arguments[0].click();", el)
                self._switch_to_new_window(before_handles)
                await self.log("OK Portal Global clicked")
                return
        await self.log("INFO Portal Global not visible, skipping")

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

    async def wait_for_otp(self) -> None:
        self.helpers.wait_for_element(*self.sel.OTP_CODE)
        await self.log("INFO Waiting for OTP entry")

        continue_btn = self._wait_enabled(self.sel.OTP_CONTINUE)
        continue_btn.click()
        await self.log("OK OTP continued")

    # ========== ACCESS ==========

    async def select_country_us(self) -> None:
        if self._is_visible(self.sel.COUNTRY_US):
            self.helpers.click_element(*self.sel.COUNTRY_US)
            await self.log("OK Country selected: United States")

    async def select_all_accounts(self) -> None:
        checkboxes = self.driver.find_elements(*self.sel.ACCOUNT_CHECKBOXES)
        for chk in checkboxes:
            if chk.is_displayed() and chk.is_enabled() and not chk.is_selected():
                chk.click()
        await self.log("OK Accounts selected")

    async def submit_access(self) -> None:
        access_btn = self._wait_enabled(self.sel.ACCESS_BTN)
        access_btn.click()
        await self.log("OK Access submitted")

    async def dismiss_biometric_modal(self) -> None:
        if self._click_if_visible(self.sel.DONT_SHOW_AGAIN):
            await self.log("OK Dismissed biometric modal")

    # ========== FILTER / EXPORT ==========

    async def open_start_date_input(self) -> None:
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
