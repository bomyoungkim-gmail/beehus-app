import logging
import os
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
    def __init__(self, use_local: bool = False):
        self.driver = None
        self.node_id = None
        self.use_local = use_local

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
            "download.default_directory": "/home/seluser/Downloads",
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
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
                logger.info(f"✅ Created Local UC driver session: {self.driver.session_id}")
                self.node_id = "LOCAL_WORKER_CONTAINER"
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
                logger.info(f"✅ Created remote driver session: {self.driver.session_id}")
                
                # Try to get node info
                self.node_id = self.get_node_info()
                if self.node_id:
                     logger.info(f"📍 Executing on node: {self.node_id}")
            except Exception as e:
                 logger.error(f"❌ Failed to connect to Selenium Grid: {e}")
                 raise

    def get_node_info(self):
        """Attempt to retrieve the node ID from Selenium Grid."""
        try:
            if not self.driver or not self.driver.session_id:
                return None
            
            # Query Grid status endpoint
            grid_url = settings.SELENIUM_REMOTE_URL.replace('/wd/hub', '')
            status_url = f"{grid_url}/status"
            
            response = requests.get(status_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                # Try to find which node has our session
                nodes = data.get('value', {}).get('nodes', [])
                for node in nodes:
                    node_id = node.get('nodeId') or node.get('id')
                    if node_id:
                        return node_id
            
            return "selenium-node-1"
        except Exception as e:
            logger.warning(f"Could not determine node ID: {e}")
            return "selenium-node-unknown"

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
