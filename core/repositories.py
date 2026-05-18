"""
Repository for Run-related operations using Beanie ODM.
Replaces SQLAlchemy/raw SQL implementation.
"""

import os
import logging
from core.models.mongo_models import Run
from core.utils.date_utils import get_now
from core.services.run_state import run_state

logger = logging.getLogger(__name__)

class RunRepository:
    """Repository for managing Run documents and raw data"""

    @staticmethod
    def _database():
        # Reuse Beanie's active Motor database bound to the current event loop.
        return Run.get_motor_collection().database

    async def save_run_status(self, run_id: str, status: str, error: str = None):
        """
        Update run status in MongoDB using atomic updates.
        Also publishes the update to Redis for real-time WebSocket clients.
        
        Args:
            run_id: Run document ID
            status: New status (queued, running, success, failed)
            error: Optional error message
        """
        try:
            updated = await run_state.save_run_status(
                str(run_id),
                status,
                error=error,
            )
            if not updated:
                logger.error(f"Run {run_id} not found for status update")
        except Exception as e:
            logger.error(f"Error updating run {run_id[:8]}: {e}")

    async def save_raw_payload(self, run_id: str, url: str, content: str):
        """
        Save raw scraping payload to MongoDB.
        """
        await self._database().raw_payloads.insert_one(
            {
                "run_id": str(run_id),
                "url": url,
                "content": content,
                "created_at": get_now(),
            }
        )
    
    async def save_evidence(self, run_id: str, screenshot_path: str = None, html_path: str = None):
        """
        Save evidence (screenshots, HTML dumps) for failed runs.
        
        Args:
            run_id: Associated run ID
            screenshot_path: Path to screenshot file
            html_path: Path to HTML dump file
        """
        await self._database().evidences.insert_one({
            "run_id": run_id,
            "screenshot_path": screenshot_path,
            "html_path": html_path,
            "created_at": get_now()
        })


# Global singleton instance
repo = RunRepository()
