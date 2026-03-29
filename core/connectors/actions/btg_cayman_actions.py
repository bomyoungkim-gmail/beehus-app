"""
Cayman-specific actions for BTG connector.
"""

import time

from selenium.common.exceptions import TimeoutException

from core.connectors.actions.btg_global_actions_base import BtgGlobalActionsBase


class BtgCaymanActions(BtgGlobalActionsBase):
    """BTG actions constrained to Cayman flow."""

    async def wait_for_access_screen(self) -> None:
        try:
            self._wait_any_visible(
                [self.sel.COUNTRY_CAYMAN, self.sel.ACCOUNT_CHECKBOXES],
                "Access screen not visible after OTP.",
            )
            await self.log("OK Access screen visible")
        except TimeoutException:
            await self.log("WARN Access screen not visible after OTP")

    async def select_country_cayman(self) -> None:
        try:
            self.helpers.wait_for_visible(*self.sel.COUNTRY_CAYMAN)
            self.helpers.click_element(*self.sel.COUNTRY_CAYMAN)
            await self.log("OK Country selected: Cayman Islands")
        except TimeoutException:
            await self.log("WARN Country tab not visible: Cayman Islands")

    def _is_custom_period_active(self) -> bool:
        try:
            inputs = self.driver.find_elements(*self.sel.CUSTOM_DATE_INPUTS)
            if any(el.is_displayed() for el in inputs):
                return True
        except Exception:
            pass
        try:
            return bool(
                self.driver.execute_script(
                    """
                    const roots = [];
                    const seen = new Set();
                    const queue = [document];
                    while (queue.length) {
                      const root = queue.shift();
                      if (!root || seen.has(root)) continue;
                      seen.add(root);
                      roots.push(root);
                      const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
                      for (const el of all) if (el && el.shadowRoot) queue.push(el.shadowRoot);
                    }

                    for (const root of roots) {
                      const inputs = root.querySelectorAll
                        ? root.querySelectorAll('input[placeholder*=\"Click and select\"], input[placeholder*=\"Data de\"], input[placeholder*=\"Date\"]')
                        : [];
                      for (const i of inputs) {
                        const style = window.getComputedStyle(i);
                        if (style && style.display !== 'none' && style.visibility !== 'hidden') return true;
                      }
                    }
                    return false;
                    """
                )
            )
        except Exception:
            return False

    def _has_custom_period_option(self) -> bool:
        try:
            return bool(
                self.driver.execute_script(
                    """
                    const roots = [];
                    const seen = new Set();
                    const queue = [document];
                    while (queue.length) {
                      const root = queue.shift();
                      if (!root || seen.has(root)) continue;
                      seen.add(root);
                      roots.push(root);
                      const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
                      for (const el of all) if (el && el.shadowRoot) queue.push(el.shadowRoot);
                    }

                    const tokens = ['custom period', 'custom range', 'período personalizado', 'periodo personalizado'];
                    const selectors = ['div.description', 'button', '[role=\"option\"]', 'li', 'span', 'mat-option', '.orq-droplist__item'];

                    for (const root of roots) {
                      for (const sel of selectors) {
                        const nodes = root.querySelectorAll ? root.querySelectorAll(sel) : [];
                        for (const el of nodes) {
                          const txt = (el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                          if (tokens.some((t) => txt.includes(t))) return true;
                        }
                      }
                    }
                    return false;
                    """
                )
            )
        except Exception:
            return False

    def _expand_time_period_cayman_js(self) -> bool:
        try:
            clicked = self.driver.execute_script(
                """
                const roots = [];
                const seen = new Set();
                const queue = [document];
                while (queue.length) {
                  const root = queue.shift();
                  if (!root || seen.has(root)) continue;
                  seen.add(root);
                  roots.push(root);
                  const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
                  for (const el of all) if (el && el.shadowRoot) queue.push(el.shadowRoot);
                }

                const selectors = ['label', 'button', 'div', 'span'];
                for (const root of roots) {
                  for (const sel of selectors) {
                    const nodes = root.querySelectorAll ? root.querySelectorAll(sel) : [];
                    for (const el of nodes) {
                      const txt = (el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                      if (!txt.includes('time period')) continue;
                      const clickable = el.closest('button, label, [role=\"button\"], div') || el;
                      clickable.scrollIntoView({ block: 'center' });
                      clickable.click();
                      return true;
                    }
                  }
                }
                return false;
                """
            )
            return bool(clicked)
        except Exception:
            return False

    def _click_custom_period_cayman_js(self) -> bool:
        try:
            clicked = self.driver.execute_script(
                """
                const roots = [];
                const seen = new Set();
                const queue = [document];

                while (queue.length) {
                  const root = queue.shift();
                  if (!root || seen.has(root)) continue;
                  seen.add(root);
                  roots.push(root);

                  const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
                  for (const el of all) {
                    if (el && el.shadowRoot) queue.push(el.shadowRoot);
                  }
                }

                const selectors = [
                  'div.description',
                  'button',
                  '[role=\"option\"]',
                  'li',
                  'span',
                  'mat-option',
                  '.orq-droplist__item',
                ];

                const tokens = ['custom period', 'custom range', 'período personalizado', 'periodo personalizado'];

                for (const root of roots) {
                  for (const sel of selectors) {
                    const nodes = root.querySelectorAll ? root.querySelectorAll(sel) : [];
                    for (const el of nodes) {
                      const txt = (el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                      if (!tokens.some((t) => txt.includes(t))) continue;
                      const clickable =
                        el.closest('button, [role=\"option\"], li, mat-option, .orq-droplist__item') || el;
                      clickable.scrollIntoView({ block: 'center' });
                      clickable.click();
                      return true;
                    }
                  }
                }
                return false;
                """
            )
            return bool(clicked)
        except Exception:
            return False

    async def open_time_period(self) -> None:
        await self.dismiss_modal_overlay("before time period (cayman)", wait_seconds=2)

        if self._is_custom_period_active() or self._has_custom_period_option():
            await self.log("OK Time Period opened (Cayman)")
            return

        try:
            await super().open_time_period()
        except Exception:
            pass

        deadline = time.time() + 30
        while time.time() < deadline:
            if self._is_custom_period_active() or self._has_custom_period_option():
                await self.log("OK Time Period opened (Cayman)")
                return
            self._expand_time_period_cayman_js()
            time.sleep(0.5)

        raise RuntimeError("Could not click required BTG element: time period")

    async def select_custom_period(self) -> None:
        await self.dismiss_modal_overlay("before custom period (cayman)", wait_seconds=2)
        await self.open_time_period()

        if self._is_custom_period_active():
            await self.log("OK Custom period already active (Cayman)")
            return

        try:
            await super().select_custom_period()
            return
        except Exception:
            pass

        deadline = time.time() + 45
        while time.time() < deadline:
            if self._is_custom_period_active():
                await self.log("OK Custom period active after fallback (Cayman)")
                return
            if not self._has_custom_period_option():
                self._expand_time_period_cayman_js()
                time.sleep(0.4)
            if self._click_custom_period_cayman_js():
                time.sleep(0.5)
                if self._is_custom_period_active():
                    await self.log("OK Custom period selected (Cayman fallback)")
                    return
            time.sleep(0.5)

        raise RuntimeError("Could not click required BTG element: custom period")

    def _click_export_all_history_cayman_js(self) -> bool:
        try:
            clicked = self.driver.execute_script(
                """
                const roots = [];
                const seen = new Set();
                const queue = [document];
                while (queue.length) {
                  const root = queue.shift();
                  if (!root || seen.has(root)) continue;
                  seen.add(root);
                  roots.push(root);
                  const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
                  for (const el of all) if (el && el.shadowRoot) queue.push(el.shadowRoot);
                }

                for (const root of roots) {
                  const nodes = root.querySelectorAll ? root.querySelectorAll('button, a, span') : [];
                  for (const el of nodes) {
                    const txt = (el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (!txt.includes('export all')) continue;
                    const clickable = el.closest('button, a, [role=\"button\"]') || el;
                    clickable.scrollIntoView({ block: 'center' });
                    clickable.click();
                    return true;
                  }
                }
                return false;
                """
            )
            return bool(clicked)
        except Exception:
            return False

    async def click_export(self) -> None:
        if self._click_now_with_fallback(self.sel.EXPORT_ALL_HISTORY_BTN):
            await self.log("OK Export all requested (Cayman)")
            return
        if self._click_export_all_history_cayman_js():
            await self.log("OK Export all requested (Cayman deep JS)")
            return
        raise RuntimeError("Could not click required BTG element: export all (history cayman)")

    async def click_download(self) -> None:
        # Cayman history flow is direct download from "Export all" button.
        await self.log("OK Download started (Cayman direct export)")
