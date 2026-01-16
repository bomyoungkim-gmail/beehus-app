import logging
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from core.config import settings

logger = logging.getLogger(__name__)

class SeleniumExecutor:
    """
    Manages the lifecycle of a Selenium WebDriver instance connected to the Grid.
    """
    def __init__(self):
        self.driver = None
        self.node_id = None

    def start(self):
        """Initializes the remote webdriver connection."""
        if self.driver:
            return

        chrome_options = Options()
        # Ensure we run headless if needed, though on Grid usually it doesn't matter as much, 
        # but good practice for consistency.
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--window-size=1920,1080")
        # chrome_options.add_argument("--headless") # Optional, helpful for stability

        prefs = {
            "download.default_directory": "/home/seluser/Downloads",
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        chrome_options.add_experimental_option("prefs", prefs)

        logger.info(f"🔌 Connecting to Selenium Grid at {settings.SELENIUM_REMOTE_URL}...")
        
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
            
            # Fallback: use a generic identifier
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
