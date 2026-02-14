import logging
import os
import re
import time

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from core.config import settings

logger = logging.getLogger(__name__)


class SeleniumExecutor:
    """
    Manages the lifecycle of a Selenium WebDriver instance.
    Supports Hybrid Mode:
    - Local: Uses undetected-chromedriver (for JP Morgan evasion)
    - Remote: Uses Selenium Grid (for standard scraping)
    """
    def __init__(self, use_local: bool = False, download_dir: str = "/downloads"):
        """Initialize executor state and mode."""
        self.driver = None
        self.node_id = None
        self.node_uri = None
        self.vnc_url = None
        self.use_local = use_local
        self.download_dir = download_dir

    def start(self):
        """Initializes the webdriver connection based on mode."""
        if self.driver:
            return

        chrome_options = Options()
        # Basic options for stability and container compatibility
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--lang=en-US,en")
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
        # chrome_options.add_argument("--headless") # Disabled to allow VNC visibility

        prefs = {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "profile.default_content_settings.popups": 0,
            "profile.default_content_setting_values.automatic_downloads": 1,
            "download.open_pdf_in_system_reader": False,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False
        }
        chrome_options.add_experimental_option("prefs", prefs)
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        if self.use_local:
            # --- LOCAL EXECUTION (JP Morgan Evasion) ---
            logger.info("🔌 Initializing Driver (LOCAL Mode for Evasion)...")
            try:
                os.environ["DISPLAY"] = os.environ.get("DISPLAY", ":99")
                import undetected_chromedriver as uc
                logger.info("⚡ Attempting to start Local Undetected Chrome...")
                
                uc_options = uc.ChromeOptions()
                for arg in chrome_options.arguments:
                    if "--headless" not in arg:
                        uc_options.add_argument(arg)
                uc_options.add_experimental_option("prefs", prefs)

                uc_options.add_argument("--no-sandbox")
                uc_options.add_argument("--disable-dev-shm-usage")
                uc_options.add_argument("--window-size=1920,1080")
                uc_options.add_argument("--window-position=0,0")
                uc_options.add_argument("--disable-gpu")
                uc_options.add_argument("--no-first-run")
                uc_options.add_argument("--no-default-browser-check")
                
                self.driver = uc.Chrome(
                    options=uc_options,
                    version_main=None,
                    headless=False,
                    use_subprocess=True,
                )
                self._enable_auto_download()
                logger.info(f"✅ Created Local UC driver session: {self.driver.session_id}")
                self.node_id = "LOCAL_WORKER_CONTAINER"
                self.vnc_url = f"{settings.VNC_URL_BASE}:7901"
            except Exception as e:
                logger.error(f"❌ Failed to start local driver: {e}")
                raise
        else:
            # --- REMOTE GRID EXECUTION (Standard) ---
            logger.info(f"🔌 Initializing Driver (REMOTE Mode at {settings.SELENIUM_REMOTE_URL})...")
            try:
                self.driver = webdriver.Remote(
                    command_executor=settings.SELENIUM_REMOTE_URL,
                    options=chrome_options
                )
                self._enable_auto_download()
                logger.info(f"✅ Created remote driver session: {self.driver.session_id}")
                
                # Try to get node info
                self._resolve_vnc_url()
                if self.vnc_url:
                    logger.info(f"📺 VNC: {self.vnc_url}")
                else:
                    logger.warning("⚠️ VNC URL not resolved for this session")
            except Exception as e:
                logger.error(f"❌ Failed to connect to Selenium Grid: {e}")
                raise

    def _enable_auto_download(self) -> None:
        """
        Force Chrome to allow downloads in the configured directory without Save dialog.
        """
        if not self.driver:
            return
        page_ok = self._execute_cdp_command(
            "Page.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": self.download_dir},
        )
        browser_ok = self._execute_cdp_command(
            "Browser.setDownloadBehavior",
            {
                "behavior": "allow",
                "downloadPath": self.download_dir,
                "eventsEnabled": False,
            },
        )

        if page_ok or browser_ok:
            logger.info(
                "⬇️ Auto-download behavior enabled via CDP (page=%s, browser=%s)",
                page_ok,
                browser_ok,
            )
        else:
            logger.warning("Could not set CDP download behavior with available driver APIs")

    def _execute_cdp_command(self, cmd: str, params: dict) -> bool:
        """Execute CDP command across local and remote driver implementations."""
        if not self.driver:
            return False

        # Local Chrome and some Selenium bindings expose execute_cdp_cmd directly.
        try:
            execute_cdp = getattr(self.driver, "execute_cdp_cmd", None)
            if callable(execute_cdp):
                execute_cdp(cmd, params)
                return True
        except Exception as e:
            logger.debug("CDP via execute_cdp_cmd failed for %s: %s", cmd, e)

        # RemoteWebDriver may only support the generic command executor API.
        try:
            execute = getattr(self.driver, "execute", None)
            command_executor = getattr(self.driver, "command_executor", None)
            if callable(execute) and command_executor is not None:
                commands = getattr(command_executor, "_commands", None)
                if isinstance(commands, dict):
                    commands.setdefault(
                        "executeCdpCommand",
                        ("POST", "/session/$sessionId/goog/cdp/execute"),
                    )
                execute("executeCdpCommand", {"cmd": cmd, "params": params})
                return True
        except Exception as e:
            logger.debug("CDP via execute() failed for %s: %s", cmd, e)

        return False

    def _resolve_vnc_url(self, retries: int = 5, delay_seconds: float = 1.0) -> None:
        """Resolve and set the VNC URL for the current session."""
        # First try capabilities (Grid may expose nodeId)
        caps = getattr(self.driver, "capabilities", {}) or {}
        node_id = caps.get("se:nodeId") or caps.get("nodeId")
        if node_id:
            self.node_id = node_id
            self.vnc_url = self._build_vnc_url(self.node_id, self.node_uri)
            if self.vnc_url:
                return

        # Retry Grid session endpoint while session is still live
        for _ in range(retries):
            self.node_id = self.get_node_info()
            # Prefer nodeUri when available (more reliable for mapping VNC ports)
            if self.node_uri:
                self.vnc_url = self._build_vnc_url(self.node_id or "", self.node_uri)
                if self.vnc_url:
                    return
            if self.node_id:
                self.vnc_url = self._build_vnc_url(self.node_id, self.node_uri)
                if self.vnc_url:
                    return
            time.sleep(delay_seconds)

    def _build_vnc_url(self, node_id: str, node_uri: str | None) -> str | None:
        """Build a VNC URL from the node ID or URI."""
        candidates = [node_id or "", node_uri or ""]
        for value in candidates:
            match = re.search(r"chrome-node-(\d+)", value)
            if match:
                node_num = int(match.group(1))
                return f"{settings.VNC_URL_BASE}:{7901 + node_num}"
        return None

    def get_node_info(self):
        """Attempt to retrieve the node ID from Selenium Grid."""
        try:
            if not self.driver or not self.driver.session_id:
                return None
            
            # Query Grid status endpoint
            grid_url = settings.SELENIUM_REMOTE_URL.replace('/wd/hub', '')
            session_url = f"{grid_url}/se/grid/session/{self.driver.session_id}"
            status_url = f"{grid_url}/status"

            # Prefer session lookup (more reliable for node mapping)
            try:
                response = requests.get(session_url, timeout=5)
                if response.status_code == 200:
                    data = response.json().get("value", {})
                    node_id = data.get("nodeId")
                    node_uri = data.get("nodeUri") or data.get("uri")
                    logger.info(
                        "Grid session lookup: status=200 nodeId=%s nodeUri=%s",
                        node_id,
                        node_uri,
                    )
                    if node_uri:
                        self.node_uri = node_uri
                    if node_id:
                        return node_id
                else:
                    logger.warning(
                        "Grid session lookup: status=%s body=%s",
                        response.status_code,
                        response.text[:500],
                    )
            except Exception as e:
                logger.warning(f"Could not query session endpoint: {e}")

            # Try alternate session endpoint (older grid versions)
            try:
                alt_session_url = f"{grid_url}/session/{self.driver.session_id}"
                alt_res = requests.get(alt_session_url, timeout=5)
                if alt_res.status_code == 200:
                    data = alt_res.json().get("value", {})
                    node_id = data.get("nodeId")
                    node_uri = data.get("nodeUri") or data.get("uri")
                    logger.info(
                        "Grid alt session lookup: status=200 nodeId=%s nodeUri=%s",
                        node_id,
                        node_uri,
                    )
                    if node_uri:
                        self.node_uri = node_uri
                    if node_id:
                        return node_id
                else:
                    logger.warning(
                        "Grid alt session lookup: status=%s body=%s",
                        alt_res.status_code,
                        alt_res.text[:500],
                    )
            except Exception as e:
                logger.warning(f"Could not query alternate session endpoint: {e}")
            
            # Try GraphQL session lookup (Selenium 4)
            try:
                gql_url = f"{grid_url}/graphql"
                query = {
                    "query": (
                        "query { "
                        f"session(id: \"{self.driver.session_id}\") {{ id, nodeId, nodeUri }} "
                        "}"
                    )
                }
                gql_res = requests.post(gql_url, json=query, timeout=5)
                if gql_res.status_code == 200:
                    gql_data = gql_res.json()
                    session = (gql_data.get("data") or {}).get("session") or {}
                    node_id = session.get("nodeId")
                    node_uri = session.get("nodeUri")
                    logger.info(
                        "Grid GraphQL session lookup: status=200 nodeId=%s nodeUri=%s",
                        node_id,
                        node_uri,
                    )
                    if node_uri:
                        self.node_uri = node_uri
                    if node_id:
                        return node_id
                else:
                    logger.warning(
                        "Grid GraphQL session lookup: status=%s body=%s",
                        gql_res.status_code,
                        gql_res.text[:500],
                    )
            except Exception as e:
                logger.warning(f"Could not query GraphQL session: {e}")

            response = requests.get(status_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                # Try to find which node has our session
                nodes = data.get('value', {}).get('nodes', [])
                for node in nodes:
                    node_id = node.get('nodeId') or node.get('id')
                    node_uri = node.get('uri')
                    if node_id:
                        self.node_uri = node_uri
                        return node_id
            
            return None
        except Exception as e:
            logger.warning(f"Could not determine node ID: {e}")
            return None

    def stop(self):
        """Quits the webdriver session."""
        if self.driver:
            try:
                logger.info("🛑 Quitting webdriver session...")
                self.driver.quit()
            except Exception as e:
                logger.warning(f"Error quitting driver: {e}")
            finally:
                self.driver = None
                self.node_id = None
