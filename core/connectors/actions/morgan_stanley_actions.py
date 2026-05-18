import asyncio
import os
import time
from datetime import date
from pathlib import Path
from typing import Callable

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.remote.webdriver import WebDriver

from core.connectors.helpers.selenium_helpers import SeleniumHelpers
from core.connectors.seletores.morgan_stanley import SeletorMorganStanley


class MorganStanleyActions:
    """Encapsulates Morgan Stanley portal actions."""

    def __init__(
        self,
        driver: WebDriver,
        helpers: SeleniumHelpers,
        selectors: SeletorMorganStanley,
        log_func: Callable,
    ):
        self.driver = driver
        self.helpers = helpers
        self.sel = selectors
        self.log = log_func
        self._stealth_applied = False

    def _apply_browser_stealth(self) -> None:
        """Apply lightweight stealth overrides similar to JPM to reduce bot signals."""
        if self._stealth_applied:
            return
        if not hasattr(self.driver, "execute_cdp_cmd"):
            return

        try:
            caps = getattr(self.driver, "capabilities", {}) or {}
            version = caps.get("browserVersion") or caps.get("version") or "122.0.0.0"
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36"
            )
            self.driver.execute_cdp_cmd(
                "Network.setUserAgentOverride",
                {"userAgent": user_agent, "platform": "Windows"},
            )
        except Exception:
            pass

        stealth_script = """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
            if (!window.chrome) {
              window.chrome = { runtime: {}, app: {} };
            }
        """
        try:
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": stealth_script},
            )
            self._stealth_applied = True
        except Exception:
            pass

    def _safe_click(self, element) -> None:
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        except WebDriverException:
            pass

        try:
            element.click()
            return
        except WebDriverException:
            pass

        self.driver.execute_script("arguments[0].click();", element)

    def _is_element_visible(self, locator) -> bool:
        try:
            for element in self.driver.find_elements(*locator):
                if element.is_displayed():
                    return True
            return False
        except Exception:
            return False

    def _first_visible_element(self, locator):
        try:
            for element in self.driver.find_elements(*locator):
                if element.is_displayed():
                    return element
            return None
        except Exception:
            return None

    def _element_text(self, element) -> str:
        try:
            text = (element.text or "").strip()
            if text:
                return " ".join(text.split())
        except Exception:
            pass
        try:
            raw = (element.get_attribute("textContent") or "").strip()
            if raw:
                return " ".join(raw.split())
        except Exception:
            pass
        try:
            aria = (element.get_attribute("aria-label") or "").strip()
            if aria:
                return " ".join(aria.split())
        except Exception:
            pass
        return ""

    def _current_url(self) -> str:
        try:
            return self.driver.current_url or "-"
        except Exception:
            return "-"

    def _page_title(self) -> str:
        try:
            return self.driver.title or "-"
        except Exception:
            return "-"

    def _download_directory(self) -> Path:
        return Path(os.getenv("DOWNLOADS_DIR", "/downloads"))

    def _download_snapshot(self, download_dir: Path) -> dict[str, tuple[int, int]]:
        snapshot: dict[str, tuple[int, int]] = {}
        if not download_dir.exists() or not download_dir.is_dir():
            return snapshot

        for path in download_dir.iterdir():
            if not path.is_file():
                continue
            stat = path.stat()
            snapshot[path.name] = (stat.st_size, stat.st_mtime_ns)
        return snapshot

    def _visible_texts(self, locator, limit: int = 3) -> list[str]:
        texts: list[str] = []
        try:
            for element in self.driver.find_elements(*locator):
                if not element.is_displayed():
                    continue
                text = (element.text or "").strip()
                if text:
                    texts.append(" ".join(text.split()))
                if len(texts) >= limit:
                    break
        except Exception:
            return []
        return texts

    def _post_login_signals(self) -> dict[str, object]:
        return {
            "url": self._current_url(),
            "title": self._page_title(),
            "accounts_visible": self._is_element_visible(self.sel.ACCOUNTS_MENU),
            "mfa_input_visible": self._is_element_visible(self.sel.MFA_CODE_INPUT),
            "mfa_send_otp_visible": self._is_element_visible(self.sel.MFA_SEND_OTP_COMPONENT),
            "verify_identity_visible": self._is_element_visible(self.sel.VERIFY_IDENTITY_TITLE),
            "service_unavailable_visible": self._is_element_visible(self.sel.SERVICE_UNAVAILABLE_BANNER),
            "service_unavailable_internal_error_visible": self._is_element_visible(
                self.sel.SERVICE_UNAVAILABLE_INTERNAL_ERROR
            ),
            "login_error_texts": self._visible_texts(self.sel.LOGIN_ERROR_MESSAGE, limit=4),
            "login_banner_texts": self._visible_texts(self.sel.LOGIN_ERROR_BANNER, limit=4),
            "lock_or_reset_texts": self._visible_texts(self.sel.PASSWORD_RESET_OR_LOCK_NOTICE, limit=4),
            "service_unavailable_texts": self._visible_texts(
                self.sel.SERVICE_UNAVAILABLE_INTERNAL_ERROR,
                limit=3,
            ),
        }

    async def _save_debug_artifacts(self, prefix: str) -> tuple[str | None, str | None]:
        screenshot_path: str | None = None
        html_path: str | None = None
        try:
            ts = time.strftime("%Y%m%d_%H%M%S")
            artifacts_dir = Path("/app/artifacts")
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = str(artifacts_dir / f"{prefix}_{ts}.png")
            html_path = str(artifacts_dir / f"{prefix}_{ts}.html")
            self.driver.save_screenshot(screenshot_path)
            html = self.driver.page_source or ""
            Path(html_path).write_text(html, encoding="utf-8")
            await self.log(f"DEBUG Saved artifacts screenshot={screenshot_path} html={html_path}")
        except Exception as exc:
            await self.log(f"WARN Failed saving debug artifacts for {prefix}: {exc}")
        return screenshot_path, html_path

    async def navigate_to_login(self, url: str) -> None:
        self._apply_browser_stealth()
        await self.log(f"NAVIGATE {url}")
        self.driver.get(url)
        self.helpers.wait_for_visible(*self.sel.USERNAME_INPUT)

    async def fill_credentials(self, username: str, password: str) -> None:
        username_input = self.helpers.wait_for_visible(*self.sel.USERNAME_INPUT)
        username_input.clear()
        username_input.send_keys(username)

        password_input = self.helpers.wait_for_visible(*self.sel.PASSWORD_INPUT)
        password_input.clear()
        password_input.send_keys(password)
        await self.log("LOGIN Credentials filled")

    async def submit_login(self) -> None:
        login_btn = self.helpers.wait_until(
            EC.element_to_be_clickable(self.sel.LOGIN_BUTTON),
            timeout=30,
        )
        self._safe_click(login_btn)
        await self.log("LOGIN Submitted login form")

    async def wait_for_post_login_ready(self, timeout_seconds: int = 150) -> None:
        await self.log(f"LOGIN Waiting up to {timeout_seconds}s for post-login state")
        end_at = time.time() + timeout_seconds
        continue_clicks = 0
        mfa_detected = False
        mfa_route_logged = False
        unavailable_dismiss_attempted = False
        last_diag_at = 0.0

        while time.time() < end_at:
            if self._is_element_visible(self.sel.ACCOUNTS_MENU):
                await self.log("LOGIN Post-login ready: Accounts menu visible")
                return

            # Prioritize explicit post-login states before generic error probes.
            verify_continue = self._first_visible_element(self.sel.VERIFY_CONTINUE_BUTTON)
            if verify_continue and self._is_element_visible(self.sel.VERIFY_IDENTITY_TITLE):
                continue_clicks += 1
                self._safe_click(verify_continue)
                await self.log(
                    f"LOGIN Verify identity interstitial detected; clicked Continue ({continue_clicks})"
                )
                await asyncio.sleep(2)
                continue

            login_error = self._first_visible_element(self.sel.LOGIN_ERROR_MESSAGE)
            if login_error:
                error_text = self._element_text(login_error)
                if not error_text:
                    # Common case: hidden/empty accessibility alerts should not fail the run.
                    await asyncio.sleep(1)
                    continue
                raise RuntimeError(f"Login rejected by Morgan Stanley portal: {error_text}")

            if self._is_element_visible(self.sel.SERVICE_UNAVAILABLE_BANNER):
                raise RuntimeError(
                    "Morgan Stanley portal returned 'service unavailable' on login page "
                    "after credential submission"
                )

            if self._is_element_visible(self.sel.SERVICE_UNAVAILABLE_INTERNAL_ERROR):
                modal_texts = self._visible_texts(self.sel.SERVICE_UNAVAILABLE_INTERNAL_ERROR, limit=2)
                help_texts = self._visible_texts(self.sel.SERVICE_UNAVAILABLE_HELP_PHONE, limit=1)
                details = " | ".join((modal_texts + help_texts)) if (modal_texts or help_texts) else (
                    "internal error submitting OTP delivery request"
                )
                await self._save_debug_artifacts("ms_mfa_internal_error")
                raise RuntimeError(f"Morgan Stanley MFA delivery failed: {details}")

            if self._is_element_visible(self.sel.SERVICE_UNAVAILABLE_TITLE):
                if not unavailable_dismiss_attempted:
                    unavailable_dismiss_attempted = True
                    close_btn = self._first_visible_element(self.sel.SERVICE_UNAVAILABLE_CLOSE)
                    if close_btn:
                        self._safe_click(close_btn)
                        await self.log(
                            "WARN Service unavailable modal detected after login verification; "
                            "dismissed once and retrying state detection"
                        )
                        await asyncio.sleep(2)
                        continue

                raise RuntimeError(
                    "Morgan Stanley portal returned 'This service is temporarily unavailable' "
                    "after login verification"
                )

            mfa_input_visible = self._is_element_visible(self.sel.MFA_CODE_INPUT)
            mfa_submit_visible = self._is_element_visible(self.sel.MFA_SUBMIT_BUTTON)
            verify_identity_visible = self._is_element_visible(self.sel.VERIFY_IDENTITY_TITLE)
            on_mfa_route = "/prompts/mfa/" in self._current_url().lower()
            mfa_route_marker = self._is_element_visible(self.sel.MFA_DELIVER_ROUTE_MARKER)
            mfa_send_otp_visible = self._is_element_visible(self.sel.MFA_SEND_OTP_COMPONENT)

            if on_mfa_route and not mfa_route_logged:
                mfa_route_logged = True
                await self.log("LOGIN MFA route detected (/prompts/mfa/...)")

            if on_mfa_route or mfa_input_visible or mfa_route_marker or mfa_send_otp_visible or (
                verify_identity_visible and mfa_submit_visible
            ):
                if not mfa_detected:
                    mfa_detected = True
                    await self.log(
                        "LOGIN MFA/identity challenge detected; waiting for challenge to complete"
                    )
                await asyncio.sleep(1)
                continue

            now = time.time()
            if now - last_diag_at >= 15:
                last_diag_at = now
                signals = self._post_login_signals()
                login_errors = signals.get("login_error_texts") or []
                banners = signals.get("login_banner_texts") or []
                lock_reset = signals.get("lock_or_reset_texts") or []
                mfa_send_otp_visible = bool(signals.get("mfa_send_otp_visible"))
                service_unavailable_texts = signals.get("service_unavailable_texts") or []
                await self.log(
                    "DEBUG post-login pending "
                    f"url={self._current_url()} title={self._page_title()} "
                    f"continue_clicks={continue_clicks} mfa_detected={mfa_detected} "
                    f"mfa_send_otp_visible={mfa_send_otp_visible} "
                    f"login_errors={login_errors[:1]} banners={banners[:1]} "
                    f"lock_reset={lock_reset[:1]} service_unavailable={service_unavailable_texts[:1]}"
                )

            await asyncio.sleep(1)

        signals = self._post_login_signals()
        await self._save_debug_artifacts("ms_post_login_timeout")
        reason_parts: list[str] = []
        for key in ("login_error_texts", "login_banner_texts", "lock_or_reset_texts"):
            values = signals.get(key) or []
            if values:
                reason_parts.append(f"{key}={values[:2]}")
        reason = " | ".join(reason_parts) if reason_parts else "no explicit error text detected"
        raise TimeoutException(
            "Timeout waiting for Morgan Stanley post-login completion "
            f"(url={self._current_url()} title={self._page_title()} "
            f"continue_clicks={continue_clicks} mfa_detected={mfa_detected} reason={reason})"
        )

    async def _hover_accounts_menu(self) -> None:
        accounts_anchor = self.helpers.wait_for_visible(*self.sel.ACCOUNTS_MENU)
        ActionChains(self.driver).move_to_element(accounts_anchor).pause(0.4).perform()
        await self.log("NAV Hovered Accounts menu")

    async def go_to_holdings(self) -> None:
        await self._hover_accounts_menu()
        holdings = self.helpers.wait_until(
            EC.element_to_be_clickable(self.sel.HOLDINGS_SUBMENU),
            timeout=30,
        )
        self._safe_click(holdings)
        await self.log("NAV Clicked Holdings submenu")
        self.helpers.wait_until(EC.url_contains("/accounts/holdings"), timeout=60)

    async def go_to_activity(self) -> None:
        await self._hover_accounts_menu()
        activity = self.helpers.wait_until(
            EC.element_to_be_clickable(self.sel.ACTIVITY_SUBMENU),
            timeout=30,
        )
        self._safe_click(activity)
        await self.log("NAV Clicked Activity submenu")
        self.helpers.wait_until(EC.url_contains("/accounts/activity"), timeout=60)

    async def _wait_download_finished(self, baseline: dict[str, tuple[int, int]], timeout: int = 120) -> None:
        download_dir = self._download_directory()
        if not download_dir.exists() or not download_dir.is_dir():
            await self.log(
                f"WARN Download directory not found ({download_dir}). Waiting fixed 10s fallback."
            )
            await asyncio.sleep(10)
            return

        end_at = time.time() + timeout
        while time.time() < end_at:
            current = self._download_snapshot(download_dir)
            temp_present = any(
                name.endswith((".crdownload", ".part", ".tmp")) for name in current.keys()
            )

            changed = False
            for name, meta in current.items():
                previous = baseline.get(name)
                if previous is None or previous != meta:
                    changed = True
                    break

            if changed and not temp_present:
                await self.log("DOWNLOAD File download completed")
                return

            await asyncio.sleep(1)

        raise TimeoutException(f"Timeout waiting for download completion after {timeout}s")

    async def click_download_and_wait(self, timeout: int = 120) -> None:
        baseline = self._download_snapshot(self._download_directory())
        download_action = self.helpers.wait_until(
            EC.element_to_be_clickable(self.sel.DOWNLOAD_ACTION),
            timeout=40,
        )
        self._safe_click(download_action)
        await self.log("DOWNLOAD Clicked download action")
        await self._wait_download_finished(baseline, timeout=timeout)

    def _month_abbr(self, target_date: date) -> str:
        month_map = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        return month_map[target_date.month - 1]

    def _pick_date_in_calendar(self, target_date: date, timeout: int = 30) -> None:
        self.helpers.wait_for_visible(*self.sel.CALENDAR)

        month_selects = self.driver.find_elements(*self.sel.CALENDAR_MONTH_SELECT)
        year_selects = self.driver.find_elements(*self.sel.CALENDAR_YEAR_SELECT)
        visible_month = next((el for el in month_selects if el.is_displayed()), None)
        visible_year = next((el for el in year_selects if el.is_displayed()), None)

        if visible_month and visible_year:
            Select(visible_month).select_by_visible_text(self._month_abbr(target_date))
            Select(visible_year).select_by_visible_text(str(target_date.year))

        day_button = self.helpers.wait_until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    f"//mat-calendar//button[not(contains(@class,'mat-calendar-body-disabled')) and .//div[normalize-space()='{target_date.day}']]",
                )
            ),
            timeout=timeout,
        )
        self._safe_click(day_button)

    async def set_activity_custom_date_range(self, target_date: date) -> None:
        await self.log("ACTIVITY Opening period selector")
        period_trigger = self.helpers.wait_until(
            EC.element_to_be_clickable(self.sel.PERIOD_TRIGGER),
            timeout=40,
        )
        self._safe_click(period_trigger)

        custom_option = self.helpers.wait_until(
            EC.element_to_be_clickable(self.sel.CUSTOM_DATE_RANGE_OPTION),
            timeout=30,
        )
        self._safe_click(custom_option)

        self.helpers.wait_for_visible(*self.sel.CUSTOM_DATE_RANGE_MODAL_TITLE)
        await self.log(f"ACTIVITY Selecting custom date range D-2 ({target_date.isoformat()})")

        from_input = self.helpers.wait_until(
            EC.element_to_be_clickable(self.sel.FROM_DATE_INPUT),
            timeout=30,
        )
        self._safe_click(from_input)
        self._pick_date_in_calendar(target_date, timeout=30)

        to_input = self.helpers.wait_until(
            EC.element_to_be_clickable(self.sel.TO_DATE_INPUT),
            timeout=30,
        )
        self._safe_click(to_input)
        self._pick_date_in_calendar(target_date, timeout=30)

        apply_btn = self.helpers.wait_until(
            EC.element_to_be_clickable(self.sel.APPLY_DATE_RANGE_BUTTON),
            timeout=30,
        )
        self._safe_click(apply_btn)
        await self.log("ACTIVITY Applied custom date range")

        WebDriverWait(self.driver, 60).until_not(
            EC.visibility_of_element_located(self.sel.CUSTOM_DATE_RANGE_MODAL_TITLE)
        )

    async def logout(self) -> None:
        logout_btn = self.helpers.wait_until(
            EC.element_to_be_clickable(self.sel.LOGOUT_BUTTON),
            timeout=40,
        )
        self._safe_click(logout_btn)
        await self.log("LOGOUT Clicked Log out")
