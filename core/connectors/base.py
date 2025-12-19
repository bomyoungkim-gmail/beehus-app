from abc import ABC, abstractmethod
from typing import Dict, Any, List
from core.schemas.messages import ScrapeResult

class BaseConnector(ABC):
    """
    Interface that all Scraper Plugins must implement.
    """
    
    @abstractmethod
    async def scrape(self, driver, params: Dict[str, Any]) -> ScrapeResult:
        """
        Executes the scraping logic.
        :param driver: RemoteWebDriver instance (Selenium)
        :param params: Job parameters
        :return: ScrapeResult
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass
