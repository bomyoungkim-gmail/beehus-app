"""
Repository for Run-related operations using Beanie ODM.
Replaces SQLAlchemy/raw SQL implementation.
"""

import os
import logging
from core.models.mongo_models import Run
from core.utils.date_utils import get_now

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
        update_dict = {"status": status}
        
        if error is not None:
            update_dict["error_summary"] = error
            
        if status == "running":
            update_dict["started_at"] = get_now()
        elif status in ["success", "failed"]:
            update_dict["finished_at"] = get_now()
        
        try:
            # Explicitly force string ID just in case
            query_id = str(run_id) 
            
            result = await Run.get_motor_collection().update_one(
                {"_id": query_id},
                {"$set": update_dict}
            )

            if result.matched_count == 0:
                logger.error(
                    "[CRITICAL] Run %s not matched in DB for status update. Check _id type.",
                    run_id,
                )
            
            if result.matched_count > 0:
                # Publish to Redis for WebSockets
                try:
                    import redis.asyncio as redis
                    import json
                    from core.config import settings
                    
                    redis_client = redis.from_url(settings.REDIS_URL)
                    message = {
                        "run_id": run_id,
                        "status": status,
                        "node": os.getenv("HOSTNAME", "worker"),
                        "timestamp": get_now().isoformat()
                    }
                    await redis_client.publish("run_updates", json.dumps(message))
                    await redis_client.close()
                except Exception as redis_error:
                    # Don't fail the job if Redis publishing fails
                    logger.error(f"Redis publish failed: {redis_error}")
            else:
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
