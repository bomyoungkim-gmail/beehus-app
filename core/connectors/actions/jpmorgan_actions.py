import asyncio
from typing import Callable, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from core.connectors.helpers.selenium_helpers import SeleniumHelpers
from core.connectors.seletores.jpmorgan import SeletorJPMorgan


class JPMorganActions:
    def __init__(
        self,
        driver: WebDriver,
        helpers: SeleniumHelpers,
        selectors: SeletorJPMorgan,
        log_func: Callable,
    ):
        self.driver = driver
        self.helpers = helpers
        self.sel = selectors
        self.log = log_func

    def _is_system_requirements_page(self) -> bool:
        title = (self.driver.title or "").lower()
        url = (self.driver.current_url or "").lower()
        if "system requirements" in title:
            return True
        if "systemrequirements" in url or "system-requirements" in url:
            return True
        try:
            return "system requirements" in (self.driver.page_source or "").lower()
        except Exception:
            return False

    def _reset_session(self) -> None:
        try:
            self.driver.delete_all_cookies()
        except Exception:
            pass

    def _build_container_user_agent(self) -> Optional[str]:
        caps = getattr(self.driver, "capabilities", {}) or {}
        version = caps.get("browserVersion") or caps.get("version")
        if not version:
            # Fallback to a clear recent version if detection fails
            version = "120.0.0.0"
        
        # Use Windows UA as it's less likely to be flagged than Headless Linux
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36"
        )

    def _apply_chrome_overrides(self) -> None:
        if not hasattr(self.driver, "execute_cdp_cmd"):
            return
        user_agent = self._build_container_user_agent()
        
        # 1. Override UA to Windows
        self.driver.execute_cdp_cmd(
            "Network.setUserAgentOverride",
            {
                "userAgent": user_agent,
                "platform": "Windows",
            },
        )
        
        # 2. Inject Comprehensive Stealth Scripts
        stealth_script = """
            // Hide Webdriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Mock Plugins with realistic PluginArray
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const plugins = [
                        {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
                        {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
                        {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''}
                    ];
                    plugins.__proto__ = PluginArray.prototype;
                    return plugins;
                }
            });
            
            // Languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            
            // Hardware Concurrency (realistic CPU cores)
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });
            
            // Device Memory (realistic RAM)
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });
            
            // Mock Chrome Object
            if (!window.chrome) {
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };
            }
            
            // Mock Permissions API
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Mock Battery API
            Object.defineProperty(navigator, 'getBattery', {
                value: () => Promise.resolve({
                    charging: true,
                    chargingTime: 0,
                    dischargingTime: Infinity,
                    level: 1
                })
            });
            
            // Override outerWidth/outerHeight (headless detection)
            if (window.outerWidth === 0) {
                Object.defineProperty(window, 'outerWidth', {get: () => window.innerWidth});
                Object.defineProperty(window, 'outerHeight', {get: () => window.innerHeight});
            }
            
            // Canvas Fingerprint Randomization
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type) {
                const context = this.getContext('2d');
                if (context) {
                    const imageData = context.getImageData(0, 0, this.width, this.height);
                    // Add subtle noise to prevent fingerprinting
                    for (let i = 0; i < imageData.data.length; i += 4) {
                        imageData.data[i] += Math.floor(Math.random() * 3) - 1;
                    }
                    context.putImageData(imageData, 0, 0);
                }
                return originalToDataURL.apply(this, arguments);
            };
            
            // WebGL Fingerprint Spoofing
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                // UNMASKED_VENDOR_WEBGL
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                // UNMASKED_RENDERER_WEBGL  
                if (parameter === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter.apply(this, arguments);
            };
            
            // Scrub CDC variables (Selenium artifacts)
            let objectToInspect = window;
            let result = [];
            while(objectToInspect !== null) { 
                result = result.concat(Object.getOwnPropertyNames(objectToInspect)); 
                objectToInspect = Object.getPrototypeOf(objectToInspect); 
            }
            result.forEach(p => p.match(/.+_.+_(Array|Promise|Symbol)/ig) && delete window[p]);
            
            // Remove Selenium-specific properties
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
        """
        
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": stealth_script},
        )
        
        # 3. Set Realistic HTTP Headers
        self.driver.execute_cdp_cmd(
            "Network.setExtraHTTPHeaders",
            {
                "headers": {
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "DNT": "1",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1"
                }
            }
        )

        try:
            self.driver.execute_cdp_cmd(
                "Emulation.setLocaleOverride",
                {"locale": "en-US"},
            )
        except Exception:
            pass

    async def navigate_to_login(self, retries: int = 2) -> None:
        """
        Navigate to login page. 
        Strategy: Direct link with heavy stealth injection and human-like timing.
        """
        import random
        
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            await self.log(f"NAVIGATE: {self.sel.URL_BASE} (attempt {attempt + 1})")
            self._apply_chrome_overrides()
            
            # Human-like delay before navigation (0.5-1.5s)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            try:
                self.driver.get(self.sel.URL_BASE)
                
                # Critical: Wait for any JS redirects to "System Requirements" to trigger
                # Use random delay to avoid pattern detection (4-7s)
                wait_time = random.uniform(4.0, 7.0)
                await self.log(f"Waiting {wait_time:.1f}s for page to stabilize...")
                await asyncio.sleep(wait_time)
                
                # Check for blocking immediately
                if self._is_system_requirements_page():
                    await self.log("WARN System requirements detected")
                    raise RuntimeError("System requirements page detected")

                # Wait for Login Form
                self.helpers.wait_for_element(*self.sel.LOGIN_USERNAME)
                await self.log("OK Login page loaded successfully")
                return # Success

            except Exception as exc:
                last_error = exc
                await self.log(f"WARN Navigation attempt {attempt + 1} failed: {exc}")
                if attempt >= retries:
                    break
                
                # Reset strategy for retry with random backoff
                self._reset_session()
                self.driver.get("about:blank")
                backoff = random.uniform(2.0, 4.0)
                await self.log(f"Retrying in {backoff:.1f}s...")
                await asyncio.sleep(backoff)

        raise RuntimeError("Failed to load Chase login page") from last_error


    async def fill_credentials(self, username: str, password: str) -> None:
        await self.log("Waiting for login fields...")
        self.helpers.send_keys(*self.sel.LOGIN_USERNAME, username)
        self.helpers.send_keys(*self.sel.LOGIN_PASSWORD, password)
        await self.log("OK Credentials filled")

    async def submit_login(self) -> None:
        await self.log("Submitting login...")
        try:
            self.helpers.click_element(*self.sel.LOGIN_SUBMIT)
        except Exception:
            await self.log("Fallback: using submit button")
            self.helpers.click_element(*self.sel.LOGIN_SUBMIT_FALLBACK)
        await self.log("OK Login submitted")

    async def open_mfa_dropdown(self) -> None:
        await self.log("Opening MFA dropdown...")
        self.helpers.click_element(*self.sel.MFA_DROPDOWN)
        await self.log("OK MFA dropdown opened")

    async def select_mfa_option(self, option_id: Optional[str]) -> None:
        await self.log("Selecting MFA option...")
        if option_id:
            self.helpers.click_element(By.ID, option_id)
        else:
            self.helpers.click_element(*self.sel.MFA_OPTION_DEFAULT)
        await self.log("OK MFA option selected")

    async def request_mfa_code(self) -> None:
        await self.log("Requesting MFA code...")
        self.helpers.click_element(*self.sel.MFA_NEXT)
        await self.log("OK MFA code requested")

    async def confirm_mfa_login(self) -> None:
        await self.log("Waiting for user to fill OTP and password...")
        self.helpers.wait_for_element(*self.sel.MFA_OTP_INPUT)
        self.helpers.wait_for_element(*self.sel.MFA_PASSWORD_INPUT)
        await self.log("Submitting MFA verification...")
        self.helpers.click_element(*self.sel.MFA_NEXT_AFTER_OTP)
        await self.log("OK MFA verification submitted")

    async def wait_for_login_complete(self, timeout_seconds: int) -> None:
        await self.log(f"Waiting up to {timeout_seconds}s for MFA completion...")
        try:
            self.helpers.wait_until(
                lambda d: len(d.find_elements(*self.sel.MENU_INVESTMENTS)) > 0,
                timeout=timeout_seconds,
            )
            await self.log("OK MFA completed")
        except Exception as exc:
            raise RuntimeError("MFA timeout waiting for Investments menu.") from exc

    async def open_investments_menu(self) -> None:
        await self.log("Opening Investments menu...")
        self.helpers.click_element(*self.sel.MENU_INVESTMENTS)
        await self.log("OK Investments menu opened")

    async def open_positions(self) -> None:
        await self.log("Opening Positions...")
        self.helpers.click_element(*self.sel.MENU_POSITIONS)
        await self.log("OK Positions opened")

    async def select_all_accounts(self) -> None:
        await self.log("Selecting all eligible accounts...")
        self.helpers.click_element(*self.sel.ACCOUNTS_DROPDOWN)
        self.helpers.click_element(*self.sel.ACCOUNTS_ALL_ELIGIBLE)
        await self.log("OK Accounts selected")

    async def enable_show_all_tax_lots(self) -> None:
        await self.log("Enabling show all tax lots...")
        toggle = self.helpers.find_element(*self.sel.SHOW_ALL_TAX_LOTS)
        is_checked = (toggle.get_attribute("aria-checked") or "").lower() == "true"
        if not is_checked:
            toggle.click()
        await self.log("OK Show all tax lots enabled")

    async def open_things_you_can_do(self) -> None:
        await self.log("Opening Things you can do...")
        self.helpers.click_element(*self.sel.THINGS_YOU_CAN_DO)
        await self.log("OK Things you can do opened")

    async def open_export_as(self) -> None:
        await self.log("Opening Export as...")
        self.helpers.click_element(*self.sel.EXPORT_AS_GROUP)
        await self.log("OK Export as opened")

    async def select_export_excel(self) -> None:
        await self.log("Selecting Microsoft Excel export...")
        self.helpers.click_element(*self.sel.EXPORT_AS_EXCEL)
        await self.log("OK Microsoft Excel selected")

    async def select_transactions(self) -> None:
        await self.log("Selecting Transactions...")
        self.helpers.click_element(*self.sel.TRANSACTIONS_TAB)
        await self.log("OK Transactions selected")

    async def select_custom_range(self) -> None:
        await self.log("Selecting Custom date range...")
        self.helpers.click_element(*self.sel.CUSTOM_RANGE)
        await self.log("OK Custom range selected")

    async def set_custom_dates(self, start_date: str, end_date: str) -> None:
        await self.log(f"Setting date range: {start_date} - {end_date}")
        self.helpers.clear_and_send_keys(*self.sel.CUSTOM_FROM, start_date)
        self.helpers.clear_and_send_keys(*self.sel.CUSTOM_TO, end_date)
        await self.log("OK Date range set")

    async def apply_custom_dates(self) -> None:
        await self.log("Applying custom date range...")
        self.helpers.click_element(*self.sel.CUSTOM_APPLY)
        await self.log("OK Custom date range applied")

    async def export_transactions_excel(self) -> None:
        await self.log("Exporting to Excel...")
        self.helpers.click_element(*self.sel.EXPORT_BUTTON)
        self.helpers.click_element(*self.sel.EXPORT_MENU_EXCEL)
        await self.log("OK Export triggered")

    async def export_holdings(self, date: Optional[str] = None) -> None:
        """
        Export portfolio holdings/positions.
        
        Args:
            date: Optional date (not currently used for JPM positions as they are real-time/D0)
        """
        await self.log(f"Exporting holdings (Date: {date or 'Current'})...")
        await self.open_investments_menu()
        await self.open_positions()
        await self.select_all_accounts()
        await self.enable_show_all_tax_lots()
        
        await self.open_things_you_can_do()
        await self.open_export_as()
        await self.select_export_excel()
        await self.log("OK Holdings export triggered")

    async def export_history(self, date: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> None:
        """
        Export transaction history.
        
        Args:
            date: Reference calculation date
            start_date: Start date for range
            end_date: End date for range
        """
        target_start = start_date or date
        target_end = end_date or date
        
        await self.log(f"Exporting history (Range: {target_start} - {target_end})...")
        
        # Ensure we are in the Investments -> Positions context
        # (This is required to access the Transactions tab and Export options)
        await self.open_investments_menu()
        await self.open_positions()
        await self.select_all_accounts()
        await self.enable_show_all_tax_lots()
        
        await self.open_things_you_can_do()
        await self.open_export_as()
        await self.select_export_excel()
        
        # Select Transactions context
        await self.select_transactions()
        
        await self.select_custom_range()
        if target_start and target_end:
            await self.set_custom_dates(target_start, target_end)
            await self.apply_custom_dates()
        
        await self.export_transactions_excel()
        await self.log("OK History export triggered")

    async def logout(self) -> None:
        await self.log("Signing out...")
        self.helpers.click_element(*self.sel.SIGN_OUT)
        await self.log("OK Signed out")
