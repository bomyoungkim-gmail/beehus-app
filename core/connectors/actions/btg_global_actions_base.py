"""
Shared actions for BTG Global connectors.
Contains the common Selenium flow used by BTG US and BTG Cayman.
"""

from typing import Any, Callable, Optional
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
import time
import random

from core.connectors.helpers.selenium_helpers import SeleniumHelpers


class BtgGlobalActionsBase:
    """Common BTG portal interactions reused by region-specific connectors."""

    def __init__(
        self,
        driver: WebDriver,
        helpers: SeleniumHelpers,
        selectors: Any,
        log_func: Callable,
    ):
        self.driver = driver
        self.helpers = helpers
        self.sel = selectors
        self.log = log_func

    def _is_visible(self, locator) -> bool:
        try:
            elements = self.driver.find_elements(*locator)
        except Exception:
            return False

        for el in elements:
            try:
                if el.is_displayed():
                    return True
            except StaleElementReferenceException:
                continue
            except Exception:
                continue
        return False

    def _click_if_visible(self, locator) -> bool:
        try:
            elements = self.driver.find_elements(*locator)
        except Exception:
            return False
        for el in elements:
            try:
                if el.is_displayed() and el.is_enabled():
                    el.click()
                    return True
            except StaleElementReferenceException:
                continue
            except Exception:
                continue
        return False

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

    def _click_now_with_fallback(self, locator) -> bool:
        """Fast click path: avoids long explicit waits in retry loops."""
        try:
            elements = self.driver.find_elements(*locator)
        except Exception:
            elements = []

        for el in elements:
            try:
                if el.is_displayed() and el.is_enabled():
                    el.click()
                    return True
            except StaleElementReferenceException:
                continue
            except Exception:
                continue

        for el in elements:
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                self.driver.execute_script("arguments[0].click();", el)
                return True
            except Exception:
                continue

        return False

    def _require_click(self, locator, action_name: str) -> None:
        if not self._click_with_fallback(locator):
            raise RuntimeError(f"Could not click required BTG element: {action_name}")

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

    def _wait_any_visible(self, locators, timeout_msg: str, timeout_seconds: Optional[int] = None):
        try:
            return self.helpers.wait_until(
                lambda d: any(
                    el.is_displayed()
                    for loc in locators
                    for el in d.find_elements(*loc)
                ),
                timeout=timeout_seconds,
            )
        except Exception as exc:
            raise TimeoutException(timeout_msg) from exc

    def _overlay_visible(self) -> bool:
        return self._is_visible(self.sel.MODAL_OVERLAY) or self._is_visible(self.sel.GENERIC_OVERLAY)

    def _overlay_state(self) -> dict:
        return {
            "modal": self._is_visible(self.sel.MODAL_OVERLAY),
            "generic": self._is_visible(self.sel.GENERIC_OVERLAY),
        }

    def _remove_generic_overlay_js(self) -> bool:
        try:
            removed = self.driver.execute_script(
                """
                const selectors = [
                  'div.overlay',
                  '.cdk-overlay-backdrop',
                  '.cdk-overlay-backdrop-showing',
                  '.shepherd-modal-overlay-container',
                  '.shepherd-modal-overlay-container.shepherd-modal-is-visible'
                ];

                let removedCount = 0;
                for (const sel of selectors) {
                  const nodes = document.querySelectorAll(sel);
                  nodes.forEach((o) => {
                    try {
                      o.style.pointerEvents = 'none';
                      o.style.display = 'none';
                      o.style.visibility = 'hidden';
                      o.remove();
                      removedCount += 1;
                    } catch (e) {}
                  });
                }
                return removedCount;
                """
            )
            return bool(removed)
        except Exception:
            return False

    def _wait_overlay_gone(self, timeout_seconds: int = 15) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self._overlay_visible():
                return True
            time.sleep(0.25)
        return not self._overlay_visible()

    def _wait_not_visible(self, locator, timeout_seconds: int = 8) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if not self._is_visible(locator):
                return True
            time.sleep(0.25)
        return not self._is_visible(locator)

    def _click_summary_holdings_check_all_js(self) -> bool:
        try:
            clicked = self.driver.execute_script(
                """
                const cards = Array.from(document.querySelectorAll('div.card-btg'));
                const target = cards.find((card) => {
                  const h3 = card.querySelector('h3');
                  if (!h3) return false;
                  const title = (h3.textContent || '').trim().toLowerCase();
                  return (
                    title.includes('summary of holdings') ||
                    title.includes('holdings summary') ||
                    title.includes('resumo de posicoes') ||
                    title.includes('resumo de posições')
                  );
                });
                if (!target) return false;
                const anchor = target.querySelector('a.see-more');
                if (!anchor) return false;
                anchor.scrollIntoView({ block: 'center' });
                anchor.click();
                return true;
                """
            )
            return bool(clicked)
        except Exception:
            return False

    def _mfe_summary_check_all_stats_js(self) -> dict:
        try:
            data = self.driver.execute_script(
                """
                const result = { summary_cards_mfe: 0, summary_check_all_mfe: 0 };
                const hosts = Array.from(document.querySelectorAll('wrapper-mfe *'))
                  .filter((el) => !!el.shadowRoot);

                for (const host of hosts) {
                  const root = host.shadowRoot;
                  const cards = Array.from(root.querySelectorAll('div.card-btg'));
                  const summaryCards = cards.filter((card) => {
                    const h3 = card.querySelector('h3');
                    const title = (h3?.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    return title.includes('summary of holdings') || title.includes('holdings summary');
                  });
                  result.summary_cards_mfe += summaryCards.length;
                  for (const card of summaryCards) {
                    result.summary_check_all_mfe += card.querySelectorAll('a.see-more').length;
                  }
                }
                return result;
                """
            )
            return data if isinstance(data, dict) else {"summary_cards_mfe": 0, "summary_check_all_mfe": 0}
        except Exception:
            return {"summary_cards_mfe": 0, "summary_check_all_mfe": 0}

    def _has_summary_holdings_check_all_mfe_js(self) -> bool:
        stats = self._mfe_summary_check_all_stats_js()
        return bool((stats.get("summary_check_all_mfe") or 0) > 0)

    def _click_summary_holdings_check_all_mfe_js(self) -> bool:
        try:
            clicked = self.driver.execute_script(
                """
                const hosts = Array.from(document.querySelectorAll('wrapper-mfe *'))
                  .filter((el) => !!el.shadowRoot);

                for (const host of hosts) {
                  const root = host.shadowRoot;
                  const cards = Array.from(root.querySelectorAll('div.card-btg'));
                  for (const card of cards) {
                    const h3 = card.querySelector('h3');
                    const title = (h3?.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (!(title.includes('summary of holdings') || title.includes('holdings summary'))) {
                      continue;
                    }
                    const anchor = card.querySelector('a.see-more');
                    if (!anchor) continue;
                    const txt = (anchor.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (!txt.includes('check all')) continue;
                    anchor.scrollIntoView({ block: 'center' });
                    anchor.click();
                    return true;
                  }
                }
                return false;
                """
            )
            return bool(clicked)
        except Exception:
            return False

    def _click_summary_holdings_check_all_deep_js(self) -> bool:
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

                for (const root of roots) {
                  const anchors = root.querySelectorAll ? root.querySelectorAll('a.see-more') : [];
                  for (const a of anchors) {
                    const text = (a.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (!text.includes('check all')) continue;

                    const card = a.closest('div.card-btg');
                    if (!card) continue;

                    const h3 = card.querySelector('h3');
                    const title = (h3?.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (!(title.includes('summary of holdings') || title.includes('holdings summary'))) {
                      continue;
                    }

                    a.scrollIntoView({ block: 'center' });
                    a.click();
                    return true;
                  }
                }
                return false;
                """
            )
            return bool(clicked)
        except Exception:
            return False

    def _has_summary_holdings_check_all_deep_js(self) -> bool:
        try:
            exists = self.driver.execute_script(
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

                for (const root of roots) {
                  const anchors = root.querySelectorAll ? root.querySelectorAll('a.see-more') : [];
                  for (const a of anchors) {
                    const text = (a.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (!text.includes('check all')) continue;
                    const card = a.closest('div.card-btg');
                    if (!card) continue;
                    const h3 = card.querySelector('h3');
                    const title = (h3?.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (title.includes('summary of holdings') || title.includes('holdings summary')) {
                      return true;
                    }
                  }
                }
                return false;
                """
            )
            return bool(exists)
        except Exception:
            return False

    def _click_history_check_all_deep_js(self) -> bool:
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

                // First pass: activities-history scoped check all
                for (const root of roots) {
                  const titles = root.querySelectorAll ? root.querySelectorAll('app-title-home') : [];
                  for (const t of titles) {
                    const h1 = t.querySelector('h1');
                    const title = (h1?.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (!title.includes('activities history')) continue;

                    const link = t.querySelector('a.orq-link span.orq-link__label');
                    if (!link) continue;
                    const txt = (link.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (!txt.includes('check all')) continue;
                    const anchor = link.closest('a.orq-link');
                    if (!anchor) continue;
                    anchor.scrollIntoView({ block: 'center' });
                    anchor.click();
                    return true;
                  }
                }

                // Second pass: generic inside app-history only
                for (const root of roots) {
                  const historyRoots = root.querySelectorAll ? root.querySelectorAll('app-history') : [];
                  for (const hr of historyRoots) {
                    const labels = hr.querySelectorAll('a.orq-link span.orq-link__label');
                    for (const label of labels) {
                      const txt = (label.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                      if (!txt.includes('check all')) continue;
                      const anchor = label.closest('a.orq-link');
                      if (!anchor) continue;
                      anchor.scrollIntoView({ block: 'center' });
                      anchor.click();
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

    def _has_history_check_all_deep_js(self) -> bool:
        try:
            exists = self.driver.execute_script(
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

                for (const root of roots) {
                  const titles = root.querySelectorAll ? root.querySelectorAll('app-title-home') : [];
                  for (const t of titles) {
                    const h1 = t.querySelector('h1');
                    const title = (h1?.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (!title.includes('activities history')) continue;

                    const link = t.querySelector('a.orq-link span.orq-link__label');
                    if (!link) continue;
                    const txt = (link.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (txt.includes('check all')) return true;
                  }
                }

                for (const root of roots) {
                  const historyRoots = root.querySelectorAll ? root.querySelectorAll('app-history') : [];
                  for (const hr of historyRoots) {
                    const labels = hr.querySelectorAll('a.orq-link span.orq-link__label');
                    for (const label of labels) {
                      const txt = (label.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                      if (txt.includes('check all')) return true;
                    }
                  }
                }
                return false;
                """
            )
            return bool(exists)
        except Exception:
            return False

    def _is_export_options_visible_js(self) -> bool:
        try:
            visible = self.driver.execute_script(
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

                for (const root of roots) {
                  const buttons = root.querySelectorAll ? root.querySelectorAll('button') : [];
                  for (const btn of buttons) {
                    const txt = (btn.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (txt.includes('export options')) return true;
                  }
                }
                return false;
                """
            )
            return bool(visible)
        except Exception:
            return False

    def _has_export_options_deep_js(self) -> bool:
        return self._is_export_options_visible_js()

    def _has_export_all_deep_js(self) -> bool:
        try:
            visible = self.driver.execute_script(
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

                for (const root of roots) {
                  const items = root.querySelectorAll ? root.querySelectorAll('div.item, button, span') : [];
                  for (const el of items) {
                    const txt = (el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (txt.includes('export all')) return true;
                  }
                }
                return false;
                """
            )
            return bool(visible)
        except Exception:
            return False

    def _is_holdings_details_page(self) -> bool:
        try:
            url = (self.driver.current_url or "").lower()
            if "/holdings/" in url:
                return True
        except Exception:
            pass
        try:
            return bool(
                self.driver.execute_script(
                    """
                    return !!document.querySelector('mfe-balance-allocation-details-element, wrapper-mfe mfe-balance-allocation-details-element');
                    """
                )
            )
        except Exception:
            return False

    def _click_export_options_deep_js(self) -> bool:
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

                for (const root of roots) {
                  const scoped = root.querySelectorAll
                    ? root.querySelectorAll('div.expand-btn button, div.expand-btn [role=\"button\"]')
                    : [];
                  for (const el of scoped) {
                    const txt = (el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (!txt.includes('export options')) continue;
                    el.scrollIntoView({ block: 'center' });
                    el.click();
                    return true;
                  }
                }

                for (const root of roots) {
                  const candidates = root.querySelectorAll
                    ? root.querySelectorAll('button, div.expand-btn, [role=\"button\"], span')
                    : [];
                  for (const el of candidates) {
                    const txt = (el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (!txt.includes('export options')) continue;
                    const clickable = el.closest('button, [role=\"button\"], div.expand-btn') || el;
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

    def _click_export_all_deep_js(self) -> bool:
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

                for (const root of roots) {
                  const itemsStrict = root.querySelectorAll ? root.querySelectorAll('div.item') : [];
                  for (const el of itemsStrict) {
                    const txt = (el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (!txt.includes('export all')) continue;
                    el.scrollIntoView({ block: 'center' });
                    el.click();
                    return true;
                  }
                }

                for (const root of roots) {
                  const items = root.querySelectorAll ? root.querySelectorAll('div.item, button, span') : [];
                  for (const el of items) {
                    const txt = (el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    if (!txt.includes('export all')) continue;
                    el.scrollIntoView({ block: 'center' });
                    el.click();
                    return true;
                  }
                }
                return false;
                """
            )
            return bool(clicked)
        except Exception:
            return False

    def _get_holdings_check_all_diagnostics(self) -> dict:
        data = {
            "url": "",
            "on_login": False,
            "summary_cards": 0,
            "summary_check_all": 0,
            "summary_cards_mfe": 0,
            "summary_check_all_mfe": 0,
            "history_check_all": 0,
            "export_options_visible": False,
        }
        try:
            data["url"] = self.driver.current_url or ""
        except Exception:
            pass

        try:
            data["on_login"] = self._is_visible(self.sel.EMAIL)
        except Exception:
            pass

        try:
            js_data = self.driver.execute_script(
                """
                const result = {
                  summary_cards: 0,
                  summary_check_all: 0,
                  history_check_all: 0,
                };
                const cards = Array.from(document.querySelectorAll('div.card-btg'));
                result.summary_cards = cards.filter((card) => {
                  const h3 = card.querySelector('h3');
                  const t = (h3?.textContent || '').trim().toLowerCase();
                  return t.includes('summary of holdings') || t.includes('holdings summary');
                }).length;
                result.summary_check_all = cards
                  .filter((card) => {
                    const h3 = card.querySelector('h3');
                    const t = (h3?.textContent || '').trim().toLowerCase();
                    return t.includes('summary of holdings') || t.includes('holdings summary');
                  })
                  .reduce((acc, card) => acc + card.querySelectorAll('a.see-more').length, 0);
                const historyRoot = document.querySelector('app-history');
                result.history_check_all = historyRoot
                  ? historyRoot.querySelectorAll('a.see-more, a.orq-link').length
                  : 0;
                return result;
                """
            )
            if isinstance(js_data, dict):
                data.update(js_data)
        except Exception:
            pass
        try:
            data.update(self._mfe_summary_check_all_stats_js())
        except Exception:
            pass

        try:
            data["export_options_visible"] = (
                self._is_visible(self.sel.EXPORT_OPTIONS_BTN) or self._is_export_options_visible_js()
            )
        except Exception:
            pass
        return data

    async def dismiss_modal_overlay(self, context: str = "", wait_seconds: int = 15) -> None:
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

            overlay_state = self._overlay_state()
            if overlay_state.get("generic") and not overlay_state.get("modal"):
                await self.log("INFO Generic overlay visible, waiting to clear before close")
                if self._wait_overlay_gone(timeout_seconds=6):
                    return
                if self._overlay_visible():
                    if self._remove_generic_overlay_js():
                        await self.log("WARN Generic overlay removed via JS fallback")
                        if self._wait_overlay_gone(timeout_seconds=4):
                            return

            dont_show_visible = self._is_visible(self.sel.DONT_SHOW_AGAIN)
            if dont_show_visible and self._click_if_visible(self.sel.DONT_SHOW_AGAIN):
                await self.log("OK Clicked modal action: Don't show again")
                if self._wait_not_visible(self.sel.DONT_SHOW_AGAIN, timeout_seconds=6):
                    await self.log("OK 'Don't show again' no longer visible")
                else:
                    await self.log("WARN 'Don't show again' still visible after click")

                if self._wait_overlay_gone(timeout_seconds=8):
                    await self.log("OK Modal overlay gone after 'Don't show again'")
                    return
                await self.log("WARN Overlay still visible after 'Don't show again'")
                # If this modal had "Don't show again", do not guess other close buttons.
                # Keep behavior deterministic: wait for overlay to disappear or fail.
                continue

            if overlay_state.get("modal"):
                overlays = self.driver.find_elements(*self.sel.MODAL_OVERLAY)
                for ov in overlays:
                    try:
                        btns = ov.find_elements(*self.sel.MODAL_CLOSE_BUTTON)
                        for btn in btns:
                            if btn.is_displayed() and btn.is_enabled():
                                btn.click()
                                await self.log("OK Dismissed modal (Close button in overlay)")
                                break
                    except Exception:
                        continue
                if not self._overlay_visible():
                    return

            if self._click_if_visible(self.sel.MODAL_CLOSE_BUTTON):
                await self.log("OK Dismissed modal (Close button)")
            elif self._click_if_visible(self.sel.MODAL_CLOSE):
                await self.log("OK Dismissed modal (Close icon/btn)")
            elif self._click_if_visible(self.sel.MODAL_SKIP):
                await self.log("OK Dismissed modal (Skip/Close text)")

            time.sleep(1)

        if self._overlay_visible():
            if self._wait_overlay_gone():
                await self.log("OK Modal overlay gone after close")
                return

        if self._overlay_visible() and self._is_visible(self.sel.GENERIC_OVERLAY):
            if self._remove_generic_overlay_js():
                await self.log("WARN Generic overlay removed via JS fallback")

        if self._overlay_visible():
            overlays = self.driver.find_elements(*self.sel.MODAL_OVERLAY)
            if overlays:
                try:
                    self.driver.execute_script("arguments[0].click();", overlays[-1])
                    time.sleep(1)
                except Exception:
                    pass

        if self._overlay_visible():
            overlays = self.driver.find_elements(*self.sel.GENERIC_OVERLAY)
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
            raise RuntimeError("Modal overlay still visible after dismiss attempts")

        if self._wait_not_visible(self.sel.DONT_SHOW_AGAIN, timeout_seconds=4):
            await self.log("OK Overlay dismissed and 'Don't show again' hidden")
        else:
            await self.log("WARN Overlay dismissed but 'Don't show again' still visible")

    async def navigate_to_login(self, url: str) -> None:
        await self.log(f"NAVIGATE: {url}")
        self.driver.get(url)

    async def click_portal_global(self) -> None:
        before_handles = set(self.driver.window_handles)
        deadline = time.time() + 60
        refreshed_once = False
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

            if not refreshed_once and (deadline - time.time()) <= 30:
                try:
                    self.driver.refresh()
                    refreshed_once = True
                    await self.log("INFO Portal Global not visible yet; refreshed login page once")
                except Exception:
                    pass

            time.sleep(0.5)

        if self._is_visible(self.sel.EMAIL):
            await self.log("INFO Global login form visible after extended wait, skipping Portal Global")
            return

        raise TimeoutException("Portal Global and login form were not visible after waiting on login page.")

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
        try:
            self.helpers.wait_for_visible(*self.sel.EMAIL)
            await self.log("OK Login form visible")
        except Exception as exc:
            current_url = ""
            title = ""
            try:
                current_url = self.driver.current_url
                title = self.driver.title
            except Exception:
                pass
            raise RuntimeError(
                f"Login form not visible. url={current_url!r}, title={title!r}"
            ) from exc

    async def fill_credentials(self, email: str, password: str) -> None:
        email_input = self.helpers.wait_for_visible(*self.sel.EMAIL)
        password_input = self.helpers.wait_for_visible(*self.sel.PASSWORD)

        self._type_human(email_input, email)
        self._type_human(password_input, password)
        await self.log("OK Credentials filled")

        sign_in_btn = self._wait_enabled(self.sel.SIGN_IN)
        sign_in_btn.click()
        await self.log("OK Sign in submitted")

    async def request_otp(self) -> None:
        await self.log("INFO OTP already sent, waiting for user input")

    async def wait_for_otp(self, timeout_seconds: int = 240) -> None:
        self.helpers.wait_for_element(*self.sel.OTP_CODE)
        await self.log("INFO Waiting for OTP entry")

        continue_btn = self._wait_enabled(self.sel.OTP_CONTINUE, timeout=timeout_seconds)
        continue_btn.click()
        await self.log("OK OTP continued")

    async def select_all_accounts(self) -> None:
        """Selects all available accounts using JS click for reliability."""
        try:
            total_chk = self.driver.find_elements(*self.sel.CHECKBOX_TOTAL)
            if total_chk:
                await self.log("INFO Found Total Checkbox, attempting click...")
                self.driver.execute_script("arguments[0].click();", total_chk[0])
                time.sleep(1)
                await self.log("OK Total Checkbox clicked")
                return

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
        try:
            access_btn.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", access_btn)
        await self.log("OK Access submitted")
        await self.dismiss_modal_overlay("post-access", wait_seconds=6)

    async def open_start_date_input(self) -> None:
        await self.dismiss_modal_overlay("before start date input")
        self._require_click(self.sel.DATE_INPUT, "start date input")
        await self.log("OK Start date input opened")

    async def select_calendar_date(self, date_str: str) -> None:
        day_cell = (By.XPATH, f"//td[@title='{date_str}']")
        self._require_click(day_cell, f"calendar day {date_str}")
        await self.log(f"OK Date selected: {date_str}")

    async def open_check_all_anchor(self) -> None:
        summary_locator = getattr(self.sel, "CHECK_ALL_ANCHOR_SUMMARY", None)
        if not summary_locator:
            raise RuntimeError("Missing selector CHECK_ALL_ANCHOR_SUMMARY for holdings check all")

        await self.dismiss_modal_overlay("before holdings check all", wait_seconds=2)

        if self._is_visible(self.sel.EMAIL):
            raise RuntimeError("Session returned to login while waiting for holdings check all")

        diag = self._get_holdings_check_all_diagnostics()
        await self.log(
            "DEBUG Holdings check-all diag - "
            f"url={diag.get('url')}, on_login={diag.get('on_login')}, "
            f"summary_cards={diag.get('summary_cards')}, "
            f"summary_check_all={diag.get('summary_check_all')}, "
            f"summary_cards_mfe={diag.get('summary_cards_mfe')}, "
            f"summary_check_all_mfe={diag.get('summary_check_all_mfe')}, "
            f"history_check_all={diag.get('history_check_all')}, "
            f"export_options_visible={diag.get('export_options_visible')}"
        )

        if self._is_holdings_details_page():
            await self.log("INFO Holdings details page already open; skipping summary Check all click")
            return

        try:
            self.helpers.wait_until(
                lambda d: (
                    self._is_visible(summary_locator)
                    or self._has_summary_holdings_check_all_mfe_js()
                    or self._is_holdings_details_page()
                ),
                timeout=60,
            )
        except Exception as exc:
            raise RuntimeError("Holdings summary Check all anchor did not become visible.") from exc

        if self._is_holdings_details_page() and not self._is_visible(summary_locator) and not self._has_summary_holdings_check_all_mfe_js():
            await self.log("INFO Holdings details page detected while waiting for summary Check all")
            return

        attempts = [
            ("summary card (mfe shadow)", self._click_summary_holdings_check_all_mfe_js),
            ("summary card", lambda: self._click_now_with_fallback(summary_locator)),
            ("summary JS fallback", self._click_summary_holdings_check_all_js),
        ]
        for label, click_fn in attempts:
            try:
                clicked = bool(click_fn())
            except Exception:
                clicked = False
            if not clicked:
                continue
            try:
                self.helpers.wait_until(
                    lambda d: (
                        self._is_visible(self.sel.EXPORT_OPTIONS_BTN)
                        or self._has_export_options_deep_js()
                        or self._is_holdings_details_page()
                    ),
                    timeout=60,
                )
                await self.log(f"OK Check all opened ({label})")
                return
            except Exception:
                await self.log(f"WARN {label} click had no expected effect (export options/details)")

        try:
            ts = time.strftime("%Y%m%d_%H%M%S")
            path = f"/app/artifacts/error_check_all_holdings_{ts}.png"
            self.driver.save_screenshot(path)
            await self.log(f"SCREEN Holdings check-all failure screenshot: {path}")
        except Exception:
            pass
        raise RuntimeError("Could not click required BTG element: check all (holdings)")

    async def open_export_options(self) -> None:
        await self.dismiss_modal_overlay("before export options", wait_seconds=2)
        try:
            self.helpers.wait_until(
                lambda d: self._is_visible(self.sel.EXPORT_OPTIONS_BTN) or self._has_export_options_deep_js(),
                timeout=60,
            )
        except Exception as exc:
            raise RuntimeError("Export options button did not become visible.") from exc
        if self._click_now_with_fallback(self.sel.EXPORT_OPTIONS_BTN):
            await self.log("OK Export options opened")
            return
        if self._click_export_options_deep_js():
            await self.log("OK Export options opened (deep JS)")
            return

        raise RuntimeError("Could not click required BTG element: export options")

    async def select_export_all(self) -> None:
        await self.dismiss_modal_overlay("before export all", wait_seconds=2)
        try:
            self.helpers.wait_until(
                lambda d: self._is_visible(self.sel.EXPORT_ALL_OPTION) or self._has_export_all_deep_js(),
                timeout=60,
            )
        except Exception as exc:
            raise RuntimeError("Export all option did not become visible.") from exc
        if self._click_now_with_fallback(self.sel.EXPORT_ALL_OPTION):
            await self.log("OK Export all selected")
            return
        if self._click_export_all_deep_js():
            await self.log("OK Export all selected (deep JS)")
            return

        raise RuntimeError("Could not click required BTG element: export all option")

    async def open_portfolio(self) -> None:
        if not self._is_visible(self.sel.SIDEBAR_PORTFOLIO):
            self._click_if_visible(self.sel.SIDEBAR_TOGGLE)
        self._require_click(self.sel.SIDEBAR_PORTFOLIO, "sidebar portfolio")
        await self.log("OK Portfolio opened")

    async def click_portfolio_check_all(self) -> None:
        await self.dismiss_modal_overlay("before portfolio check all", wait_seconds=2)
        locators = []
        activities_locator = getattr(self.sel, "PORTFOLIO_CHECK_ALL_ACTIVITIES", None)
        if activities_locator:
            locators.append(("activities history", activities_locator))
        locators.append(("generic", self.sel.PORTFOLIO_CHECK_ALL))

        # First, wait for either normal DOM locator or shadow/MFE history check-all.
        try:
            self.helpers.wait_until(
                lambda d: any(self._is_visible(locator) for _, locator in locators) or self._has_history_check_all_deep_js(),
                timeout=60,
            )
        except Exception:
            pass

        # Prefer explicit history check-all via shadow/MFE when available.
        if self._has_history_check_all_deep_js() and self._click_history_check_all_deep_js():
            self._wait_any_visible(
                [self.sel.FILTERS_BTN],
                "Filters button did not become visible after deep JS portfolio check all click.",
                timeout_seconds=60,
            )
            await self.log("OK Portfolio check all selected (deep JS)")
            return

        for label, locator in locators:
            try:
                self._wait_any_visible(
                    [locator],
                    f"Portfolio check all ({label}) did not become visible.",
                    timeout_seconds=60,
                )
            except TimeoutException:
                continue

            if not self._click_now_with_fallback(locator):
                continue
            try:
                self._wait_any_visible(
                    [self.sel.FILTERS_BTN],
                    "Filters button did not become visible after portfolio check all click.",
                    timeout_seconds=60,
                )
                await self.log(f"OK Portfolio check all selected ({label})")
                return
            except TimeoutException:
                await self.log(f"WARN Portfolio check all click had no expected effect ({label})")

        if self._click_history_check_all_deep_js():
            self._wait_any_visible(
                [self.sel.FILTERS_BTN],
                "Filters button did not become visible after deep JS portfolio check all click.",
                timeout_seconds=60,
            )
            await self.log("OK Portfolio check all selected (deep JS)")
            return

        raise RuntimeError("Could not click required BTG element: portfolio check all")

    async def open_filters(self) -> None:
        self._require_click(self.sel.FILTERS_BTN, "filters button")
        await self.log("OK Filters opened")

    async def open_time_period(self) -> None:
        self._require_click(self.sel.TIME_PERIOD, "time period")
        await self.log("OK Time Period opened")

    async def select_custom_period(self) -> None:
        self._require_click(self.sel.CUSTOM_PERIOD, "custom period")
        await self.log("OK Custom period selected")

    async def set_custom_period_dates(self, date_str: str) -> None:
        date_inputs = self.driver.find_elements(*self.sel.CUSTOM_DATE_INPUTS)
        if len(date_inputs) >= 2:
            date_inputs[0].click()
            await self.select_calendar_date(date_str)
            date_inputs[1].click()
            await self.select_calendar_date(date_str)
        else:
            self._click_with_fallback(self.sel.CUSTOM_DATE_INPUTS)
            await self.select_calendar_date(date_str)
        await self.log(f"OK Custom period dates set: {date_str}")

    async def click_filter(self) -> None:
        self._require_click(self.sel.FILTER_BTN, "filter apply")
        await self.log("OK Filter applied")

    async def click_export(self) -> None:
        self._require_click(self.sel.EXPORT_BTN, "export button")
        await self.log("OK Export requested")

    async def click_download(self) -> None:
        self._require_click(self.sel.DOWNLOAD_BTN, "download button")
        await self.log("OK Download started")

    def _type_human(self, el, value: str) -> None:
        el.click()
        el.send_keys(Keys.CONTROL, "a")
        el.send_keys(Keys.BACKSPACE)
        for ch in value:
            ActionChains(self.driver).send_keys(ch).perform()
            time.sleep(random.uniform(0.03, 0.09))

    async def open_profile_menu(self) -> bool:
        if self._click_if_visible(self.sel.PROFILE_MENU):
            await self.log("OK Profile menu opened")
            return True
        await self.log("WARN Profile menu not visible")
        return False

    async def logout(self) -> None:
        if await self.open_profile_menu():
            await self.click_sign_out()
            await self.log("OK Signed out")

    async def click_sign_out(self) -> None:
        self._click_with_fallback(self.sel.SIGN_OUT)
        await self.log("OK Sign out clicked")

    async def export_holdings(self, date: str) -> None:
        await self.log(f"Exporting holdings for date: {date}")
        await self.open_start_date_input()
        await self.select_calendar_date(date)
        # Required sequence: click holdings "Check all" first, then open export options.
        await self.open_check_all_anchor()
        await self.open_export_options()
        await self.select_export_all()
        await self.log("OK Holdings export completed")

    async def export_history(self, date: str) -> None:
        await self.log(f"Exporting history for date: {date}")
        await self.open_portfolio()
        await self.click_portfolio_check_all()
        await self.open_filters()
        await self.open_time_period()
        await self.select_custom_period()
        await self.set_custom_period_dates(date)
        await self.click_filter()
        await self.click_export()
        await self.click_download()
        await self.log("OK History export completed")
