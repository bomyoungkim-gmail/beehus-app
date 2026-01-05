"""
Repository for Run-related operations using Beanie ODM.
Replaces SQLAlchemy/raw SQL implementation.
"""

import os
from motor.motor_asyncio import AsyncIOMotorClient
from core.config import settings
from core.models.mongo_models import Run
from datetime import datetime


class RunRepository:
    """Repository for managing Run documents and raw data"""
    
    def __init__(self):
        self.mongo_client = AsyncIOMotorClient(settings.MONGO_URI)
        self.mongo_db = self.mongo_client[settings.MONGO_DB_NAME]

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
            update_dict["started_at"] = datetime.utcnow()
        elif status in ["success", "failed"]:
            update_dict["finished_at"] = datetime.utcnow()
        
        try:
            # Use direct MongoDB update_one for guaranteed persistence
            from pymongo import UpdateOne
            
            # Explicitly force string ID just in case
            query_id = str(run_id) 
            
            result = await Run.get_motor_collection().update_one(
                {"_id": query_id},
                {"$set": update_dict}
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
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    await redis_client.publish("run_updates", json.dumps(message))
                    await redis_client.close()
                except Exception as redis_error:
                    # Don't fail the job if Redis publishing fails
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Redis publish failed: {redis_error}")
            else:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Run {run_id} not found for status update")
                    
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error updating run {run_id[:8]}: {e}")

    async def save_raw_payload(self, run_id: str, url: str, content: str):
        """
        Save raw scraping payload to MongoDB.
        TODO: Fix event loop conflict with AsyncIOMotorClient
        """
        pass
    
    async def save_evidence(self, run_id: str, screenshot_path: str = None, html_path: str = None):
        """
        Save evidence (screenshots, HTML dumps) for failed runs.
        
        Args:
            run_id: Associated run ID
            screenshot_path: Path to screenshot file
            html_path: Path to HTML dump file
        """
        await self.mongo_db.evidences.insert_one({
            "run_id": run_id,
            "screenshot_path": screenshot_path,
            "html_path": html_path,
            "created_at": datetime.utcnow()
        })


# Global singleton instance
repo = RunRepository()
