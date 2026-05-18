"""
Morgan Stanley connector - refactored structure.
"""

import logging
import json
import asyncio
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from selenium.webdriver.remote.webdriver import WebDriver

from core.connectors.base import BaseConnector
from core.connectors.helpers.selenium_helpers import SeleniumHelpers
from core.connectors.actions.morgan_stanley_actions import MorganStanleyActions
from core.connectors.seletores.morgan_stanley import SeletorMorganStanley
from core.schemas.messages import ScrapeResult
from core.utils.date_utils import get_now, get_today

logger = logging.getLogger(__name__)

CIRCUIT_STATE_FILE = Path("/app/artifacts/ms_circuit_breaker_state.json")
CIRCUIT_FAILURE_THRESHOLD = 3
CIRCUIT_OPEN_SECONDS = 15 * 60


@dataclass
class MorganStanleyCredentials:
    username: str
    password: str


class MorganStanleyConnector(BaseConnector):
    """Conector para automacao do portal Morgan Stanley."""

    @property
    def name(self) -> str:
        return "morgan_stanley_login"

    def _make_run_logger(self, run):
        async def log(msg: str):
            logger.info(f"[MorganStanley] {msg}")
            if run:
                timestamped_msg = f"[{get_now().time()}] {msg}"
                await run.update({"$push": {"logs": timestamped_msg}})

        return log

    async def _setup_run(self, params: Dict[str, Any]):
        from core.models.mongo_models import Run

        run_id = params.get("run_id")
        run = await Run.get(run_id) if run_id else None
        return run, self._make_run_logger(run)

    def _validate_credentials(self, params: Dict[str, Any]) -> Optional[MorganStanleyCredentials]:
        username = params.get("username") or params.get("user")
        password = params.get("password") or params.get("pass")
        if not username or not password:
            return None
        return MorganStanleyCredentials(username=username, password=password)

    def _create_actions(self, driver: WebDriver, log_func) -> MorganStanleyActions:
        helpers = SeleniumHelpers(driver, timeout=50)
        selectors = SeletorMorganStanley()
        return MorganStanleyActions(driver, helpers, selectors, log_func)

    def _target_date_d_minus_two(self) -> date:
        return get_today() - timedelta(days=2)

    def _build_login_url_candidates(self, params: Dict[str, Any]) -> list[str]:
        manual = params.get("ms_login_urls")
        if isinstance(manual, str) and manual.strip():
            parsed = [item.strip() for item in manual.split(",") if item.strip()]
            if parsed:
                return parsed
        return list(SeletorMorganStanley.URL_CANDIDATES)

    def _is_retryable_login_error(self, exc: Exception) -> bool:
        return self._classify_login_error(exc)["retryable"]

    def _classify_login_error(self, exc: Exception) -> dict[str, str | bool]:
        message = f"{type(exc).__name__}: {exc}"
        lower = message.lower()
        if "service is currently unavailable" in lower or "temporarily unavailable" in lower:
            return {
                "code": "service_unavailable",
                "retryable": True,
                "stage": "post_login",
                "message": message,
            }
        if "mfa delivery failed" in lower or "internal error submitting otp delivery request" in lower:
            return {
                "code": "mfa_delivery_internal_error",
                "retryable": True,
                "stage": "mfa_delivery",
                "message": message,
            }
        if "timeout waiting for morgan stanley post-login completion" in lower:
            return {
                "code": "post_login_timeout",
                "retryable": True,
                "stage": "post_login",
                "message": message,
            }
        if "connection reset" in lower or "err_http2_protocol_error" in lower:
            return {
                "code": "network_transient",
                "retryable": True,
                "stage": "network",
                "message": message,
            }
        return {
            "code": "non_retryable",
            "retryable": False,
            "stage": "unknown",
            "message": message,
        }

    def _safe_load_circuit_state(self) -> dict:
        try:
            if not CIRCUIT_STATE_FILE.exists():
                return {}
            return json.loads(CIRCUIT_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _safe_save_circuit_state(self, state: dict) -> None:
        try:
            CIRCUIT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CIRCUIT_STATE_FILE.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")
        except Exception:
            pass

    async def _check_circuit_breaker(self, log_func) -> bool:
        now_ts = int(get_now().timestamp())
        state = self._safe_load_circuit_state()
        open_until = int(state.get("open_until", 0) or 0)
        if open_until > now_ts:
            remaining = open_until - now_ts
            await log_func(
                "CIRCUIT Morgan Stanley breaker OPEN: "
                f"remaining_seconds={remaining} reason={state.get('last_code', 'unknown')}"
            )
            return True
        if open_until and open_until <= now_ts:
            state["open_until"] = 0
            state["failure_count"] = 0
            self._safe_save_circuit_state(state)
        return False

    async def _register_circuit_outcome(self, classification: dict, log_func) -> None:
        now_ts = int(get_now().timestamp())
        state = self._safe_load_circuit_state()
        code = str(classification.get("code") or "unknown")
        retryable = bool(classification.get("retryable"))
        if retryable and code in {"service_unavailable", "mfa_delivery_internal_error", "post_login_timeout"}:
            failure_count = int(state.get("failure_count", 0) or 0) + 1
            state["failure_count"] = failure_count
            state["last_failure_at"] = now_ts
            state["last_code"] = code
            if failure_count >= CIRCUIT_FAILURE_THRESHOLD:
                state["open_until"] = now_ts + CIRCUIT_OPEN_SECONDS
                await log_func(
                    "CIRCUIT OPEN triggered for Morgan Stanley: "
                    f"failure_count={failure_count} open_seconds={CIRCUIT_OPEN_SECONDS} code={code}"
                )
            else:
                await log_func(
                    "CIRCUIT failure recorded for Morgan Stanley: "
                    f"failure_count={failure_count}/{CIRCUIT_FAILURE_THRESHOLD} code={code}"
                )
        else:
            if state.get("failure_count"):
                await log_func("CIRCUIT reset: non-retryable or successful transition detected")
            state["failure_count"] = 0
            state["open_until"] = 0
            state["last_code"] = code
            state["last_failure_at"] = now_ts
        self._safe_save_circuit_state(state)

    async def _write_technical_report(
        self,
        run_id: Optional[str],
        log_func,
        status: str,
        classification: dict,
        driver: WebDriver,
        screenshot_path: str | None = None,
        html_path: str | None = None,
    ) -> str | None:
        report = {
            "report_type": "morgan_stanley_technical_report",
            "created_at": get_now().isoformat(),
            "run_id": run_id or "manual-run",
            "status": status,
            "error_code": classification.get("code"),
            "error_stage": classification.get("stage"),
            "retryable": classification.get("retryable"),
            "message": classification.get("message"),
            "url": getattr(driver, "current_url", None),
            "title": getattr(driver, "title", None),
            "artifacts": {
                "screenshot": screenshot_path,
                "html_snapshot": html_path,
            },
        }
        try:
            ts = get_now().strftime("%Y%m%d_%H%M%S")
            report_path = Path("/app/artifacts") / f"morgan_stanley_report_{ts}.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
            await log_func(f"REPORT Technical report saved: {report_path}")
            return str(report_path)
        except Exception as report_exc:
            await log_func(f"WARN Failed writing technical report: {report_exc}")
            return None

    def _success_result(self, run_id: Optional[str], username: str) -> ScrapeResult:
        return ScrapeResult(
            run_id=run_id or "manual-run",
            success=True,
            data={"message": "Morgan Stanley flow completed", "user": username},
        )

    def _error_result(self, run_id: Optional[str], error: str) -> ScrapeResult:
        return ScrapeResult(run_id=run_id or "manual-run", success=False, error=error)

    async def _handle_error(
        self,
        e: Exception,
        driver: WebDriver,
        run_id: Optional[str],
        log_func,
        credentials: Optional[MorganStanleyCredentials] = None,
    ) -> ScrapeResult:
        error_details = str(e).strip() or repr(e)
        error_msg = f"{type(e).__name__}: {error_details}"
        classification = self._classify_login_error(e)

        if credentials:
            await log_func(f"ERROR Morgan Stanley failure for user {credentials.username}: {error_msg}")
        else:
            await log_func(f"ERROR Morgan Stanley failure: {error_msg}")

        screenshot_path: str | None = None
        html_path: str | None = None
        try:
            timestamp = get_now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"/app/artifacts/error_morgan_stanley_{timestamp}.png"
            html_path = f"/app/artifacts/error_morgan_stanley_{timestamp}.html"
            driver.save_screenshot(screenshot_path)
            page_source = driver.page_source or ""
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page_source)
            await log_func(f"SCREEN Screenshot saved: {screenshot_path}")
            await log_func(f"SCREEN HTML snapshot saved: {html_path}")
        except Exception as ss_e:
            await log_func(f"WARN Failed to save screenshot: {ss_e}")

        await self._register_circuit_outcome(classification, log_func)
        await self._write_technical_report(
            run_id=run_id,
            log_func=log_func,
            status="failed",
            classification=classification,
            driver=driver,
            screenshot_path=screenshot_path,
            html_path=html_path,
        )
        return self._error_result(run_id, error_msg)

    async def scrape(self, driver: WebDriver, params: Dict[str, Any]) -> ScrapeResult:
        run, log = await self._setup_run(params)
        run_id = params.get("run_id")

        logger.info(f"Starting Morgan Stanley flow with params: {params}")

        credentials = self._validate_credentials(params)
        if not credentials:
            error_msg = "Missing credentials - check username/user and password/pass"
            await log(f"ERROR {error_msg}")
            await log(f"INFO Available params: {list(params.keys())}")
            return self._error_result(run_id, error_msg)

        if await self._check_circuit_breaker(log):
            return self._error_result(
                run_id,
                "Circuit breaker open for Morgan Stanley due to repeated portal instability",
            )

        actions = self._create_actions(driver, log)

        try:
            # 1-3. Login with multiple entry strategies
            login_urls = self._build_login_url_candidates(params)
            login_completed = False
            last_login_error: Optional[Exception] = None
            max_attempts_per_strategy = 2
            backoff_seconds = [3, 8]
            for idx, login_url in enumerate(login_urls, start=1):
                for attempt in range(1, max_attempts_per_strategy + 1):
                    await log(
                        "LOGIN Strategy "
                        f"{idx}/{len(login_urls)} attempt {attempt}/{max_attempts_per_strategy} "
                        f"using URL: {login_url}"
                    )
                    try:
                        await actions.navigate_to_login(login_url)
                        await actions.fill_credentials(credentials.username, credentials.password)
                        await actions.submit_login()
                        await actions.wait_for_post_login_ready(timeout_seconds=180)
                        login_completed = True
                        await log(f"LOGIN Strategy {idx} succeeded on attempt {attempt}")
                        break
                    except Exception as login_exc:
                        last_login_error = login_exc
                        classification = self._classify_login_error(login_exc)
                        await log(
                            "WARN LOGIN strategy failed "
                            f"{idx}/{len(login_urls)} attempt={attempt} "
                            f"code={classification['code']} retryable={classification['retryable']} "
                            f"error={type(login_exc).__name__}: {login_exc}"
                        )

                        should_retry_same_strategy = (
                            attempt < max_attempts_per_strategy
                            and bool(classification.get("retryable"))
                        )
                        if should_retry_same_strategy:
                            sleep_for = backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)]
                            await log(
                                f"LOGIN Backoff before retrying same strategy: sleep_seconds={sleep_for}"
                            )
                            await asyncio.sleep(sleep_for)
                            try:
                                driver.delete_all_cookies()
                            except Exception:
                                pass
                            try:
                                driver.get("about:blank")
                            except Exception:
                                pass
                            continue
                        break

                if login_completed:
                    break
                if last_login_error and (
                    idx >= len(login_urls) or not self._is_retryable_login_error(last_login_error)
                ):
                    raise last_login_error

            if not login_completed and last_login_error:
                raise last_login_error

            # 4-7. Accounts > Holdings > Download
            await actions.go_to_holdings()
            await actions.click_download_and_wait()

            # 8-16. Accounts > Activity > Custom Date Range (D-2) > Download
            await actions.go_to_activity()
            await actions.set_activity_custom_date_range(self._target_date_d_minus_two())
            await actions.click_download_and_wait()

            # 17. Logout
            await actions.logout()
            await self._register_circuit_outcome(
                {"code": "success", "retryable": False, "stage": "completed", "message": "success"},
                log,
            )
            await self._write_technical_report(
                run_id=run_id,
                log_func=log,
                status="success",
                classification={"code": "success", "retryable": False, "stage": "completed", "message": "success"},
                driver=driver,
            )

            return self._success_result(run_id, credentials.username)
        except Exception as e:
            try:
                await actions.logout()
            except Exception:
                pass
            return await self._handle_error(e, driver, run_id, log, credentials)
