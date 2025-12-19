from core.connectors.base import BaseConnector
from core.schemas.messages import ScrapeResult
from selenium.webdriver.common.by import By
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class ExampleConnector(BaseConnector):
    @property
    def name(self):
        return "example_site"

    async def scrape(self, driver, params: Dict[str, Any]) -> ScrapeResult:
        logger.info(f"Starting Example Scrape with params: {params}")
        
        # 1. Target URL (default or from params)
        url = params.get("url", "https://example.com")
        
        # 2. Navigate
        driver.get(url)
        
        # 3. Extract logic
        title = driver.title
        heading = driver.find_element(By.TAG_NAME, "h1").text
        
        # 4. Result
        data = {
            "title": title,
            "heading": heading,
            "url": driver.current_url
        }
        
        return ScrapeResult(
            run_id=params.get("run_id", "unknown"),
            success=True,
            data=data,
            meta={"scraped_at": params.get("created_at")}
        )
