from core.connectors.base import BaseConnector
from core.schemas.messages import ScrapeResult
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import logging
import time
from typing import Dict, Any

# TODO: implementar scrapping para download 
logger = logging.getLogger(__name__)

class MyNewScraper(BaseConnector):
    @property
    def name(self):
        """
        Unique identifier for this connector. 
        Used when creating a Job (connector='my_new_site').
        """
        return "my_new_site"

    async def scrape(self, driver, params: Dict[str, Any]) -> ScrapeResult:
        """
        Main scraping logic.
        :param driver: Is a RemoteWebDriver instance (synced).
        """
        logger.info(f"Starting MyNewScraper with params: {params}")
        
        target_url = params.get("url", "https://example.com")
        
        try:
            # 1. Navigate
            driver.get(target_url)
            
            # 2. Wait for element (Best Practice: Explicit Wait)
            wait = WebDriverWait(driver, 15) # 15 seconds timeout
            # Example: Wait for the main heading to be visible
            heading_el = wait.until(EC.visibility_of_element_located((By.TAG_NAME, "h1")))
            
            # 3. Interact (Click, Type)
            # btn = driver.find_element(By.ID, "submit-btn")
            # btn.click()
            
            # 4. Extract Data
            title = driver.title
            heading_text = heading_el.text
            
            # Example: Find list items
            # items = driver.find_elements(By.CSS_SELECTOR, ".item-class")
            # data_list = [item.text for item in items]

            # 5. Return Result
            return ScrapeResult(
                run_id=params.get("run_id"),
                success=True,
                data={
                    "title": title,
                    "heading": heading_text,
                    # "items": data_list
                }
            )

        except TimeoutException:
            logger.error("Element not found within timeout")
            # You can extract page source here for debugging
            # html = driver.page_source
            return ScrapeResult(run_id=params.get("run_id"), success=False, error="Timeout waiting for element")
            
        except Exception as e:
            logger.exception("Scraping failed")
            return ScrapeResult(run_id=params.get("run_id"), success=False, error=str(e))
