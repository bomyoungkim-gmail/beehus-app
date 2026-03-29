"""
US-specific actions for BTG connector.
"""

from selenium.common.exceptions import TimeoutException

from core.connectors.actions.btg_global_actions_base import BtgGlobalActionsBase


class BtgUsActions(BtgGlobalActionsBase):
    """BTG actions constrained to United States flow."""

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
